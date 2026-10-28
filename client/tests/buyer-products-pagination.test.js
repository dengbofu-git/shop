// node client/tests/buyer-products-pagination.test.js [isolated-catalog.json]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const model = require('../static/js/buyer-catalog-model.js');
let id = 0;
const groups = [22, 21, 20, 15, 10, 15].map((count, index) => ({catalog_id: index + 1, catalog_name: 'Tea ' + index,
    sku: Array.from({length: count}, () => ({skuid: ++id, name: '250g', spu_name: 'Tea ' + id, price: String(id * 10),
        stock: id, merchant: {id: id % 2 + 1, name: id % 2 ? 'East' : 'West'}}))}));
const cats = model.normalize(groups);
const state = model.read('');
const seen = [];
for (let page = 1; page <= 11; page++) {
    const result = model.query(cats, {...state, page});
    assert.equal(result.rows.length, page === 11 ? 3 : 10);
    seen.push(...result.rows.map(row => row.skuid));
}
assert.equal(new Set(seen).size, 103); assert.equal(seen.length, 103);
assert.equal(model.query(cats, {...state, page: 999}).page, 11);
assert.equal(model.query(cats, {...state, catalog_id: '2'}).total, 21);
let query = model.read('?q=250g&min_price=14&max_price=28&min_stock=12&merchant_id=1&sort=price_desc&page=4&currency=USD');
let result = model.query(cats, query);
assert.deepEqual(result.rows.map(row => row.skuid), [20, 18, 16, 14, 12]);
assert.equal(result.page, 1);
assert.deepEqual(model.read(model.search(query)), query, 'URL round trip retains every filter and currency');
assert.equal(model.query(cats, model.read('?q=west')).total, 51);
assert.equal(model.query(cats, model.read('?min_price=14&max_price=14')).rows[0].skuid, 10, 'inclusive price bounds use displayed USD amount');
assert.equal(model.query(cats, model.read('?q=no-such-product')).total, 0);
assert.equal(model.read('?min_price=-1&max_price=Infinity&currency=invalid&page=-5').currency, 'USD');
assert.equal(model.read('?min_price=-1').min_price, '');

// Execute the real page controller, including generated cards, events and browser history.
class Node {
    constructor(tag = 'div') { this.tag = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.events = {}; this.value = ''; this.hidden = false;
        this.classList = {toggle: () => {}}; }
    appendChild(child) { this.children.push(child); return child; }
    replaceChildren(...children) { this.children = children; }
    setAttribute(key, value) { this.attrs[key] = value; }
    addEventListener(key, fn) { this.events[key] = fn; }
    setCustomValidity(message) { this.invalid = message; }
    reportValidity() { return !nodes['filter-max_price'].invalid; }
    scrollIntoView() { this.scrolled = true; }
    querySelector() { return this.children.find(item => item.attrs['aria-current'] === 'page'); }
    focus() { this.focused = true; }
}
const template = fs.readFileSync(require.resolve('../templates/buyer_products.html'), 'utf8');
const nodes = Object.fromEntries([...template.matchAll(/id="([^"]+)"/g)].map(match => [match[1], new Node()]));
['currency-select', 'search-input', 'lang-switch'].forEach(key => { nodes[key] = new Node(); });
const doc = {getElementById: key => { assert(nodes[key], key); return nodes[key]; }, createElement: tag => new Node(tag), querySelectorAll: () => [], events: {},
    addEventListener(key, fn) { this.events[key] = fn; }};
let language = 'zh', fetchCount = 0, fail = false;
const ready = [];
const win = {BuyerCatalogModel: model, location: {search: '?page=2', href: 'http://fixture/buyer_products.html?page=2'}, scrollY: 0, events: {},
    addEventListener(key, fn) { this.events[key] = fn; }, requestAnimationFrame: fn => fn(), scrollTo: (x, y) => {win.scrollY = y;} };
function navigate(url) { const target = new URL(url, win.location.href); win.location.href = target.href; win.location.search = target.search; }
const history = {state: {procurementScrollY: 420}, entries: [],
    replaceState(value, title, url) { this.state = value; navigate(url); },
    pushState(value, title, url) { this.entries.push({url: win.location.href, state: this.state}); this.state = value; navigate(url); }};
const contract = process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2])) : {code: 200, data: groups};
const context = {window: win, document: doc, history, URLSearchParams, baseUrl: 'http://fixture',
    localStorage: {getItem: () => language}, $: fn => ready.push(fn),
    fetch: async () => { fetchCount++; if (fail) throw Error('offline'); return {ok: true, json: async () => contract}; }};
