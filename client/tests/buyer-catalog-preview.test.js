// Run: node client/tests/buyer-catalog-preview.test.js (no dependencies or business DB).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../static/js/buyer-catalog-preview.js'), 'utf8');
class Element {
    constructor(tag) {
        this.tag = tag; this.children = []; this.style = {}; this.dataset = {}; this.attrs = {};
        this.events = {}; this.className = ''; this.hidden = false; this.textContent = '';
        this.classList = { toggle: (name, on) => {
            const names = new Set(this.className.split(' ').filter(Boolean));
            if (on) names.add(name); else names.delete(name);
            this.className = [...names].join(' ');
        } };
    }
    setAttribute(name, value) { this.attrs[name] = value; }
    appendChild(node) { this.children.push(node); }
    replaceChildren() { this.children = []; }
    querySelectorAll(tag) { return this.children.filter(child => child.tag === tag); }
    addEventListener(name, callback) { this.events[name] = callback; }
    click() { if (!this.disabled) return this.events.click(); }
    focus() { this.focused = true; }
    scrollIntoView() { this.scrolled = true; }
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function setup(response) {
    const context = { window: {}, document: {createElement: tag => new Element(tag)}, fetch: async () => response() };
    vm.runInNewContext(script, context);
    const elements = Object.fromEntries(['tabs', 'grid', 'summary', 'error', 'retry', 'empty', 'viewAll', 'pager', 'section'].map(name => [name, new Element('div')]));
    const lang = {tea_all: '全部', tea_black: '红茶', tea_green: '绿茶', grid_summary: '{start}-{end}/{total}',
        grid_retry: '重试', grid_loading: '加载', grid_prev: '上一页', grid_next: '下一页', grid_pagination: '商品分页'};
    let rows = [];
    const controller = context.window.BuyerCatalogPreview.start({
        ...elements, url: '/v1/goods/index', labels: () => lang,
        render: value => { rows = value; elements.empty.style.display = value.length ? 'none' : 'block'; }
    });
    return {elements, controller, context, lang, get rows() { return rows; }};
}
function response(data) { return {ok: true, json: async () => ({code: 200, data})}; }
function category(id, name, count) {
    return {catalog_id: id, catalog_name: name, sku: Array.from({length: count}, (_, i) => ({skuid: id * 100 + i + 1, spu_name: name + i}))};
}
function control(page, kind, target) {
    const found = page.elements.pager.children.find(button => button.tag === 'button' && button.dataset.kind === kind &&
        (target === undefined || Number(button.dataset.page) === target));
    assert.ok(found, 'pagination control must exist: ' + kind + ' ' + target);
    return found;
}
function collectPages(page) {
    const ids = page.rows.map(row => row.skuid);
    let pages = 1;
    while (!control(page, 'next').disabled) {
        control(page, 'next').click(); pages++;
        assert.ok(pages < 1000, 'pagination must terminate');
        assert.ok(page.rows.length > 0 && page.rows.length <= 10);
        ids.push(...page.rows.map(row => row.skuid));
    }
    return {ids, pages};
}
async function main() {
    const data = [category(7, '红茶', 16), category(19, '绿茶', 14)];
    const page = setup(() => response(data));
    await tick();
    assert.deepEqual(page.elements.tabs.children.map(b => b.dataset.catalogId), ['all', '7', '19']);
    assert.equal(page.rows.length, 10);
    assert.equal(page.rows.filter(row => row.catalog_id === 7).length, 5);
    assert.equal(page.rows.filter(row => row.catalog_id === 19).length, 5);
    assert.equal(page.elements.summary.textContent, '1-10/30');
    const initialIds = page.rows.map(row => row.skuid);
    assert.equal(control(page, 'previous').disabled, true);
    control(page, 'next').click();
    assert.equal(page.elements.summary.textContent, '11-20/30');
    assert.ok(page.rows.every(row => !initialIds.includes(row.skuid)));
    assert.equal(control(page, 'number', 2).attrs['aria-current'], 'page');
    assert.equal(control(page, 'number', 2).focused, true);
    assert.equal(page.elements.section.scrolled, true);
    control(page, 'number', 3).click();
    assert.equal(page.elements.summary.textContent, '21-30/30');
    assert.equal(control(page, 'next').disabled, true);
    control(page, 'next').click();
    assert.equal(page.elements.summary.textContent, '21-30/30');
    control(page, 'previous').click();
    assert.equal(page.elements.summary.textContent, '11-20/30');
    page.elements.tabs.children[2].click();
    assert.equal(page.rows.length, 10);
    assert.equal(page.elements.summary.textContent, '1-10/14');
    assert.ok(page.rows.every(row => row.catalog_id === 19));
    assert.equal(page.rows[0].skuid, 1914);
    assert.equal(page.elements.viewAll.href, 'buyer_products.html?catalog_id=19');
    assert.equal(page.elements.tabs.children[2].attrs['aria-pressed'], 'true');
    assert.equal(page.elements.tabs.children[0].attrs['aria-pressed'], 'false');
    control(page, 'next').click();
    assert.equal(page.rows.length, 4);
    assert.equal(page.elements.summary.textContent, '11-14/14');
    assert.ok(page.rows.every(row => row.catalog_id === 19));
    page.lang.tea_green = 'Green'; page.lang.grid_prev = 'Previous'; page.controller.setLanguage();
    assert.equal(page.elements.tabs.children[2].textContent, 'Green (14)');
    assert.equal(control(page, 'previous').textContent, 'Previous');
    assert.equal(control(page, 'number', 2).attrs['aria-current'], 'page');
    assert.ok(page.rows.every(row => row.catalog_id === 19));
    page.elements.tabs.children[0].click();
    assert.equal(page.elements.viewAll.href, 'buyer_products.html');
    assert.deepEqual(Array.from(page.rows, row => row.skuid), Array.from(initialIds));

    // Match the reported 103-product catalog: every item must be reachable exactly once.
    const largeData = [22, 21, 20, 15, 10, 15].map((count, i) => category(i + 1, 'Tea-' + i, count));
    const large = setup(() => response(largeData));
    await tick();
    const allExpected = largeData.flatMap(cat => cat.sku.map(row => row.skuid));
    assert.ok(control(large, 'number', 11));
    const traversed = collectPages(large);
    assert.equal(traversed.pages, 11);
    assert.equal(large.rows.length, 3);
    assert.equal(large.elements.summary.textContent, '101-103/103');
    assert.equal(new Set(traversed.ids).size, 103);
    assert.deepEqual([...traversed.ids].sort((a, b) => a - b), allExpected.sort((a, b) => a - b));
    control(large, 'number', 1).click();
    assert.equal(large.elements.summary.textContent, '1-10/103');
    large.elements.tabs.children[5].click();
    assert.equal(large.rows.length, 10);
    assert.equal(control(large, 'previous').disabled, true);
    assert.equal(control(large, 'next').disabled, true);

    const empty = setup(() => response([category(4, '新茶类', 0)]));
    await tick(); empty.elements.tabs.children[1].click();
    assert.equal(empty.rows.length, 0);
    assert.equal(empty.elements.empty.style.display, 'block');
    assert.equal(empty.elements.error.style.display, 'none');
    assert.equal(empty.elements.tabs.children[1].textContent, '新茶类 (0)');
    assert.equal(empty.elements.pager.hidden, true);
    assert.equal(empty.elements.pager.children.length, 0);

    let failed = true;
    const retry = setup(() => { if (failed) throw new Error('offline'); return response(data); });
    await tick();
    assert.equal(retry.elements.error.style.display, 'block');
    assert.equal(retry.elements.retry.hidden, false);
    assert.equal(retry.elements.grid.attrs['aria-busy'], 'false');
    assert.equal(retry.elements.pager.hidden, true);
    failed = false; await retry.elements.retry.click();
    assert.equal(retry.elements.error.style.display, 'none');
    assert.equal(retry.elements.retry.hidden, true);
    assert.equal(retry.rows.length, 10);

    const invalid = setup(() => ({ok: true, json: async () => ({code: 500, data: []})}));
    await tick();
    assert.equal(invalid.elements.retry.hidden, false);
    assert.equal(invalid.elements.error.style.display, 'block');
    if (process.argv[2]) {
        const actual = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
        const contract = setup(() => response(actual.data));
        await tick();
        for (let i = 0; i < actual.data.length; i++) {
            const cat = actual.data[i];
            contract.elements.tabs.children[i + 1].click();
            assert.equal(contract.rows.length, Math.min(10, cat.sku.length));
            assert.ok(contract.rows.every(row => String(row.catalog_id) === String(cat.catalog_id)));
            const ids = new Set(cat.sku.map(row => row.skuid));
            assert.ok(contract.rows.every(row => ids.has(row.skuid)));
            assert.equal(contract.elements.viewAll.href, 'buyer_products.html?catalog_id=' + cat.catalog_id);
            const traversedCategory = collectPages(contract);
            assert.equal(traversedCategory.ids.length, ids.size);
            assert.equal(new Set(traversedCategory.ids).size, ids.size);
            assert.ok(traversedCategory.ids.every(id => ids.has(id)));
        }
        contract.elements.tabs.children[0].click();
        const allContract = collectPages(contract);
        const expectedCount = actual.data.reduce((sum, cat) => sum + cat.sku.length, 0);
        assert.equal(allContract.ids.length, expectedCount);
        assert.equal(new Set(allContract.ids).size, expectedCount);
        console.log('PASS: Django catalog response consumed by actual preview script; every category contains only its own SKU IDs');
    }
    console.log('PASS: 10-item pages; all 103 items reachable exactly once over 11 pages; category reset, last page, navigation, language retention, empty/error states and retry');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
