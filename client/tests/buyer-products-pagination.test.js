// Run: node client/tests/buyer-products-pagination.test.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/buyer-products.js'), 'utf8');
const functions = source.slice(source.indexOf('    function rowsForSelection('), source.indexOf('    function loadRecommended('));
let nextId = 1;
const groups = [23, 20, 20, 15, 10, 15].map((count, index) => ({catalog_id: index + 1, catalog_name: 'Tea ' + index,
    sku: Array.from({length: count}, () => ({skuid: nextId++}))}));
const rows = groups.flatMap(cat => cat.sku);
const nodes = new Map();
let available = groups, requestedCatalog = null, fetchCount = 0;
function $(selector) {
    if (typeof selector === 'function') { selector(); return; }
    if (typeof selector === 'object') return selector;
    if (!nodes.has(selector)) nodes.set(selector, {
        content: '', visible: true, events: {}, classes: {},
        html(value) { this.content = value; return this; },
        hide() { this.visible = false; return this; }, show() { this.visible = true; return this; },
        off() { this.events = {}; return this; },
        on(event, selector, fn) { this.events[event] = fn || selector; return this; },
        text(value) { this.content = value; return this; },
        each() { return this; },
        toggleClass(name, enabled) { this.classes[name] = enabled; return this; }
    });
    return nodes.get(selector);
}
$.get = (url, callback) => {
    assert.equal(new URL(url).pathname, '/v1/goods/index', 'never depend on legacy 12-item category pages');
    fetchCount++;
    callback({code: 200, data: available});
    return {fail() { return this; }};
};
const context = {$, baseUrl: 'http://fixture', catalogs: [], currentCatalogId: 'all', currentPage: 1, PAGE_SIZE: 10,
    pageMax: 1, baseUrlMedia: '', t: key => key === 'page_summary' ? '{start}-{end}/{total}' : key,
    getUrlParam: () => requestedCatalog, history: {replaceState() {}}, Set,
    renderProductCard: row => '[' + row.skuid + ']'};
vm.runInNewContext(functions, context);
const seen = [];
context.loadCatalogs();
assert.equal(context.currentCatalogId, 'all');
assert($('#category-tabs').content.includes('data-catalog-id="all" aria-pressed="true"'));
assert.equal(context.pageMax, 11);
assert.equal($('#procurement-summary').content, '1-10/103');
for (let page = 1; page <= 11; page++) {
    const count = page === 11 ? 3 : 10;
    assert.equal(context.currentPage, page);
    const ids = [...$('#product-grid').content.matchAll(/\[(\d+)\]/g)].map(match => Number(match[1]));
    assert.equal(ids.length, count);
    seen.push(...ids);
    assert.equal($('#pager-prev').classes.disabled, page === 1);
    assert.equal($('#pager-next').classes.disabled, page === 11);
    if (page < 11) $('#pager-next').events.click();
}
assert.equal(seen.length, new Set(seen).size);
assert.deepEqual(seen.slice().sort((a, b) => a - b), rows.map(row => row.skuid));
assert.equal(fetchCount, 1, 'paging reuses complete grouped catalog');
$('#pager-next').events.click();
assert.equal(context.currentPage, 11, 'cannot advance past last page');
$('#pager-prev').events.click();
assert.equal(context.currentPage, 10);
$('#pager-nums .pager-num').events.click.call({data: () => 1});
assert.equal(context.currentPage, 1);
function selectCategory(id) { $('#category-tabs').events['click.catalogTab'].call({data: () => id}); }
selectCategory(1);
assert.equal(context.currentPage, 1, 'category resets to first page');
assert.equal(context.pageMax, 3);
assert.equal($('#procurement-summary').content, '1-10/23');
context.loadProducts(3);
assert.equal([...$('#product-grid').content.matchAll(/\[(\d+)\]/g)].length, 3);
selectCategory('all');
assert.equal(context.currentPage, 1);
assert.equal(context.pageMax, 11);
requestedCatalog = '2'; context.loadCatalogs();
assert.equal(context.currentCatalogId, 2, 'category deep link preserved');
assert.equal(context.pageMax, 2);
requestedCatalog = '999'; context.loadCatalogs();
assert.equal(context.currentCatalogId, 'all', 'invalid category defaults to all');
available = [{catalog_id: 1, sku: rows.slice(0, 3)}]; context.loadCatalogs();
assert.equal($('#pager-wrap').visible, false, 'single page hides pager');
available = []; context.loadCatalogs();
assert.equal($('#pager-wrap').visible, false, 'empty category hides pager');
console.log('PASS: all 103 products across 11 pages of 10; single categories, deep links, totals, no omissions/duplicates and empty state');

// Execute the complete page script and its real HTML renderer, optionally with a
// fresh response produced by catalog-preview-contract.py in isolated SQLite.
nodes.clear();
const contract = process.argv[2] ? JSON.parse(fs.readFileSync(process.argv[2], 'utf8')) : {code: 200, data: groups};
let language = 'zh';
$.get = (url, callback) => {
    const pathname = new URL(url).pathname;
    assert(['/v1/goods/index', '/v1/goods/recommended-products'].includes(pathname));
    callback(pathname === '/v1/goods/index' ? contract : {code: 200, data: []});
    return {fail() { return this; }};
};
const pageContext = {$, baseUrl: 'http://fixture', Set, history: {replaceState() {}},
    localStorage: {getItem: () => language, setItem: (key, value) => {language = value;}},
    document: {querySelectorAll: () => []}, window: {location: {search: ''}}};
vm.runInNewContext(source, pageContext);
const expected = contract.data.flatMap(cat => cat.sku.map(row => Number(row.skuid)));
const rendered = [];
const totalPages = Math.ceil(expected.length / 10);
for (let page = 1; page <= totalPages; page++) {
    const html = $('#product-grid').content;
    const ids = [...html.matchAll(/class="product-card" data-skuid="(\d+)"/g)].map(match => Number(match[1]));
    assert.equal(ids.length, Math.min(10, expected.length - (page - 1) * 10));
    rendered.push(...ids);
    if (page < totalPages) $('#pager-next').events.click();
}
assert.equal(new Set(rendered).size, expected.length);
assert.deepEqual(rendered.slice().sort((a, b) => a - b), expected.slice().sort((a, b) => a - b));
const lastPageHtml = $('#product-grid').content;
$('#lang-switch .lang-btn').events.click.call({data: () => 'en'});
assert.equal($('#procurement-summary').content, 'Showing ' + ((totalPages - 1) * 10 + 1) + '\u2013' + expected.length + ' of ' + expected.length + ' products');
assert.deepEqual([...$('#product-grid').content.matchAll(/data-skuid="(\d+)"/g)].map(match => match[1]),
    [...lastPageHtml.matchAll(/data-skuid="(\d+)"/g)].map(match => match[1]), 'language change keeps current page');
assert($('#category-tabs').content.includes('All Products'));
console.log('PASS: complete page script renders ' + expected.length + ' actual SKU cards in pages of 10; language retains page and all-category tab');
