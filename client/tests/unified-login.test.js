// Run with node client/tests/unified-login.test.js; no browser or business DB.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../static/js', name), 'utf8');

function loginHarness() {
    let request, submit;
    const button = { disabled: false, textContent: '' };
    const result = { textContent: '' };
    const fields = { username: { value: 'merchant001' }, password: { value: 'synthetic-only' }, showResult: result };
    fields['login-form'] = { addEventListener: (event, fn) => { submit = fn; }, querySelector: () => button };
    const context = {
        document: { documentElement: {}, body: { classList: { toggle() {} } },
            querySelectorAll: () => [], querySelector: () => null, getElementById: id => fields[id] },
        localStorage: { getItem: () => null, setItem() {} }, location: { href: '' },
        AuthStorage: { token: null, clear() { this.token = null; }, setToken(token) { this.token = token; },
            setCount() {}, setUser() {}, setShop() {}, setUserType() {} }
    };
    context.window = context;
    context.$ = function (target) {
        if (typeof target === 'function') { target(); return; }
        const wrapper = { text(value) { target.textContent = value; return wrapper; },
            empty() { target.textContent = ''; return wrapper; }, addClass() { return wrapper; }, removeClass() { return wrapper; } };
        return wrapper;
    };
    context.$.ajax = options => { request = options; };
    vm.runInNewContext(source('login-portal.js'), context);
    return { context, button, result, submit: () => { submit({ preventDefault() {} }); return request; } };
}

async function main() {
    for (const destination of ['/merchant_dashboard.html', '/buyer_dashboard.html', '/admin_panel.html', '/admin_users.html', '/admin_agents.html']) {
        const app = loginHarness();
        const request = app.submit();
        const payload = JSON.parse(request.data);
        assert.equal(payload.username, 'merchant001');
        assert.equal('selectedRole' in payload, false);
        assert.equal('expected_user_type' in payload, false);
        assert.equal(app.button.disabled, true);
        request.success({ code: 200, token: 'synthetic-token', redirect_url: destination });
        assert.equal(app.context.location.href, destination);
        assert.equal(app.context.AuthStorage.token, 'synthetic-token');
    }
    for (const destination of ['https://example.test', '//example.test', '/unexpected.html', null]) {
        const app = loginHarness();
        app.submit().success({ code: 200, token: 'must-not-save', redirect_url: destination });
        assert.equal(app.context.location.href, '');
        assert.equal(app.context.AuthStorage.token, null);
        assert.equal(app.button.disabled, false);
    }
    for (const fail of ['business', 'network']) {
        const app = loginHarness(), request = app.submit();
        if (fail === 'business') request.success({ code: 10006, error: 'No workspace' });
        else request.error({ responseJSON: { error: 'Network unavailable' } });
        assert.equal(app.context.AuthStorage.token, null);
        assert.equal(app.button.disabled, false);
        assert.ok(app.result.textContent);
    }
    {
        const app = loginHarness();
        app.submit().success({ code: 200, token: 'old-backend-token' });
        assert.equal(app.context.location.href, '');
        assert.equal(app.context.AuthStorage.token, null);
        assert.equal(app.button.disabled, false);
        assert.match(app.result.textContent, /重启后端/);
    }
    for (const access of [
        { roles: ['supplier'], permissions: ['user_manage'], redirect_url: '/merchant_dashboard.html' },
        { roles: ['super_admin'], permissions: ['system_config'], redirect_url: '/admin_agents.html' },
        { roles: ['super_admin'], permissions: ['user_manage'], redirect_url: '/admin_panel.html' }
    ]) {
        const context = { location: { replace(url) { this.destination = url; } },
            AuthStorage: { getToken: () => 'synthetic-token', clear() {} },
            document: { body: { style: { visibility: 'hidden' } }, querySelectorAll: () => [] },
            fetch: async () => ({ status: 200, ok: true, json: async () => access }) };
        context.window = context;
        vm.runInNewContext(source('platform-access.js'), context);
        const allowed = await context.PlatformAccess.requirePermission('user_manage');
        assert.equal(allowed, access.roles.includes('super_admin') && access.permissions.includes('user_manage'));
        assert.equal(context.document.body.style.visibility, allowed ? 'visible' : 'hidden');
        if (!allowed) assert.equal(context.location.destination, access.redirect_url);
        const anyAllowed = await context.PlatformAccess.requirePermission(['data_view', 'user_manage', 'system_config']);
        assert.equal(anyAllowed, access.roles.includes('super_admin') && access.permissions.some(code => ['data_view', 'user_manage', 'system_config'].includes(code)));
        if (anyAllowed) assert.equal(context.PlatformAccess.currentAccess, access);
    }
    console.log('PASS: login routing, destination allowlist, error recovery and platform initialization guards');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
