/* Run with node --test tools/tests/test_support_stream.cjs. No server/model required. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { chat, parser } = require('../../client/static/js/buyer-support-stream.js');
const frame = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const final = { answer: '核验后的绿茶回答🍵', conversation_id: 'c1', revision: 1 };
const opts = extra => Object.assign({ token: 'synthetic-token', checkIdentity() {}, onStatus() {}, onAnswer() {} }, extra);
function mockFetch(t, fn) { const before = global.fetch; global.fetch = fn; t.after(() => { global.fetch = before; }); }
function response(text, width) {
    const bytes = new TextEncoder().encode(text);
    let pos = 0;
    return new Response(new ReadableStream({ pull(controller) {
        if (pos === bytes.length) return controller.close();
        controller.enqueue(bytes.slice(pos, pos += width || bytes.length));
    } }), { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } });
}
test('UTF8 code points and every SSE delimiter may span individual bytes', async t => {
    const statuses = [], answers = [];
    mockFetch(t, async (url, request) => {
        assert.equal(url, '/v1/support/chat/');
        assert.equal(request.method, 'POST');
        assert.equal(request.headers.Accept, 'text/event-stream');
        assert.equal(request.headers.Authorization, 'Bearer synthetic-token');
        assert.equal(JSON.parse(request.body).request_id, 'same-id');
        return response(frame('status', { message: '正在查找资料🍵' }) + frame('ping', {}) +
            frame('answer', { text: '核验要点' }) + frame('done', final), 1);
    });
    const result = await chat({ request_id: 'same-id' }, opts({ onStatus: x => statuses.push(x), onAnswer: x => answers.push(x) }));
    assert.deepEqual(result, final);
    assert.deepEqual(statuses, ['正在查找资料🍵']);
    assert.deepEqual(answers, ['核验要点']);
});
test('CRLF, comments, ignored extensions and multiline data parse together', () => {
    const events = [], accept = parser((...args) => events.push(args));
    accept(': comment\r\nevent: status\r\ndata: {\r\ndata: "message":"收到"}\r\n\r');
    accept('\nevent: future\ndata: private-extension\n\n', true);
    assert.deepEqual(events, [['status', { message: '收到' }]]);
});
test('progress and verified answer appear before the server finishes', async t => {
    let release, sawProgress, sawAnswer;
    const gate = new Promise(resolve => { release = resolve; });
    const progress = new Promise(resolve => { sawProgress = resolve; });
    const answer = new Promise(resolve => { sawAnswer = resolve; });
    mockFetch(t, async () => new Response(new ReadableStream({ async start(c) {
        const send = (event, value) => c.enqueue(new TextEncoder().encode(frame(event, value)));
        send('status', { message: '查询中' });
        send('answer', { text: '已核验的第一项' });
        await gate;
        send('done', final);
        c.close();
    } }), { headers: { 'Content-Type': 'text/event-stream' } }));
    let completed = false;
    const running = chat({}, opts({ onStatus: sawProgress, onAnswer: sawAnswer })).then(x => { completed = true; return x; });
    await progress;
    await answer;
    assert.equal(completed, false);
    release();
    assert.deepEqual(await running, final);
});
test('EOF without done is uncertain and must preserve retry idempotency', async t => {
    mockFetch(t, async () => response(frame('answer', { text: '部分回答' })));
    await assert.rejects(chat({}, opts()), error => !error.status && /重试原问题/.test(error.message));
});
test('in-stream revision conflict preserves HTTP-equivalent status', async t => {
    mockFetch(t, async () => response(frame('error', { error: '会话更新', status: 409, error_code: 'CONVERSATION_CONFLICT' })));
    await assert.rejects(chat({}, opts()), error => error.status === 409 && error.errorCode === 'CONVERSATION_CONFLICT');
});
test('preflight HTTP errors remain actionable', async t => {
    mockFetch(t, async () => Response.json({ error: '登录失效' }, { status: 401 }));
    await assert.rejects(chat({}, opts()), error => error.status === 401);
});
test('old JSON servers remain compatible', async t => {
    mockFetch(t, async () => Response.json(final));
    assert.deepEqual(await chat({}, opts()), final);
});
test('identity changes cancel the reader before delivering cross-account text', async t => {
    let checks = 0, delivered = false, cancelled = false;
    mockFetch(t, async () => new Response(new ReadableStream({
        start(c) { c.enqueue(new TextEncoder().encode(frame('answer', { text: '旧账号回答' }))); },
        cancel() { cancelled = true; }
    }), { headers: { 'Content-Type': 'text/event-stream' } }));
    await assert.rejects(chat({}, opts({
        checkIdentity() { if (++checks >= 3) throw new Error('identity changed'); },
        onAnswer() { delivered = true; }
    })), /identity changed/);
    assert.equal(delivered, false);
    assert.equal(cancelled, true);
});
test('invalid, oversized and truncated event frames fail closed', () => {
    assert.throws(() => parser(() => {})('event: answer\ndata: not-json\n\n'), /异常/);
    assert.throws(() => parser(() => {})('x'.repeat(1048577)), /过长/);
    assert.throws(() => parser(() => {})('event: answer\ndata: {', true), /中断/);
});
test('duplicate terminal frames and invalid final metadata are rejected', async t => {
    mockFetch(t, async () => response(frame('done', final) + frame('done', final)));
    await assert.rejects(chat({}, opts()), /结束标记异常/);
    global.fetch = async () => response(frame('done', { answer: '缺少会话信息' }));
    await assert.rejects(chat({}, opts()), /保存信息异常/);
});
