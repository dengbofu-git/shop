// node client/tests/auth-storage.test.js -- synthetic per-tab browser storage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/auth-storage.js'), 'utf8');
function storage() {
    const values = new Map();
    return { getItem: key => values.has(key) ? values.get(key) : null,
        setItem: (key, value) => values.set(key, String(value)), removeItem: key => values.delete(key) };
}
const shared = storage();
function tab(session = storage()) {
    const context = { sessionStorage: session, localStorage: shared };
    vm.runInNewContext(source, context);
    return { auth: context.AuthStorage, session };
}
function login(auth, name, type) {
    auth.clear(); auth.setToken(name + '-synthetic-token'); auth.setUser(name);
    auth.setUserType(type); auth.setShop(name + '-shop'); auth.setCount(3);
}
const merchant = tab(), buyer = tab();
login(merchant.auth, 'merchant001', 'merchant');
login(buyer.auth, 'buyer001', 'customer');
assert.equal(merchant.auth.getUser(), 'merchant001');
assert.equal(buyer.auth.getUser(), 'buyer001');
assert.equal(shared.getItem('tea_saas_token'), null);
// Simulate an old, cached tab still writing the former global auth keys.
shared.setItem('tea_saas_token', 'buyer001-synthetic-token');
shared.setItem('tea_saas_user', 'buyer001');
shared.setItem('tea_saas_user_type', 'customer');
assert.equal(merchant.auth.getUser(), 'merchant001');
const newTab = tab();
assert.equal(newTab.auth.getToken(), null);
assert.equal(newTab.auth.getUser(), null);
assert.equal(newTab.auth.getUserType(), null);
const refreshed = tab(merchant.session), iframe = tab(merchant.session);
assert.equal(refreshed.auth.getUser(), 'merchant001');
assert.equal(iframe.auth.getToken(), 'merchant001-synthetic-token');
merchant.auth.clear();
assert.equal(iframe.auth.getToken(), null);
assert.equal(merchant.auth.getUser(), null);
assert.equal(buyer.auth.getToken(), 'buyer001-synthetic-token');
assert.equal(shared.getItem('tea_saas_token'), 'buyer001-synthetic-token');
buyer.auth.clear();
assert.equal(shared.getItem('tea_saas_token'), null);
assert.equal(buyer.auth.getUser(), null);
assert.equal(newTab.auth.getToken(), null); // logout never resurrects a shared login
console.log('PASS: two-account isolation, blank tabs, refresh, iframe session and independent logout');
