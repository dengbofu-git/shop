// Run: node client/tests/merchant-orders.test.js [isolated-response.json]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const api = require('../static/js/merchant-orders.js');
const fixture = [1, 2, 3, 4].map(status => ({order_id: String(status), status, total_amount: '35',
    order_type: 'standard', can_ship: status === 2, can_delete: status === 1,
    status_text: ['', '待付款', '待发货', '待收货', '订单完成'][status]}));
fixture.push({order_id: 'trial', status: 4, status_text: '试用中'},
    {order_id: 'presale', status: 1, status_text: '待付定金'});
const count = (state, name) => state.tabs.find(t => t.name === name).count;
const tick = () => new Promise(resolve => setImmediate(resolve));

async function main() {
    assert.equal(api.statusOf({status: 4}), '已完成');
    assert.equal(api.statusOf({status: 4, status_text: '试用中'}), '试用中');
    assert.equal(api.statusOf({status: null}), '未知状态');
    assert.equal(api.initialFilter('?embed=1&filter=unshipped'), '待发货');
    assert.equal(api.initialFilter('?filter=4'), '已完成');
    assert.equal(api.initialFilter(''), '全部');
    const html = api.rowsHtml([{...fixture[0], order_id: '\"><script>x</script>', receiver: '<img onerror=x>', address: '&"\''}]);
    assert(!html.includes('<script>') && !html.includes('<img'));
    assert(html.includes('&lt;img onerror=x&gt;') && html.includes('&amp;&quot;&#39;'));
    assert(html.includes('￥35.00') && html.includes('scope="col"'));
    assert(!api.rowsHtml([fixture[2]]).includes('data-action='));
    assert(api.rowsHtml([fixture[1]]).includes('data-action="ship"'));
    assert(api.rowsHtml([{order_id:'trial-ship',status:null,status_text:'待发货',can_ship:true,can_delete:false}]).includes('data-action="ship"'));
    assert(!api.rowsHtml([{order_id:'mixed',status:2,can_ship:false,can_delete:false,requires_merchant_split:true}]).includes('data-action='));
    let subtypeCalls=[];
    const subtypeController=api.createController({render:()=>{},confirm:()=>true,notify:()=>{},
        request:async function(action,id) { subtypeCalls.push([action,id]);return {code:200,data:[
            {order_id:'trial-ship',status:null,status_text:'待发货',can_ship:true,can_delete:false}]}; }});
    await subtypeController.load();
    await subtypeController.act('ship','trial-ship');
    assert(subtypeCalls.some(call=>call[0]==='ship'),'Subtype action follows authenticated API flag, not null base status');

    let state, server = structuredClone(fixture), calls = [], failList = false, failAction = false, allowDelete = true;
    const controller = api.createController({initial: '待发货', render: value => state = value,
        confirm: () => allowDelete, notify: () => {}, request: async (action, id) => {
            calls.push([action, id]);
            if (action === 'list') {
                if (failList) throw new Error('offline');
                return {code: 200, data: structuredClone(server)};
            }
            if (failAction) return {code: 400, error: '库存不足'};
            if (action === 'ship') Object.assign(server.find(o => o.order_id === id), {status: 3, status_text: '待收货'});
            else Object.assign(server.find(o => o.order_id === id), {status: 0, status_text: '已关闭', can_delete: false});
            return {code: 200};
        }});
    await controller.load();
    assert.deepEqual(state.orders.map(o => o.order_id), ['2']);
    assert.equal(count(state, '全部'), 6);
    assert.equal(count(state, '已完成'), 1);
    assert.equal(count(state, '试用中'), 1);
    assert.equal(count(state, '待付定金'), 1);
    await controller.act('ship', '2');
    assert.equal(state.active, '待发货');
    assert.equal(state.orders.length, 0);
    assert.equal(count(state, '待收货'), 2);
    assert.equal(count(state, '待发货'), 0);
    controller.select('已完成');
    allowDelete = false;
    const before = calls.length;
    await controller.act('delete', '4');
    assert.equal(calls.length, before);
    allowDelete = true;
    await controller.act('delete', '4');
    assert.equal(state.orders.length, 1);
    assert.equal(count(state, '已完成'), 1);
    assert.equal(count(state, '全部'), 6);
    await controller.act('delete', '3'); // Unavailable action never sent.
    assert.equal(calls.at(-1)[0], 'list');
    controller.select('待付款');
    failAction = true;
    await controller.act('delete', '1');
    assert.equal(state.error, '库存不足');
    assert.equal(count(state, '待付款'), 1);
    failAction = false; failList = true;
    await controller.load();
    assert.equal(state.error, 'offline');
    assert.equal(state.orders.length, 1); // Retain previous data after reload failure.
    failList = false; await controller.load();
    assert.equal(state.error, '');
    controller.select('试用中');
    await controller.act('delete', 'trial');
    assert.equal(state.active, '试用中');
    assert.equal(count(state, '试用中'), 1); // Subtypes cannot be cancelled through the standard route.
    controller.select('待付款');
    await controller.act('delete', '1');
    assert.equal(count(state, '已关闭'), 1);
    assert.equal(count(state, '全部'), 6);
    assert.equal(count(state, '待付款'), 0);
    server = []; await controller.load(); controller.select('全部');
    assert.equal(state.orders.length, 0);
    assert.equal(state.total, 0);

    let resolveList, last, actions = 0;
    const pending = api.createController({render: value => last = value, confirm: () => true, notify: () => {},
        request: action => { actions++; return new Promise(resolve => { resolveList = resolve; }); }});
    const first = pending.load();
    await pending.load(); await pending.act('ship', '2');
    assert.equal(actions, 1);
    pending.select('待收货');
    resolveList({code: 200, data: structuredClone(fixture)}); await first;
    assert.equal(last.active, '待收货'); assert.equal(last.orders.length, 1);

    // Exercise mounted DOM event routing and the actual AJAX adapter.
    class Element {
        constructor() { this.handlers = {}; this.dataset = {}; this.attrs = {}; this.buttons = []; }
        set innerHTML(value) {
            this.html = value;
            this.buttons = [...value.matchAll(/<button[^>]*data-(status|action)="([^"]*)"[^>]*>/g)].map(match => {
                const button = new Element(); button.dataset[match[1]] = match[2];
                button.dataset.orderId = /data-order-id="([^"]*)"/.exec(match[0])?.[1];
                return button;
            });
        }
        querySelectorAll() { return this.buttons; }
        addEventListener(name, fn) { this.handlers[name] = fn; }
        setAttribute(name, value) { this.attrs[name] = value; }
        contains(button) { return this.buttons.includes(button); }
        closest() { return this; }
        after() {} focus() { this.focused = true; }
        click(target) { this.handlers.click({target, preventDefault() {}}); }
    }
    const elements = Object.fromEntries(['order-list', 'order-status-filters', 'order-summary', 'btn-logout'].map(id => [id, new Element()]));
    const ajax = [], history = [];
    let cleared = false;
    const win = {document: {getElementById: id => elements[id], createElement: () => new Element()},
        location: {search: '?embed=1&filter=unshipped', href: 'http://fixture/merchant_orders.html?embed=1&filter=unshipped'},
        history: {replaceState: (...args) => history.push(String(args[2]))},
        AuthStorage: {getToken: () => 'fixture-token', clear: () => { cleared = true; }},
        jQuery: {ajax: options => ajax.push(options)}, baseUrl: 'http://fixture', alert() {}, confirm: () => true};
    const mounted = api.mount(win);
    assert.equal(ajax[0].url, 'http://fixture/v1/supplier/orders');
    assert.equal(ajax[0].headers.Authorization, 'fixture-token');
    ajax[0].success({code: 200, data: structuredClone(fixture)}); await tick();
    assert(elements['order-list'].html.includes('data-action="ship"'));
    elements['order-list'].click(elements['order-list'].buttons[0]);
    assert.equal(ajax[1].url, 'http://fixture/v1/supplier/orders/2/ship');
    assert.equal(ajax[1].type, 'POST');
    assert.equal(elements['order-list'].buttons[0].disabled, true);
    ajax[1].success({code: 200}); await tick();
    assert.equal(ajax[2].type, 'GET');
    ajax[2].success({code: 200, data: []}); await tick();
    assert(elements['order-list'].html.includes('暂无“待发货”订单'));
    const all = elements['order-status-filters'].buttons[0];
    elements['order-status-filters'].click(all);
    assert(history[0].includes('embed=1') && !history[0].includes('filter='));
    elements['btn-logout'].click(); assert(cleared);
    assert.equal(win.location.href, 'login.html');
    assert(mounted);
    if (process.argv[2]) {
        const response = JSON.parse(fs.readFileSync(process.argv[2] === '-' ? 0 : process.argv[2], 'utf8'));
        assert.equal(api.categories(response.data)[0].count, response.data.length);
        assert.equal(api.categories(response.data).find(t => t.name === '试用中').count, 1);
        assert.equal(api.categories(response.data).find(t => t.name === '待付尾款').count, 1);
        assert.equal(api.categories(response.data).find(t => t.name === '已完成').count, 1);
        assert(response.data.length > 12);
    }
    console.log('PASS: category counts, subtype labels, filter links, ship/delete refresh, errors/retry, concurrent guards, escaping and mounted AJAX/events');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
