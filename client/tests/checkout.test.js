// node client/tests/checkout.test.js -- no network, DB, order creation or payment.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const utils = require('../static/js/checkout-utils.js');
const items = ['75.00', '28.11', '60.00', '24.40'].map((price, i) => ({
    id: i + 1, name: 'Tea ' + i, price, count: 1, sku_sale_attr_name: [], sku_sale_attr_val: []
}));
assert.deepEqual(utils.summary(items, 'USD'), {count: 4, cents: 18751});
assert.equal(utils.format(18751, 'USD'), '$187.51');
assert.equal(utils.cents('1.005'), 101);
for (const invalid of ['NaN', 'Infinity', '-1', '<script>', '']) assert.throws(() => utils.cents(invalid));
for (const invalid of [0, -1, 0.5, NaN, Infinity]) assert.throws(() => utils.quantity(invalid));
const original = JSON.stringify(items);
for (const currency of ['USD', 'AED', 'SAR', 'USD']) {
    const sum = utils.summary(items, currency);
    assert.equal(sum.cents, items.reduce((total, item) => total + utils.line(item, currency), 0));
    assert.equal(sum.count, 4);
}
assert.equal(JSON.stringify(items), original);
assert.equal(utils.currency('__proto__'), 'USD');
assert.equal(utils.summary([{price: '0.01', count: 3}, {price: '0.01', count: 3}], 'AED').cents, 22);
assert.equal(utils.summary([{price: '1', count: 3}], 'USD').count, 3);
assert.equal(utils.request('').get('settlement_type'), '0');
assert.equal(utils.request('?currency=AED').get('settlement_type'), '0');
assert.equal(utils.request('?sku_id=12&buy_num=3').get('settlement_type'), '1');
assert.throws(() => utils.request('?sku_id=12'));
assert.throws(() => utils.request('?sku_id=12&buy_num=-1'));
const payment = new URL('http://test/' + utils.payment({type: 1, sku: '12', count: '3'}, 9));
assert.deepEqual(Object.fromEntries(payment.searchParams), {address_id: '9', settlement_type: '1', buy_count: '3', sku_id: '12'});

async function ui(saved, blocked = false, empty = false, noAddress = false) {
    const nodes = new Map(); let ready; let calls = 0;
    function element(tag = 'div') {
        return {tag, children: [], textContent: '', value: '', events: {},
            append(...children) { this.children.push(...children); }, appendChild(child) { this.children.push(child); return child; },
            replaceChildren() { this.children = []; }, addEventListener(type, fn) { this.events[type] = fn; },
            showModal() {}, close() {} };
    }
    function get(id) { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); }
    const data = {sku_list: empty ? [] : JSON.parse(original), addresses: noAddress ? [] : [
        {id: 1, name: 'One', mobile: 'synthetic', address: 'Test road 1'},
        {id: 2, name: 'Two', mobile: 'synthetic', address: 'Test road 2'}
    ]};
    const context = {CheckoutUtils: utils, URLSearchParams, baseUrl: '',
        document: {getElementById: get, createElement: element, querySelectorAll: () => [get('currency-label')],
            addEventListener(event, callback) { ready = callback; }},
        AuthStorage: {getToken: () => 'synthetic', getUser: () => 'buyer', clear() {}},
        localStorage: {getItem() { if (blocked) throw Error('blocked'); return saved; }, setItem() { if (blocked) throw Error('blocked'); }},
        location: {search: '', href: ''}, fetch: async (url, options) => {
            calls++; assert.equal(options.method, undefined, 'preview/currency must only read');
            return {ok: true, status: 200, json: async () => ({code: 200, data, base_url: '/media/'})};
        }};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/orderconfirm.js'), 'utf8'), context);
    ready();
    await new Promise(resolve => setImmediate(resolve));
    const initialCalls = calls;
    if (!noAddress) get('checkout-addresses').children[1].children[0].events.change();
    for (const code of ['AED', 'SAR', 'USD']) {
        get('currency-select').value = code;
        get('currency-select').events.change();
        assert.equal(get('checkout-total').textContent, utils.format(utils.summary(data.sku_list, code).cents, code));
        if (!noAddress) assert.ok(get('checkout-delivery').textContent.includes('Test road 2'));
        assert.equal(calls, initialCalls, 'currency switch performs no API or address save');
    }
    if (empty || noAddress) assert.equal(get('go_pay').disabled, true);
    else {
        assert.equal(get('go_pay').disabled, false);
        get('go_pay').events.click();
        assert.equal(context.location.href, 'payment.html?address_id=2&settlement_type=0');
        assert.equal(get('count').textContent, 4);
    }
}
Promise.all([ui('AED'), ui('SAR', true), ui('USD', false, true), ui('USD', false, false, true)]).then(() => {
    console.log('PASS: exact amounts, currency cycles, address preservation, empty state and unchanged payment parameters');
}).catch(error => { console.error(error); process.exitCode = 1; });
