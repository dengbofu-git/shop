// Run: node client/tests/cart-currency.test.js (no browser, network or business DB).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/cart.js'), 'utf8');

function harness(authenticated, savedCurrency, blockedStorage = false, suppliedRows) {
    const rows = suppliedRows || [
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
for (const authenticated of [false, true]) {
    for (const oldCurrency of ['USD', 'EUR', 'SAR', 'AED', 'invalid']) {
        const page = harness(authenticated, oldCurrency);
        assert.equal(page.$('#currency-select').value, 'CNY');
        assert.equal(page.$('.susum,.susumOne').content, '¥20.00');
    }
}
assert.equal(harness(true, 'SAR', true).$('#currency-select').value, 'CNY');
console.log('PASS: CNY entry default, stale/blocked storage, manual currency switching, totals, quantity and raw-price integrity');

for (const authenticated of [false, true]) {
    const original = [{id:'1', name:'Tea', count:99, selected:true, unit_price:10, available_stock:50}];
    const page = harness(authenticated, 'SAR', false, original);
    assert(page.$('#cart_imfor').content.includes('value="99"'), 'short stock preserves intended quantity');
    assert(page.$('#cart_imfor').content.includes('当前仅 50 件可售'), 'short stock has an explicit message');
    assert.equal(page.$('.susum,.susumOne').content, '¥990.00');
    assert.equal(original[0].count, 99, 'render never changes the cart quantity');
}
const overNine = harness(false, 'CNY', false, [{id:'1', name:'Tea', count:9, selected:true, unit_price:10, available_stock:100}]);
overNine.$('#cart_imfor').events['click:.reduc,.add'].call({closest:()=>({data:()=> '1'}),hasClass:()=>true});
assert.equal(JSON.parse(overNine.storage.cart)[0].count, 10, 'available stock can be selected above nine');

for (const authenticated of [false, true]) {
    const rows = [
        {id: '23', name: '默认规格', sku_name: '默认规格', product_name: '石牌茶', unit_price: 75, count: 1},
        {id: '24', name: '英红9号', product_name: '英红9号', unit_price: 123, count: 1},
        {id: '130', name: '陈香寿眉 100g', product_name: '陈香寿眉', unit_price: 66, count: 1,
            sku_sale_attr_name: ['净含量'], sku_sale_attr_val: ['100g']},
        {id: '131', name: '礼盒装', spu_name: '红茶', unit_price: 50, count: 1},
        {id: '132', name: '旧缓存商品', unit_price: 10, count: 1},
        {id: '133', product_name: '<img src=x onerror=alert(1)>', name: '<规格>', unit_price: 10, count: 1}
    ];
    const page = harness(authenticated, 'CNY', false, rows);
    const original = JSON.stringify(rows);
    function checkNames() {
        const html = page.$('#cart_imfor').content;
        assert(html.includes('<span class="des">石牌茶</span>'));
        assert(!html.includes('默认规格'), 'placeholder specification must not replace the product title');
        assert(html.includes('<span class="des">英红9号</span>'));
        assert(html.includes('<span class="des">陈香寿眉</span>'));
        assert(html.includes('<span>净含量：</span><span>100g</span>'));
        assert(html.includes('规格：礼盒装'));
        assert(html.includes('<span class="des">旧缓存商品</span>'), 'legacy guest data remains readable');
        assert(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
        assert(html.includes('规格：&lt;规格&gt;'));
        assert(!html.includes('<img src=x'));
    }
    checkNames();
    page.switchTo('USD'); checkNames();
    page.switchTo('CNY'); checkNames();
    assert.equal(JSON.stringify(rows), original, 'display names never change SKU identity or prices');
    if (!authenticated) {
        const add = {closest: () => ({data: () => '23'}), hasClass: name => name === 'add'};
        page.$('#cart_imfor').events['click:.reduc,.add'].call(add);
        checkNames();
        const stored = JSON.parse(page.storage.cart)[0];
        assert.equal(stored.id, '23'); assert.equal(stored.product_name, '石牌茶');
        assert.equal(stored.unit_price, 75); assert.equal(stored.count, 2);
    }
}
console.log('PASS: SPU titles, default/meaningful specifications, guest compatibility, escaping and redraws');
