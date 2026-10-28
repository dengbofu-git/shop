const {test}=require('node:test');
const assert=require('node:assert/strict');
const {requestId,remaining,mount}=require('../static/js/reservation-checkout.js');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
class Node {
    constructor(){this.textContent='';this.children=[];this.style={};this.events={};this.parentNode=this;}
    setAttribute(k,v){this[k]=v;}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=nodes;}
    addEventListener(k,fn){this.events[k]=fn;}
    closest(){return null;}
}
async function setup(mode='create',fetcher){
    const nodes=Object.fromEntries(['pay_now','total_amount','order_id','clock'].map(k=>[k,new Node()]));
    let signedIn=true;const calls=[],intervals=[];
    const win={document:{body:{dataset:{reservationMode:mode}},getElementById:k=>nodes[k],createElement:()=>new Node(),querySelector:()=>nodes.clock},
        AuthStorage:{getToken:()=>signedIn?'synthetic':null,getUser:()=>signedIn?'buyer':null},
        crypto:{randomUUID:()=> 'stable-request-id-123456'},history:{replaceState:(_,__,url)=>{win.url=url;}},
        location:{search:'?settlement_type=1&address_id=1&sku_id=8&buy_count=2&order_id=example',pathname:'/payment.html'},
        setInterval:fn=>{intervals.push(fn);return 1;},clearInterval:()=>{},addEventListener:()=>{},
        fetch:async(url,options)=>{calls.push({url,options});return fetcher(url,options);}};
    mount(win);await flush();return {win,nodes,calls,intervals,signOut:()=>{signedIn=false;},click:()=>nodes.pay_now.events.click({preventDefault(){}})};
}
const ok=data=>({ok:true,json:async()=>({code:200,data})});
test('refresh keeps request id and never extends an absolute deadline',()=>{
    const first=requestId('?sku_id=1',()=> 'stable-request-id-123456');
    assert.equal(requestId('?'+first.query.toString(),()=>assert.fail('must not generate')).id,first.id);
    assert.equal(remaining('2026-10-22T10:00:00Z',Date.parse('2026-10-22T10:00:01Z')),0);
});
test('opening checkout does not reserve; a network retry uses the same id',async()=>{
    let fail=true;const app=await setup('create',async(url,options)=>{
        if(!options.method)return ok({reservation_checkout_version:1,sku_list:[{price:10,count:2}]});
        if(fail)throw Error('network lost');
        return ok({orders:[{order_id:'one',total_amount:'20.00',status:1}]});
    });
    assert.equal(app.calls.length,1);await app.click();fail=false;await app.click();
    const posts=app.calls.filter(c=>c.options.method==='POST');
    assert.equal(posts.length,2);assert.equal(posts[0].options.body,posts[1].options.body);
    assert.equal(JSON.parse(posts[0].options.body).request_id,'stable-request-id-123456');
    assert.equal(app.nodes.pay_now.textContent,'查看我的订单');
});
test('legacy backend without capability cannot create an unprotected order',async()=>{
    const app=await setup('create',async()=>ok({sku_list:[]}));await app.click();
    assert.equal(app.calls.length,1);assert.equal(app.win.location.href,'buyer_orders.html');
});
test('in-flight duplicate clicks and account changes cannot submit another reservation',async()=>{
    let resolve;const app=await setup('create',async(url,opt)=>!opt.method?ok({reservation_checkout_version:1,sku_list:[]}):new Promise(r=>{resolve=r;}));
    const pending=app.click();await app.click();assert.equal(app.calls.length,2);
    resolve(ok({orders:[{order_id:'one',status:1,total_amount:0}]}));await pending;
    const other=await setup('create',async()=>ok({reservation_checkout_version:1,sku_list:[]}));other.signOut();await other.click();assert.equal(other.calls.length,1);
});
test('pay screen stops at the unchanged deadline and never writes paid state',async()=>{
    const app=await setup('pay',async()=>ok({order_id:'one',total_amount:'20',pay_url:'https://example.invalid/pay',expires_at:new Date(Date.now()+60000).toISOString()}));
    assert.equal(app.calls.length,1);await app.click();assert.equal(app.win.location.href,'https://example.invalid/pay');
    assert(app.calls.every(c=>!c.options.method));
});
