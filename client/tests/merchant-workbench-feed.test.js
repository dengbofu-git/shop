const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createController, renderMessage, panelAllowed} = require('../static/js/merchant-workbench-feed.js');
const data = () => ({total:0, todos:{unshipped:0, settlement:0, consultations:0}, messages:[]});
const deferred = () => {let resolve; const promise = new Promise(r => {resolve=r;}); return {promise,resolve};};

test('real zero is ready; failed fetch clears data and can be retried', async () => {
    const states = []; let fail = true;
    const controller = createController({token:()=>'shop-a', onState:s=>states.push(s), request:async()=>{
        if(fail) throw new Error('offline'); return data();
    }});
    await controller.refresh();
    assert.deepEqual(states.map(s=>s.status), ['loading','error']);
    assert.equal(states.at(-1).data, undefined);
    fail=false; await controller.refresh();
    assert.equal(states.at(-1).status,'ready');
    assert.equal(states.at(-1).data.todos.unshipped,0);
});
test('late response from previous refresh cannot overwrite newer facts', async () => {
    const first=deferred(), second=deferred(), states=[]; let calls=0;
    const controller=createController({token:()=>'a',onState:s=>states.push(s),request:()=>++calls===1?first.promise:second.promise});
    const old=controller.refresh(), fresh=controller.refresh();
    second.resolve({...data(),total:2}); await fresh;
    first.resolve({...data(),total:9}); await old;
    assert.equal(states.at(-1).data.total,2);
    assert.equal(states.filter(s=>s.status==='ready').length,1);
});
test('account switch and logout cannot display previous merchant data', async () => {
    const wait=deferred(), states=[]; let token='a', calls=0;
    const controller=createController({token:()=>token,onState:s=>states.push(s),request:()=>{calls++;return wait.promise;}});
    const pending=controller.refresh(); token='b'; wait.resolve({...data(),total:42}); await pending;
    assert.equal(states.at(-1).reason,'login'); assert.equal(states.at(-1).data,undefined);
    token=''; await controller.refresh(); assert.equal(calls,1); assert.equal(states.at(-1).reason,'login');
});
test('permission failure and cancellation do not turn unknown state into zero', async () => {
    const states=[]; const controller=createController({token:()=>'a',onState:s=>states.push(s),request:async()=>{throw {status:403};}});
    await controller.refresh(); assert.equal(states.at(-1).reason,'forbidden'); assert.equal(states.at(-1).data,undefined);
    const wait=deferred(), cancelled=[];
    const other=createController({token:()=>'a',onState:s=>cancelled.push(s),request:()=>wait.promise});
    const pending=other.refresh();other.cancel();wait.resolve(data());await pending;
    assert.deepEqual(cancelled.map(s=>s.status),['loading']);
});
function documentStub(){return {createElement(tag){return {tag,dataset:{},children:[],append(...nodes){this.children.push(...nodes);},set innerHTML(_){throw Error('unsafe HTML');}};}};}
test('buyer content is plain text and only merchant panels can be linked', () => {
    const unsafe='<img src=x onerror=alert(1)>';
    const li=renderMessage(documentStub(),{kind:'inquiry',text:unsafe,panel:'javascript:alert(1)',created_at:'2026-10-22T00:00:00Z'},'zh');
    const link=li.children[1];assert.equal(link.children[0].textContent,unsafe);assert.equal(link.href,undefined);
    for(const panel of ['https://evil/merchant_orders.html','buyer_orders.html','merchant_messages.html?conversation_id=1&evil=1'])assert.equal(panelAllowed(panel),false);
    for(const panel of ['merchant_orders.html?filter=unshipped','merchant_settlement.html','merchant_messages.html?conversation_id=1'])assert.equal(panelAllowed(panel),true);
});
test('order subtype and shipping statuses render from persisted codes in three languages', () => {
    const row={kind:'order',order_id:'P-1',order_type:'presale',status:4,panel:'merchant_orders.html',created_at:'2026-10-22T00:00:00Z'};
    assert.equal(renderMessage(documentStub(),row,'zh').children[1].children[0].textContent,'订单 P-1 · 待发货');
    assert.match(renderMessage(documentStub(),row,'en').children[1].children[0].textContent,/Awaiting shipment/);
    assert.match(renderMessage(documentStub(),row,'ar').children[1].children[0].textContent,/بانتظار الشحن/);
    assert.match(renderMessage(documentStub(),{...row,kind:'shipping',tracking_number:'T-1',status:5},'zh').children[1].children[0].textContent,/运单 T-1 · 已签收/);
});
