// Run: node client/tests/operations-dashboard.test.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/operations-dashboard.js'), 'utf8');
const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const fixture = value => ({summary: {total_sales_display: value, paid_order_count: 2, order_count: 3,
    completion_rate: 50, completed: 1, pending_ship: 1, unpaid: 1, in_transit: 0, avg_order_amount: 5, inventory_turnover_days: 7},
    sales_basis: 'fixture only', monthly: [], categories: [], regions: [], funnel: [], aux: {}});
const response = data => ({ok: true, json: async () => ({code: 200, data})});
function setup() {
    class Element {
        constructor(id) { this.id = id; this.attrs = {}; this.events = {}; this.children = []; this.textContent = ''; this.hidden = false; }
        addEventListener(type, fn) { this.events[type] = fn; }
        event(type, value = {}) { this.events[type]?.call(this, value); }
        setAttribute(key, value) { this.attrs[key] = value; }
        replaceChildren() { this.children = []; }
        appendChild(el) { this.children.push(el); }
        remove() { this.removed = true; }
    }
    const elements = new Map(), el = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
    const chartIds = ['chart-sales-trend','chart-order-status','chart-map','chart-category','chart-funnel'];
    const ids = ['sales-basis','m-total-sales','m-order-count','m-completion-rate','m-completed','m-pending-ship','m-unpaid',
        'm-in-transit','m-avg-order','m-turnover','m-turnover-display','aux-partners','aux-roi','aux-warehouse','aux-score'];
    const head = new Element('head'), requests = [], timers = new Map(), idle = [], events = {}, charts = [];
    let sequence = 0, failChart = '';
    const doc = {readyState: 'complete', documentElement: {}, head, getElementById: el,
        createElement: () => new Element(), querySelectorAll: selector => selector.startsWith('.core-metrics') ?
            [el('core'), el('aux')] : ids.filter(id => id !== 'sales-basis').map(el)};
    const win = {addEventListener(type, fn) { events[type] = fn; },
        setTimeout(fn, ms) { const id = ++sequence; timers.set(id, {fn, ms}); return id; }, clearTimeout(id) { timers.delete(id); },
        requestAnimationFrame(fn) { fn(); }, requestIdleCallback(fn) { idle.push(fn); }, location: {replace() {}}};
    const context = {window: win, document: doc, Promise, AbortController,
        getComputedStyle: () => ({getPropertyValue: () => ''}),
        AuthStorage: {getToken: () => 'fixture'}, baseUrl: 'http://fixture',
        fetch(url, options) { return new Promise((resolve, reject) => requests.push({url, options, resolve, reject})); }};
    Object.defineProperty(context, 'echarts', {get: () => win.echarts});
    vm.runInNewContext(source, context);
    function library() {
        win.echarts = {getInstanceByDom: dom => charts.findLast(c => c.dom === dom && !c.disposed), init(dom) {
            const chart = {dom, disposed: false, setOption() { if (dom.id === failChart) throw Error('chart failed'); },
                dispose() { this.disposed = true; }, resize() {}};
            charts.push(chart); return chart;
        }};
        head.children.at(-1).onload();
    }
    async function runIdle() { while (idle.length) { idle.shift()(); await flush(); } }
    async function timer(ms) {
        const entry = [...timers].find(([, task]) => task.ms === ms); assert(entry, 'missing timer ' + ms);
        timers.delete(entry[0]); entry[1].fn(); await flush();
    }
    return {win, doc, elements, el, head, requests, timers, idle, events, charts, chartIds, library, runIdle, timer,
        fail(id) { failChart = id; }};
}
async function main() {
    let app = setup();
    assert.equal(app.requests.length, 1, 'API starts while the local chart library is still unresolved');
    assert.equal(app.head.children[0].async, true);
    assert.equal(app.head.children[0].src, '/static/vendor/echarts/5.4.3/echarts.min.js', 'use same-origin library before any CDN');
    app.requests[0].resolve(response(fixture('¥35.00'))); await flush();
    assert.equal(app.el('m-total-sales').textContent, '¥35.00', 'metrics render before chart library');
    assert.equal(app.el('core').attrs['aria-busy'], 'false');
    assert.equal(app.charts.length, 0);
    app.library(); await flush();
    assert.equal(app.head.children.length, 1, 'local success must not request any external CDN');
    assert.equal(app.idle.length, 5);
    await app.runIdle(); assert.equal(app.charts.length, 5);
    assert.equal(app.el('retry-dashboard').hidden, true);
    // Refresh twice while old idle jobs are pending; only the latest response renders.
    app.el('time-filter').value = 'month'; app.el('time-filter').event('change');
    app.requests[1].resolve(response(fixture('old month'))); await flush();
    app.el('time-filter').value = 'quarter'; app.el('time-filter').event('change');
    app.requests[2].resolve(response(fixture('latest quarter'))); await flush();
    await app.runIdle();
    assert.equal(app.el('m-total-sales').textContent, 'latest quarter');
    assert.equal(app.charts.filter(c => !c.disposed).length, 5);
    assert(app.requests[2].url.endsWith('period=quarter'));
    app.el('time-filter').value = 'year'; app.el('time-filter').event('change');
    app.el('time-filter').value = 'month'; app.el('time-filter').event('change');
    assert(app.requests[3].options.signal.aborted);
    app.requests[4].resolve(response(fixture('new month'))); await flush();
    app.requests[3].resolve(response(fixture('stale year'))); await flush();
    await app.runIdle(); assert.equal(app.el('m-total-sales').textContent, 'new month');
    // A chart error does not discard metrics or other chart instances; retry uses cached data.
    app.fail('chart-map'); app.el('refresh-data').event('click');
    app.requests.at(-1).resolve(response(fixture('partial'))); await flush(); await app.runIdle();
    assert.equal(app.el('m-total-sales').textContent, 'partial');
    assert.equal(app.el('retry-dashboard').hidden, false);
    const before = app.requests.length;
    app.fail(''); app.el('retry-dashboard').event('click'); await flush(); await app.runIdle();
    assert.equal(app.requests.length, before);
    assert.equal(app.el('retry-dashboard').hidden, true);
    app.events.pagehide(); assert(app.charts.every(c => c.disposed));
    app.events.pageshow({persisted: true}); assert.equal(app.requests.length, before + 1);

    app = setup(); app.library(); await flush();
    app.requests[0].reject(Error('offline')); await flush();
    assert.equal(app.charts.length, 0, 'failed API must never be drawn as zero sales');
    assert.equal(app.el('retry-dashboard').hidden, false);
    app.el('retry-dashboard').event('click');
    app.requests[1].resolve(response(fixture('retry ok'))); await flush(); await app.runIdle();
    assert.equal(app.el('m-total-sales').textContent, 'retry ok');

    app = setup();
    app.requests[0].resolve(response(fixture('library offline'))); await flush();
    await app.timer(5000); // Local timeout falls back without blocking statistics.
    assert.equal(app.head.children.length, 2);
    assert(app.head.children.at(-1).src.includes('cdn.bootcdn.net'));
    app.head.children.at(-1).onerror(); await flush();
    assert.equal(app.head.children.length, 3);
    assert(app.head.children.at(-1).src.includes('cdn.jsdelivr.net'));
    app.head.children.at(-1).onerror(); await flush();
    assert.equal(app.el('m-total-sales').textContent, 'library offline');
    assert.equal(app.el('retry-dashboard').hidden, false);
    app.el('retry-dashboard').event('click');
    app.library(); await flush(); await app.runIdle();
    assert.equal(app.requests.length, 1, 'library retry must not repeat the analytics request');
    assert.equal(app.charts.length, 5);

    app = setup();
    app.head.children[0].onerror(); await flush();
    assert.equal(app.head.children.length, 2);
    app.library();
    app.requests[0].resolve(response(fixture('fallback works'))); await flush(); await app.runIdle();
    assert.equal(app.charts.length, 5, 'CDN still recovers when the local asset is missing');
    assert.equal(app.head.children.length, 2, 'successful fallback does not request further sources');

    app = setup(); app.library(); await flush();
    await app.timer(12000);
    assert(app.requests[0].options.signal.aborted);
    assert.equal(app.el('retry-dashboard').hidden, false);
    assert(app.el('dashboard-load-status').textContent.includes('超时'));
    app.requests[0].resolve(response(fixture('too late'))); await flush();
    assert.notEqual(app.el('m-total-sales').textContent, 'too late');
    console.log('PASS: local-first charts without CDN on success; fallback/retry, parallel API, early metrics, five deferred charts, stale-period/idle guards, abort/disposal and bfcache restore');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
