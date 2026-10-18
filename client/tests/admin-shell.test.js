// Run with node client/tests/admin-shell.test.js. No browser or business DB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

async function shell(permissions, hash) {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, { hidden: false, attrs: {},
            contentWindow: { location: { replace(url) { element(id).workspaceUrl = url; } } },
            addEventListener() {}, removeAttribute(key) { delete this.attrs[key]; if (key === 'src') delete this.src; },
            replaceChildren() {} });
        return elements.get(id);
    };
    let hashchange;
    const context = {
        PlatformAccess: { currentAccess: { permissions }, requirePermission: async () => true },
        AuthStorage: { getToken: () => 'test-only', clear() {} },
        document: { getElementById: element, querySelectorAll: () => [] },
        location: { hash }, history: { replaceState(a, b, value) { context.location.hash = value; } },
        addEventListener(event, fn) { if (event === 'hashchange') hashchange = fn; },
        fetch: async () => { throw new Error('offline test'); }, Intl, console
    };
    context.window = context;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/admin-overview.js'), 'utf8'), context);
    await new Promise(resolve => setImmediate(resolve));
    return { element, context, navigate(value) { context.location.hash = value; hashchange(); } };
}

(async () => {
    const app = await shell(['data_view', 'user_manage', 'system_config'], '#users');
    assert.equal(app.element('platform-workspace').workspaceUrl, '/admin_users.html?embedded=1');
    assert.equal(app.element('platform-workspace').title, '账号管理');
    assert.equal(app.element('overview-content').hidden, true);
    assert.equal(app.element('workspace-content').hidden, false);
    app.navigate('#agents');
    assert.equal(app.element('platform-workspace').workspaceUrl, '/admin_agents.html?embedded=1');
    app.navigate('#overview');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(app.element('workspace-content').hidden, true);
    assert.equal(app.element('overview-content').hidden, false);
    assert.equal(app.element('platform-workspace').workspaceUrl, 'about:blank');
    assert.equal(app.element('total_sales').textContent, '—');
    assert.match(app.element('overview-status').textContent, /刷新重试/);
    const restricted = await shell(['user_manage'], '#agents');
    assert.equal(restricted.context.location.hash, '#users');
    assert.equal(restricted.element('platform-workspace').workspaceUrl, '/admin_users.html?embedded=1');
    restricted.navigate('#constructor');
    assert.equal(restricted.context.location.hash, '#users');
    const agent = await shell(['system_config'], '');
    assert.equal(agent.context.location.hash, '#agents');
    console.log('PASS: embedded workspace routing, permission fallback and overview error state');
})().catch(error => { console.error(error); process.exitCode = 1; });
