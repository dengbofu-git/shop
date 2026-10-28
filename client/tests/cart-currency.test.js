// Run: node client/tests/cart-currency.test.js (no browser, network or business DB).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/cart.js'), 'utf8');

function harness(authenticated, savedCurrency, blockedStorage = false) {
    const rows = [
        {id: '1', unit_price: 10, price: 20, count: 2, selected: true, name: 'Tea'},
        {id: '2', unit_price: 3, price: 3, count: 1, selected: false, name: 'Other tea'}
    ];
    const storage = {cart: JSON.stringify(rows), buyer_cart_currency: savedCurrency};
    const nodes = new Map(), requests = [];
    function $(target) {
        if (typeof target === 'function') { target(); return; }
        if (typeof target === 'object') return target;
        if (!nodes.has(target)) {
            const node = {value: '', content: '', props: {}, events: {},
                on(event, selector, fn) { this.events[event + (fn ? ':' + selector : '')] = fn || selector; return this; },
                val(value) { if (value === undefined) return this.value; this.value = value; return this; },
                text(value) { this.content = String(value); return this; },
                html(value) { this.content = value; return this; },
                empty() { this.content = ''; return this; },
                append(value) { this.content += value; return this; },
                prop(key, value) { if (value === undefined) return this.props[key]; this.props[key] = value; return this; },
                toggle() { return this; }, show() { return this; }, hide() { return this; }
            };
            nodes.set(target, node);
        }
        return nodes.get(target);
    }
    $.ajax = options => {
        requests.push(options);
        assert.equal(options.type, 'GET', 'currency switching must not mutate the server cart');
        return {done(fn) { fn({code: 200, data: JSON.parse(JSON.stringify(rows))}); return this; }, fail() { return this; }};
    };
    const context = {TeaMoney:require('../static/js/currency.js'),$, AuthStorage: {getUser: () => authenticated ? 'buyer' : '', getToken: () => 'synthetic', setCount() {}},
        localStorage: {
            getItem(key) { if (blockedStorage && key !== 'cart') throw Error('blocked'); return storage[key] || null; },
            setItem(key, value) { if (blockedStorage) throw Error('blocked'); storage[key] = value; }
        }, location: {href: ''}, alert: message => { throw Error(message); }};
    vm.runInNewContext(source, context);
    return {rows, storage, requests, $, switchTo(currency) {
        const select = $('#currency-select'); select.value = currency; select.events.change.call(select);
    }};
}

for (const authenticated of [false, true]) {
    const app = harness(authenticated);
    const original = JSON.stringify(app.rows);
    const initialRequests = app.requests.length;
    assert.equal(app.$('.susum,.susumOne').content, '¥20.00');
    for (const [currency, unit, line, total] of [
        ['AED', 'AED 5.10', 'AED 10.20', 'AED 10.20'],
        ['SAR', 'SAR 5.20', 'SAR 10.40', 'SAR 10.40'],
        ['USD', '$1.40', '$2.80', '$2.80'],
        ['AED', 'AED 5.10', 'AED 10.20', 'AED 10.20']
    ]) {
        app.switchTo(currency);
        const html = app.$('#cart_imfor').content;
        assert(html.includes('>' + unit + '</p>'), 'unit price converts');
        assert(html.includes('>' + line + '</span>'), 'row subtotal converts');
        assert.equal(app.$('.susum,.susumOne').content, total, 'only selected items contribute');
        assert.equal(app.$('[data-cart-currency]').content, currency);
        assert.equal(app.$('.total,.totalOne').content, '1');
        assert.equal(app.storage.buyer_cart_currency, currency);
        assert.equal(app.requests.length, initialRequests, 'no API calls when changing currency');
    }
    assert.equal(JSON.stringify(app.rows), original, 'raw data stays unchanged');
    assert.equal(app.storage.cart, original, 'display conversion is never stored in cart prices');
    app.switchTo('__proto__');
    assert.equal(app.$('#currency-select').value, 'CNY');
    assert.equal(app.$('.susum,.susumOne').content, '¥20.00');
}

const remembered = harness(true, 'SAR');
assert.equal(remembered.$('#currency-select').value, 'CNY');
assert.equal(remembered.storage.buyer_cart_currency, 'CNY');
assert.equal(remembered.$('.susum,.susumOne').content, '¥20.00');
const blocked = harness(true, 'AED', true);
blocked.switchTo('AED');
assert.equal(blocked.$('.susum,.susumOne').content, 'AED 10.20');
const guest = harness(false, 'AED');
assert.equal(guest.$('#currency-select').value, 'CNY');
guest.switchTo('AED');
guest.$('#allcheck').props.checked = true;
guest.$('#allcheck').events.change.call(guest.$('#allcheck'));
assert.equal(guest.$('.susum,.susumOne').content, 'AED 11.73', 'selection update preserves active currency');
const add = {closest: () => ({data: () => '1'}), hasClass: name => name === 'add'};
guest.$('#cart_imfor').events['click:.reduc,.add'].call(add);
assert.equal(guest.$('.susum,.susumOne').content, 'AED 16.83', 'quantity update preserves active currency');
assert.equal(JSON.parse(guest.storage.cart)[0].unit_price, 10);
console.log('PASS: guest/server cart currency, headers, totals, selection, quantity, persistence and raw-price integrity');

for (const oldCurrency of ['USD', 'EUR', 'SAR', 'AED', 'invalid']) {
    const page = harness(true, oldCurrency);
    assert.equal(page.$('#currency-select').value, 'CNY');
    assert.equal(page.$('.susum,.susumOne').content, '¥20.00');
}
