/* Browser acceptance against rendered buyer_support.html and a local synthetic SSE server.
 * NODE_PATH must provide playwright. Pass a Django-rendered HTML path as argv[2]. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(process.argv[2], 'utf8');
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const calls = [], pending = [];
let onRequest = null;
const final = { answer: '绿茶知识回答已核验。', conversation_id: 'synthetic-conversation', revision: 1,
    intent: 'question_answering', intents: ['question_answering'], recommendations: [],
    knowledge_sources: [{ title: '测试资料', url: 'https://example.invalid/source' }] };
const server = http.createServer((req, res) => {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/buyer_support.html') {
        res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(html); return;
    }
    if (url.pathname.startsWith('/static/')) {
        const file = path.resolve(root, 'client', '.' + url.pathname);
        if (!file.startsWith(path.join(root, 'client', 'static') + path.sep) || !fs.existsSync(file)) {
            res.writeHead(404).end(); return;
        }
        res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'application/octet-stream');
        res.end(fs.readFileSync(file)); return;
    }
    if (url.pathname === '/v1/support/chat/') {
        let text = '';
        req.on('data', c => { text += c; });
        req.on('end', () => {
            calls.push(JSON.parse(text));
            assert.equal(req.headers.accept, 'text/event-stream');
            res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store' });
            res.write(frame('status', { stage: 'retrieval', message: '正在查找相关资料…' }));
            pending.push(res);
            if (onRequest) { onRequest(res); onRequest = null; }
        });
        return;
    }
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ code: 200, preferences: {}, conversations: [], data: {} }));
});
function nextRequest() { return new Promise(resolve => { onRequest = resolve; }); }
(async () => {
    let browser;
    try {
        await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
        const origin = `http://127.0.0.1:${server.address().port}`;
        browser = await chromium.launch({ headless: true, channel: process.env.SUPPORT_TEST_BROWSER || 'msedge' });
        const context = await browser.newContext({ viewport: { width: 1280, height: 960 } });
        await context.route('**/*', route => {
            if (route.request().url().startsWith(origin + '/')) return route.continue();
            return route.abort(); // Never contact the actual shop, models or external sources.
        });
        await context.addInitScript(() => {
            sessionStorage.setItem('tea_saas_token', 'synthetic-token');
            sessionStorage.setItem('tea_saas_user', 'synthetic-buyer');
            sessionStorage.setItem('tea_saas_user_type', 'customer');
        });
        const page = await context.newPage(), errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.goto(origin + '/buyer_support.html');
        await page.waitForFunction(() => !document.getElementById('bs-send').disabled);
        const submit = async text => {
            const requested = nextRequest();
            await page.locator('#bs-input').fill(text);
            await page.locator('#bs-send').click();
            return requested;
        };
        // The server stays open until the test explicitly releases each stage.
        const first = await submit('介绍绿茶');
        await page.waitForFunction(() => document.querySelector('#bs-messages .bs-assistant:last-child').textContent.includes('正在查找相关资料'));
        assert.equal(await page.locator('#bs-send').isDisabled(), true);
        first.write(frame('answer', { text: '绿茶知识回答已核验。', provisional: true }));
        await page.waitForFunction(() => document.querySelector('#bs-messages .bs-assistant:last-child').textContent.includes('尚未保存'));
        assert.equal(await page.locator('.bs-sources').count(), 0);
        assert.equal(await page.evaluate(() => sessionStorage.getItem('support-conversation:synthetic-buyer')), null);
        first.end(frame('done', final));
        await page.waitForFunction(() => !document.getElementById('bs-send').disabled);
        assert.equal(await page.locator('.bs-sources a').innerText(), '测试资料');
        assert.equal(await page.locator('#bs-messages .bs-assistant:last-child [role="status"]').count(), 0);
        assert.equal(JSON.parse(await page.evaluate(() => sessionStorage.getItem('support-conversation:synthetic-buyer'))).revision, 1);
        // A truncated stream replaces provisional text and keeps the same request ID for retry.
        const second = await submit('断线测试');
        second.write(frame('answer', { text: '暂时展示的结果', provisional: true }));
        second.end();
        await page.waitForFunction(() => !document.getElementById('bs-send').disabled);
        assert.match(await page.locator('#bs-messages .bs-assistant').last().innerText(), /连接中断/);
        assert.equal(await page.locator('#bs-input').inputValue(), '断线测试');
        const third = await submit('断线测试');
        assert.equal(calls[1].request_id, calls[2].request_id);
        third.end(frame('done', { ...final, revision: 2 }));
        await page.waitForFunction(() => !document.getElementById('bs-send').disabled);
        // Error events clear provisional content, keep the UI usable, and retain status metadata.
        const fourth = await submit('服务错误测试');
        fourth.write(frame('answer', { text: '不得残留的部分回答', provisional: true }));
        fourth.end(frame('error', { error: '数据服务暂不可用', status: 503, error_code: 'SYNTHETIC_ERROR' }));
        await page.waitForFunction(() => !document.getElementById('bs-send').disabled);
        assert.equal(await page.locator('#bs-messages .bs-assistant .bs-bubble').last().innerText(), '数据服务暂不可用');
        // Identity changes abort the open response and remove the previous buyer's content.
        const fifth = await submit('账号测试');
        await page.evaluate(() => {
            sessionStorage.setItem('tea_saas_token', 'other-token');
            sessionStorage.setItem('tea_saas_user', 'other-buyer');
            window.dispatchEvent(new StorageEvent('storage'));
        });
        fifth.end(frame('done', { ...final, answer: '旧账号内容不能出现', revision: 3 }));
        await page.waitForFunction(() => document.getElementById('bs-conversation-status').textContent.includes('登录账号已变化'));
        assert.equal(await page.locator('#bs-send').isDisabled(), true);
        assert.equal(await page.locator('#bs-messages').innerText().then(x => x.includes('旧账号内容不能出现')), false);
        assert.deepEqual(errors, []);
        console.log(JSON.stringify({ status: 'passed', requests: calls.length,
            checks: ['visible progress before completion', 'verified partial answer before save',
                'cards and sources only after done', 'retry preserves request_id', 'error clears provisional text',
                'identity change cancels stream and clears old account', 'no browser errors'] }, null, 2));
    } finally {
        pending.forEach(res => res.destroy());
        if (browser) await browser.close();
        server.closeAllConnections();
        await new Promise(resolve => server.close(resolve));
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
