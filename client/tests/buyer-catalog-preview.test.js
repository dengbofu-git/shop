// node client/tests/buyer-catalog-preview.test.js [isolated-catalog.json]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const model = require('../static/js/buyer-catalog-model.js');
class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.attrs = {}; this.events = {}; }
    appendChild(item) { this.children.push(item); return item; }
    replaceChildren(...items) { this.children = items; }
    setAttribute(key, value) { this.attrs[key] = value; }
    addEventListener(key, fn) { this.events[key] = fn; }
    querySelectorAll(tag) { return this.children.filter(item => item.tag === tag); }
    querySelector(tag) { return this.querySelectorAll(tag)[0]; }
}
const source = fs.readFileSync(require.resolve('../static/js/buyer-catalog-preview.js'), 'utf8');
function category(id, count) { return {catalog_id: id, catalog_name: 'Tea ' + id,
    sku: Array.from({length: count}, (_, i) => ({skuid: id * 100 + i + 1, image_url: '/tea.png'}))}; }
const fixture = process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2])) : {code: 200, data: [category(1, 22), category(2, 21), category(3, 20), category(4, 15), category(5, 10), category(6, 15)]};
async function main() {
    let response = fixture, failure = false, rows;
    const nodes = Object.fromEntries(['tabs', 'grid', 'error', 'retry', 'empty'].map(key => [key, new Element('div')]));
    const context = {window: {BuyerCatalogModel: model}, document: {createElement: tag => new Element(tag)},
        fetch: async () => { if (failure) throw Error('offline'); return {ok: true, json: async () => response}; }};
    vm.runInNewContext(source, context);
    const control = context.window.BuyerCatalogPreview.start({...nodes, url: '/index', labels: () => ({grid_retry: 'Retry'}),
        render: value => { rows = value; nodes.empty.style.display = rows.length ? 'none' : 'block'; }});
    const tick = () => new Promise(resolve => setImmediate(resolve));
    await tick();
    assert.equal(rows.length, 10); assert.equal(new Set(rows.map(row => row.skuid)).size, 10);
    const eligible = model.normalize(fixture.data).filter(cat => cat.rows.length);
    assert.equal(nodes.tabs.children.length, eligible.length);
    nodes.tabs.children.forEach((link, index) => {
        assert.equal(link.tag, 'a');
        assert.equal(link.href, 'buyer_products.html?catalog_id=' + eligible[index].id);
        assert(link.querySelector('img').src);
    });
    assert.equal(new Set(rows.map(row => row.catalog_id)).size, Math.min(10, eligible.length));
    const initial = rows.map(row => row.skuid); control.setLanguage();
    assert.deepEqual(rows.map(row => row.skuid), initial, 'language must not reselect products');
    failure = true; await nodes.retry.events.click();
    assert.equal(nodes.error.style.display, 'block'); assert.equal(nodes.retry.hidden, false);
    failure = false; response = {code: 200, data: []}; await nodes.retry.events.click();
    assert.equal(rows.length, 0); assert.equal(nodes.empty.style.display, 'block');
    response = {code: 200, data: [category(9, 3)]}; await nodes.retry.events.click();
    assert.equal(rows.length, 3, 'never pad a small catalog with fake products');
    console.log('PASS: ten unique balanced homepage picks, category deep links, language retention, empty/error/retry and small catalogs');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
