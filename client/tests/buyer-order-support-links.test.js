// Exercise the real buyer order page with synthetic authenticated list responses.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(require.resolve('../static/js/buyer-orders.js'), 'utf8');
const token = letter => 'os-' + letter.repeat(64);
const fixture = [
    {order_id:'synthetic-first',support_reference:token('a'),status:1,order_time:'2026-10-26 10:00',order_sku:[],order_total_amount:'40'},
    {order_id:'synthetic-second',support_reference:token('b'),status:4,order_time:'2026-10-25 10:00',order_sku:[],order_total_amount:'80'}
];

function page(hash) {
    const records = new Map(), events = {}, requests = [];
    function node(key) {
        if (!records.has(key)) records.set(key, {value:'',markup:'',textValue:'',events:{},hidden:false,
            on(event, selector, handler) {this.events[event] = handler || selector;return this;},
            val(value) {if(arguments.length){this.value=value;return this;}return this.value;},
            html(value) {this.markup=value;return this;}, text(value) {this.textValue=value;return this;},
            append(value) {this.markup+=value;return this;}, removeClass(){return this;},addClass(){return this;}});
        return records.get(key);
    }
    const win = {location:{hash,pathname:'/buyer_orders.html',search:''},
        addEventListener(name, handler){events[name]=handler;},
        history:{replaceState(state,title,url){win.location.hash='';win.location.changed=url;}}};
    function $(selector) {if(typeof selector==='function'){selector();return;}return typeof selector==='string'?node(selector):selector;}
    $.ajax = options => {requests.push(options);return {done(handler){handler({code:200,data:{orders_list:fixture}});return this;},fail(){return this;}};};
    const document = {getElementById:id=>node('#'+id)};
    vm.runInNewContext(source, {window:win,document,$,
        AuthStorage:{getUser:()=> 'synthetic-buyer',getToken:()=> 'synthetic-token'},
        TeaMoney:{format:value=>'¥'+value,currency:value=>value},confirm:()=>true,alert(){}});
    return {node,win,events,requests};
}

test('a support link opens the exact order and allows returning to all orders',()=>{
    const p=page('#support-order='+token('b'));
    assert(p.node('#bo-list').markup.includes('synthetic-second'));
    assert(!p.node('#bo-list').markup.includes('synthetic-first'));
    assert.equal(p.node('#bo-count').textValue,'共 1 笔订单');
    assert.equal(p.node('#bo-all-orders').hidden,false);
    assert.equal(p.requests[0].headers.Authorization,'synthetic-token');
    p.node('#bo-all-orders').events.click();
    assert.equal(p.node('#bo-count').textValue,'共 2 笔订单');
    assert(p.node('#bo-list').markup.includes('synthetic-first'));
    assert.equal(p.win.location.hash,'');
    assert.equal(p.node('#bo-all-orders').hidden,true);
});

test('an inaccessible, hidden or foreign reference never falls back to a different order',()=>{
    const p=page('#support-order='+token('c'));
    assert(p.node('#bo-list').markup.includes('这笔订单当前不可查看'));
    assert(!p.node('#bo-list').markup.includes('<article'));
    assert.equal(p.node('#bo-all-orders').hidden,false);
});

test('following another order link in the same page updates the target',()=>{
    const p=page('#support-order='+token('b'));
    p.win.location.hash='#support-order='+token('a');p.events.hashchange();
    assert(p.node('#bo-list').markup.includes('synthetic-first'));
    assert(!p.node('#bo-list').markup.includes('synthetic-second'));
});