vm.runInNewContext(fs.readFileSync(require.resolve('../static/js/buyer-products.js'), 'utf8'), context);
const tick = () => new Promise(resolve => setImmediate(resolve));
function cards() { return nodes['product-grid'].children; }
function pageButton(label) { return nodes['procurement-pagination'].children.find(item => item.textContent === label); }
async function main() {
    ready.forEach(fn => fn()); await tick();
    assert.equal(win.scrollY, 420, 'async catalog restores saved viewport after render');
    assert.equal(cards().length, 10); assert(new URL(win.location.href).searchParams.get('page') === '2');
    const sample = cards()[0];
    const sampleRow = contract.data.flatMap(cat => cat.sku).find(row => String(row.skuid) === String(sample.dataset.skuid));
    assert.equal(sample.children.find(item => item.className === 'product-name').children[0].textContent,
        sampleRow.spu_name || sampleRow.product_name || sampleRow.name, 'title uses product name rather than specification');
    assert.equal(sample.children.find(item => item.className === 'product-stock').textContent, '库存 ' + sampleRow.stock + ' 件');
    const expected = model.interleave(model.normalize(contract.data)).map(row => String(row.skuid)).sort();
    navigate('/buyer_products.html'); history.state = {}; win.events.popstate();
    const actual = [];
    do {
        actual.push(...cards().map(card => String(card.dataset.skuid)));
        const next = pageButton(language === 'zh' ? '下一页' : 'Next');
        if (!next || next.disabled) break;
        next.events.click();
    } while (true);
    assert.deepEqual(actual.sort(), expected);
    assert.equal(fetchCount, 1, 'filters and pages reuse the complete catalog');
    const pageBeforeLanguage = win.location.search;
    language = 'en'; nodes['lang-switch'].events.click({target: {closest: () => true}});
    assert.equal(win.location.search, pageBeforeLanguage);
    doc.events['buyer:catalog-search']({detail: 'missing fixture product'});
    assert.equal(cards().length, 0); assert.equal(nodes['procurement-empty'].hidden, false);
    nodes['procurement-reset'].events.click(); assert.equal(cards().length, 10);
    nodes['filter-min_price'].value = '100'; nodes['filter-max_price'].value = '20';
    nodes['procurement-filters'].events.submit.call(nodes['procurement-filters'], {preventDefault() {}});
    assert(nodes['filter-max_price'].invalid);
    navigate('/buyer_products.html?catalog_id=2&page=2&sort=price_desc&q=250g');
    history.state = {procurementScrollY: 690}; win.events.popstate();
    assert.equal(nodes['filter-sort'].value, 'price_desc'); assert.equal(nodes['filter-q'].value, '250g');
    assert.equal(win.scrollY, 690);
    win.scrollY = 777; win.events.pagehide(); assert.equal(history.state.procurementScrollY, 777);
    nodes['currency-select'].value = 'AED'; nodes['currency-select'].events.change.call(nodes['currency-select']);
    assert.equal(new URL(win.location.href).searchParams.get('currency'), 'AED');
    assert.equal(nodes['filter-min_price'].value, '');
    fail = true; await nodes['procurement-retry'].events.click();
    assert.equal(nodes['procurement-error'].hidden, false); assert.equal(nodes['procurement-fields'].disabled, true);
    assert.equal(nodes['product-grid'].attrs['aria-busy'], 'false');
    fail = false; await nodes['procurement-retry'].events.click();
    assert.equal(nodes['procurement-error'].hidden, true); assert.equal(nodes['procurement-fields'].disabled, false);
    console.log('PASS: 103-item coverage, compound filters, inclusive display-price bounds, sorting, deep links, real page rendering, language, empty state and history/scroll restoration');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
