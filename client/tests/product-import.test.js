/* Service boundary and accidental-write guards in the actual page controller. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
class Element {
    constructor() { this.listeners = {}; this.children = []; this.checked = false; this.disabled = false; this.hidden = false; this.files = []; this.dataset = {}; this.textContent = ''; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    fire(name, event = {}) { if (this.listeners[name]) return this.listeners[name](event); }
    appendChild(node) { this.children.push(node); return node; }
    replaceChildren() { this.children = []; }
    setAttribute(name, value) { this[name] = value; }
    showModal() { this.open = true; }
    close() { this.open = false; }
    click() { this.fire('click'); }
    remove() {}
}
const ids = ['product-import-dialog', 'btn-product-import', 'import-message', 'import-file', 'import-preview', 'import-close',
    'import-reload', 'import-template-xlsx', 'import-template-csv', 'import-commit', 'import-confirmed', 'import-rows',
    'import-errors-only', 'import-review', 'import-summary', 'import-view-products', 'import-page', 'import-prev', 'import-next'];
function setup(url = 'http://localhost/merchant_products.html?mode=create') {
    const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
    const callbacks = {}, calls = [], replies = [];
    let auth = 'fixture-token';
    const location = {href: url};
    const Url = class extends URL {};
    Url.createObjectURL = () => 'blob:fixture'; Url.revokeObjectURL = () => {};
    const document = {getElementById: id => elements[id], createElement: () => new Element(), body: new Element(),
        addEventListener: (name, fn) => { callbacks[name] = fn; }};
    const AuthStorage = {getToken: () => auth};
    const window = {AuthStorage, location, history: {replaceState: (_, __, value) => { location.href = String(value); }},
        crypto, setTimeout: () => 1, clearTimeout: () => {}};
    const context = {window, document, AuthStorage, URL: Url, Uint8Array, AbortController,
        FormData: class { constructor() { this.fields = {}; } append(key, value) { this.fields[key] = value; } },
        fetch: async (path, options) => { calls.push({path, options}); const reply = replies.shift();
            if (!reply) throw new Error('Missing fixture reply'); return reply(); }};
    vm.runInNewContext(fs.readFileSync('client/static/js/product-import.js', 'utf8'), context);
    callbacks.DOMContentLoaded();
    return {elements, calls, replies, setToken: value => { auth = value; }, location};
}
function job(count = 2, errors = false) {
    return {id: '12345678-1234-4234-8234-123456789abc', filename: '茶品.csv', status: errors ? 'invalid' : 'ready',
        expired: false, row_count: count, valid_count: errors ? 0 : count, error_count: errors ? count : 0,
        review_digest: 'a'.repeat(64), rows: Array.from({length: count}, (_, i) => ({row_number: i + 2,
            data: {name: '<img src=x onerror=alert(1)>', sku_name: '150g', catalog: '红茶', brand: '', price: '38.00',
                market_price: '38.00', stock: 10, caption: '花果香'}, errors: errors ? ['售价错误'] : []})), result: {}};
}
function reply(data, status = 200) { return async () => ({ok: status === 200, json: async () => status === 200 ? {code: 200, data} : {code: status, error: data}}); }
async function flush() { for (let i = 0; i < 15; i++) await Promise.resolve(); }
async function preview(app, data = job()) {
    app.elements['import-file'].files = [{name: '茶品.csv', size: 100}];
    app.elements['import-file'].fire('change');
    app.replies.push(reply(data)); app.elements['import-preview'].click(); await flush();
}
async function main() {
    let app = setup(), el = app.elements;
    el['btn-product-import'].click();
    assert.equal(el['product-import-dialog'].open, true);
    await preview(app);
    assert.equal(app.calls.length, 1, 'upload alone never commits');
    assert.equal(el['import-commit'].disabled, true, 'explicit checkbox required');
    assert.equal(el['import-rows'].children[0].children[1].textContent, '<img src=x onerror=alert(1)>');
    assert.equal(el['import-rows'].children[0].children[1].children.length, 0, 'cell content is never HTML');
    assert.equal(el['import-rows'].children[0].children[4].textContent, '38.00 / 38.00', 'display selling and market prices only');
    assert(!Object.keys(app.calls[0].options.body.fields).includes('merchant_id'));
    el['import-confirmed'].checked = true; el['import-confirmed'].fire('change');
    assert.equal(el['import-commit'].disabled, false);
    const done = {...job(), status: 'committed', result: {spu_count: 1, sku_count: 2}};
    app.replies.push(reply(done)); el['import-commit'].click(); await flush();
    assert.deepEqual(JSON.parse(app.calls[1].options.body), {review_digest: 'a'.repeat(64)});
    assert.equal(el['import-view-products'].hidden, false);
    assert.equal(el['import-commit'].disabled, true);
    el['import-commit'].click(); await flush(); assert.equal(app.calls.length, 2);
    console.log('PASS: preview/confirmation boundary, literal cells, one immutable commit and success receipt');

    app = setup(); el = app.elements;
    await preview(app, job(2, true));
    el['import-confirmed'].checked = true; el['import-confirmed'].fire('change');
    el['import-commit'].click(); await flush();
    assert.equal(app.calls.length, 1, 'invalid rows block all writes');
    assert.equal(el['import-confirmed'].disabled, true);
    await preview(app, job(27));
    assert.equal(el['import-rows'].children.length, 25);
    el['import-next'].click(); assert.equal(el['import-rows'].children.length, 2);
    el['import-errors-only'].checked = true; el['import-errors-only'].fire('change');
    assert.equal(el['import-rows'].children[0].children[0].textContent, '没有错误行');
    el['import-file'].fire('change');
    assert.equal(el['import-review'].hidden, true);
    assert.equal(el['import-commit'].disabled, true);
    console.log('PASS: invalid batch, paging/filter and new-file invalidation');

    app = setup(); el = app.elements;
    el['import-file'].files = [{name: '茶品.csv', size: 100}];
    app.replies.push(async () => { throw new Error('temporary network failure'); });
    el['import-preview'].click(); await flush();
    const key = app.calls[0].options.body.fields.request_key;
    app.replies.push(reply(job())); el['import-preview'].click(); await flush();
    assert.equal(app.calls[1].options.body.fields.request_key, key, 'uncertain upload retry retains idempotency key');
    assert.equal(el['import-commit'].disabled, true);

    app = setup(); el = app.elements;
    el['import-file'].files = [{name: '茶品.csv', size: 100}];
    let resolve;
    app.replies.push(() => new Promise(r => { resolve = r; }));
    el['import-preview'].click(); await flush();
    assert.equal(el['import-file'].disabled, true);
    let prevented = false;
    el['product-import-dialog'].fire('cancel', {preventDefault() { prevented = true; }});
    assert(prevented, 'prevent closing during in-flight work');
    app.setToken('another-account');
    resolve(await reply(job())()); await flush();
    assert.equal(el['import-rows'].children.length, 0, 'late old-account data must not render');
    assert(el['import-message'].textContent.includes('账号已变化'));
    console.log('PASS: uncertain upload retry, in-flight guard and account isolation');

    app = setup(); el = app.elements;
    await preview(app, {...job(), review_digest: 'not-a-valid-digest'});
    assert.equal(el['import-review'].hidden, true);
    assert.equal(el['import-commit'].disabled, true);
    assert(el['import-message'].textContent.includes('预览格式异常'));
    console.log('PASS: malformed preview is rejected without enabling confirmation');

    app = setup(); el = app.elements;
    await preview(app, {...job(), needs_reupload: true});
    el['import-confirmed'].checked = true; el['import-confirmed'].fire('change');
    el['import-commit'].click(); await flush();
    assert.equal(app.calls.length, 1);
    assert.equal(el['import-commit'].disabled, true);
    assert(el['import-message'].textContent.includes('模板已更新'));
    console.log('PASS: obsolete previews require a new upload');

    app = setup('http://localhost/merchant_products.html?mode=create&import_job=12345678-1234-4234-8234-123456789abc');
    await flush();
    assert.equal(app.calls.length, 1);
    assert(app.calls[0].path.endsWith('12345678-1234-4234-8234-123456789abc'));
    console.log('PASS: page refresh restores through the authenticated job service');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
