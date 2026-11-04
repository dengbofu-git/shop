const {test}=require('node:test');
const assert=require('node:assert/strict');
const {requestId,remaining,mount}=require('../static/js/reservation-checkout.js');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
class Node {
    constructor(){this.textContent='';this.children=[];this.style={};this.events={};this.parentNode=this;}
    set innerHTML(value){throw new Error('Unsafe HTML rendering: '+value);}
    setAttribute(k,v){this[k]=v;}
    append(...nodes){this.children.push(...nodes);}
    replaceChildren(...nodes){this.children=nodes;}
    addEventListener(k,fn){this.events[k]=fn;}
    closest(){return null;}
}
async function setup(mode='create',fetcher,search='?settlement_type=1&address_id=1&sku_id=8&buy_count=2&order_id=example'){
    const nodes=Object.fromEntries(['pay_now','total_amount','order_id','clock'].map(k=>[k,new Node()]));
    let signedIn=true;const calls=[],intervals=[],events={};
    const win={document:{body:{dataset:{reservationMode:mode}},getElementById:k=>nodes[k],createElement:()=>new Node(),querySelector:()=>nodes.clock},
        AuthStorage:{getToken:()=>signedIn?'synthetic':null,getUser:()=>signedIn?'buyer':null},
        crypto:{randomUUID:()=> 'stable-request-id-123456'},history:{replaceState:(_,__,url)=>{win.url=url;}},
        location:{search,pathname:'/payment.html'},
        setInterval:fn=>{intervals.push(fn);return 1;},clearInterval:()=>{},addEventListener:(name,fn)=>{events[name]=fn;},
        fetch:async(url,options)=>{calls.push({url,options});return fetcher(url,options);}};
    mount(win);await flush();return {win,nodes,calls,intervals,events,signOut:()=>{signedIn=false;},click:()=>nodes.pay_now.events.click({preventDefault(){}})};
}
const ok=data=>({ok:true,json:async()=>({code:200,data})});
test('refresh keeps request id and never extends an absolute deadline',()=>{
    const first=requestId('?sku_id=1',()=> 'stable-request-id-123456');
    assert.equal(requestId('?'+first.query.toString(),()=>assert.fail('must not generate')).id,first.id);
    assert.equal(remaining('2026-10-22T10:00:00Z',Date.parse('2026-10-22T10:00:01Z')),0);
});
test('preview keeps submit-order action concise for all checkout-group limits',async()=>{
    for(const limit of [3,7,undefined]){
        const app=await setup('create',async()=>ok({reservation_checkout_version:1,max_unpaid_checkouts:limit,sku_list:[]}));
        assert.equal(app.nodes.order_id.textContent,'');
        assert.equal(app.nodes.order_id.children[0].textContent,'');
        assert.equal(app.nodes.pay_now.textContent,'提交订单');
        assert.equal(app.calls.length,1,'preview does not create an order');
    }
});
test('three merchants keep safe order details and one combined payment action',async()=>{
    const evil='<img src=x onerror=alert(1)>';
    const app=await setup('create',async(url,opt)=>!opt.method
        ?ok({reservation_checkout_version:1,checkout_sku_limit:20,max_unpaid_checkouts:3,sku_list:[{price:10,count:3}]})
        :ok({payment_mode:'combined',checkout_id:21,checkout_expires_at:new Date(Date.now()+60000).toISOString(),orders:[
            {order_id:'a',merchant_id:1,merchant_name:'茶店甲',status:1,currency:'CNY',total_amount:'10.00'},
            {order_id:'b',merchant_id:2,merchant_name:evil,status:1,currency:'CNY',total_amount:'20.00'},
            {order_id:'c',merchant_id:3,merchant_name:'',status:1,currency:'CNY',total_amount:'30.00'}]}));
    await app.click();const rows=app.nodes.order_id.children[1].children;
    assert.equal(rows.length,3);
    for(const [i,name,id,amount] of [[0,'茶店甲','a','10.00'],[1,evil,'b','20.00'],[2,'商家订单','c','30.00']]){
        assert.ok(rows[i].textContent.includes(name));assert.ok(rows[i].textContent.includes(amount));
        assert.equal(rows[i].children[0].href,'buyer_orders.html');
        assert.equal(rows[i].children[0].textContent,'查看订单');
    }
    assert.match(app.nodes.order_id.children[0].textContent,/一次付款/);
    assert.equal(app.nodes.pay_now.textContent,'合并付款');
    assert.equal(app.calls.filter(c=>c.options.method==='POST').length,1,'saving orders does not prepare a payment');
});
test('cart and direct checkout preserve string input types and unsafe payment states use the order list',async()=>{
    for(const type of ['0','1']){
        const app=await setup('create',async(url,opt)=>!opt.method
            ?ok({reservation_checkout_version:1,sku_list:[]})
            :ok({orders:[{order_id:'legacy',status:'1',currency:'CNY',total_amount:'10'},
                {order_id:'paid',status:2,currency:'CNY',total_amount:'20'},
                {order_id:'currency',status:1,currency:'USD',total_amount:'30'}]}),
            '?settlement_type='+type+'&address_id=12&sku_id=8&buy_count=2');
        await app.click();const payload=JSON.parse(app.calls[1].options.body);
        assert.equal(payload.settlement_type,type);assert.equal(payload.address_id,'12');
        if(type==='1'){assert.equal(payload.sku_id,'8');assert.equal(payload.buy_count,'2');}
        else {assert.equal(payload.sku_id,undefined);assert.equal(payload.buy_count,undefined);}
        for(const row of app.nodes.order_id.children[1].children){
            assert.equal(row.children[0].href,'buyer_orders.html');assert.equal(row.children[0].textContent,'查看订单');
        }
    }
});
test('checkout-group limit blocks repeated POST and points to own pending orders',async()=>{
    const app=await setup('create',async(url,opt)=>!opt.method
        ?ok({reservation_checkout_version:1,sku_list:[]})
        :{ok:false,json:async()=>({code:429,error_code:'UNPAID_CHECKOUT_LIMIT',error:'请处理待付款订单',pending_checkout_groups:7,max_unpaid_checkouts:7})});
    await app.click();const status=app.nodes.order_id.children[0];
    assert.match(status.textContent,/7/);assert.ok(status.children.some(n=>n.href==='buyer_orders.html'));
    await app.click();await app.click();assert.equal(app.win.location.href,'buyer_orders.html');
    assert.equal(app.calls.filter(c=>c.options.method==='POST').length,1);
});
test('timeout and cancel cooldown show server recovery time and exact retry seconds without another POST',async()=>{
    for(const reason of ['timeout','cancel']){
        const app=await setup('create',async(url,opt)=>!opt.method
            ?ok({reservation_checkout_version:1,sku_list:[]})
            :{ok:false,json:async()=>({code:429,error_code:'RESERVATION_COOLDOWN',error:'预留冷却中',cooldown_until:'2026-11-03T12:15:37+08:00',cooldown_reason:reason,retry_after:37})});
        await app.click();const status=app.nodes.order_id.children[0];
        assert.doesNotMatch(status.textContent,/T12:15:37\+08:00/);assert.match(status.textContent,/2026/);assert.match(status.textContent,/37秒/);
        assert.ok(status.children.some(n=>n.href==='buyer_orders.html'));
        assert.match(status.textContent,reason==='timeout'?/超时/:/取消/);
        await app.click();assert.equal(app.win.location.href,'buyer_orders.html');
        assert.equal(app.calls.filter(c=>c.options.method==='POST').length,1);
    }
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
    const app=await setup('pay',async()=>ok({order_id:'one',currency:'CNY',total_amount:'20',pay_url:'https://example.invalid/pay',expires_at:new Date(Date.now()+60000).toISOString()}));
    assert.equal(app.calls.length,1);await app.click();assert.equal(app.win.location.href,'https://example.invalid/pay');
    assert(app.calls.every(c=>!c.options.method));
});
test('unpaid-order blockers offer recovery instead of repeatedly submitting checkout',async()=>{
    for(const code of ['UNPAID_ORDER_LIMIT','UNPAID_QUANTITY_LIMIT','UNPAID_AMOUNT_LIMIT','SKU_ALREADY_RESERVED']){
        const app=await setup('create',async(url,opt)=>!opt.method
            ?ok({reservation_checkout_version:1,sku_list:[{price:330,count:2}]})
            :{ok:false,json:async()=>({code:429,error_code:code,error:'请先付款或取消已有待付款订单'})});
        await app.click();
        const status=app.nodes.order_id.children[0];
        assert.match(status.textContent,/请先付款或取消/);
        const recovery=status.children.find(node=>node.href==='buyer_orders.html');
        assert.ok(recovery,'blocked checkout must offer a link to existing orders');
        assert.equal(recovery.textContent,'查看待付款订单');
        assert.equal(app.nodes.pay_now.textContent,'处理待付款订单');
        await app.click();
        assert.equal(app.win.location.href,'buyer_orders.html');
        assert.equal(app.calls.filter(c=>c.options.method==='POST').length,1);
    }
});
test('payment configuration failure stays visible and offers the order list without creating orders',async()=>{
    const app=await setup('pay',async()=>({ok:false,json:async()=>({code:503,error_code:'PAYMENT_NOT_CONFIGURED',error:'支付服务尚未完成收款方校验配置，请联系平台'})}));
    assert.match(app.nodes.order_id.children[0].textContent,/支付服务尚未完成/);
    assert.equal(app.nodes.pay_now.textContent,'返回我的订单');
    await app.click();
    assert.equal(app.win.location.href,'buyer_orders.html');
    assert.equal(app.calls.length,1);
    assert(app.calls.every(c=>!c.options.method));
});
test('checkout uses the actual preview SKU limit and offers the unchanged cart without posting',async()=>{
    for(const [limit,count] of [[20,21],[2,3]]){
        const app=await setup('create',async()=>ok({reservation_checkout_version:1,checkout_sku_limit:limit,
            sku_list:Array.from({length:count},()=>({price:1,count:1}))}),'?settlement_type=0&address_id=1');
        const status=app.nodes.order_id.children[0];
        assert.equal(status.textContent,'单次最多结算'+limit+'种商品，请减少勾选数量后分批结算');
        assert.ok(status.children.some(node=>node.href==='cart.html'));
        await app.click();await app.click();
        assert.equal(app.win.location.href,'cart.html');
        assert.equal(app.calls.length,1);
    }
});
test('one SKU with many units and a legacy preview without limit can still submit',async()=>{
    for(const preview of [
        {checkout_sku_limit:20,sku_list:[{price:1,count:99}]},
        {sku_list:Array.from({length:21},()=>({price:1,count:1}))}
    ]){
        const app=await setup('create',async(url,opt)=>!opt.method?ok({reservation_checkout_version:1,...preview})
            :ok({orders:[{order_id:'one',status:1,currency:'CNY',total_amount:'99'}]}));
        await app.click();assert.equal(app.calls.filter(c=>c.options.method==='POST').length,1);
    }
});
test('cart growth rejected by POST offers cart recovery and never resubmits the old preview',async()=>{
    const message='单次最多结算20种商品，请减少勾选数量后分批结算';
    const app=await setup('create',async(url,opt)=>!opt.method
        ?ok({reservation_checkout_version:1,checkout_sku_limit:20,sku_list:[{price:1,count:1}]})
        :{ok:false,json:async()=>({code:400,error_code:'CHECKOUT_SKU_LIMIT',error:message,checkout_sku_limit:20})},
        '?settlement_type=0&address_id=1');
    await app.click();assert.equal(app.nodes.order_id.children[0].textContent,message);
    assert.ok(app.nodes.order_id.children[0].children.some(node=>node.href==='cart.html'));
    await app.click();assert.equal(app.win.location.href,'cart.html');
    assert.equal(app.calls.filter(c=>c.options.method==='POST').length,1);
});
test('preview limit error offers cart recovery while existing-order payment ignores new SKU limits',async()=>{
    const blocked=await setup('create',async()=>({ok:false,json:async()=>({code:400,error_code:'CHECKOUT_SKU_LIMIT',
        error:'单次最多结算2种商品，请减少勾选数量后分批结算',checkout_sku_limit:2})}));
    await blocked.click();assert.equal(blocked.win.location.href,'cart.html');assert.equal(blocked.calls.length,1);
    const pay=await setup('pay',async()=>ok({order_id:'legacy',currency:'CNY',checkout_sku_limit:1,sku_list:[{},{}],total_amount:'20',
        pay_url:'https://example.invalid/pay',expires_at:new Date(Date.now()+60000).toISOString()}));
    await pay.click();assert.equal(pay.win.location.href,'https://example.invalid/pay');
});

const future=()=>new Date(Date.now()+60000).toISOString();
const merchantOrders=()=>[
    {order_id:'tea-a',merchant_name:'茶店甲',total_amount:'10.00',currency:'CNY',status:1},
    {order_id:'tea-b',merchant_name:'茶店乙',total_amount:'23.00',currency:'CNY',status:1}
];
const savedCheckout=(extra={})=>({payment_mode:'combined',checkout_id:21,checkout_expires_at:future(),orders:merchantOrders(),...extra});
const payment=(extra={})=>({payment_id:'pay-example',checkout_id:21,currency:'CNY',total_amount:'33.00',expires_at:future(),
    status:'pending',payment_exception:'',orders:merchantOrders(),pay_url:'https://example.invalid/combined',...extra});
const preview=()=>ok({reservation_checkout_version:1,sku_list:[{price:999,count:1}]});

test('combined action sends only checkout id and displays the server payment total before redirect',async()=>{
    const app=await setup('create',async(url,opt)=>!opt.method?preview():url==='/v1/pays/checkout-payment'?ok(payment()):ok(savedCheckout()));
    await app.click();assert.equal(app.nodes.pay_now.textContent,'合并付款');
    await app.click();
    const prepared=app.calls.find(c=>c.url==='/v1/pays/checkout-payment');
    assert.ok(prepared);assert.equal(prepared.options.method,'POST');
    assert.deepEqual(JSON.parse(prepared.options.body),{checkout_id:21});
    assert.equal(prepared.options.headers.Authorization,'synthetic');
    assert.equal(prepared.options.cache,'no-store');
    assert.equal(app.nodes.total_amount.textContent,'CNY 33.00');
    assert.equal(app.win.location.href,'https://example.invalid/combined');
    await app.click();assert.equal(app.calls.filter(c=>c.url==='/v1/pays/checkout-payment').length,1);
});

test('saved server order total includes freight while prepared total replaces it with the actual payable amount',async()=>{
    const app=await setup('create',async(url,opt)=>!opt.method?preview():url==='/v1/pays/checkout-payment'
        ?ok(payment({total_amount:'10.00'})):ok(savedCheckout({checkout_total_amount:'37.50'})));
    assert.equal(app.nodes.total_amount.textContent,'CNY 999.00');
    await app.click();assert.equal(app.nodes.total_amount.textContent,'CNY 37.50');
    await app.click();assert.equal(app.nodes.total_amount.textContent,'CNY 10.00');
    assert.equal(app.win.location.href,'https://example.invalid/combined');
});

test('missing or malformed saved checkout totals never keep the preview as the final amount',async()=>{
    for(const checkout_total_amount of [undefined,null,'',' ','NaN','-1']){
        const app=await setup('create',async(url,opt)=>!opt.method?preview():ok(savedCheckout({checkout_total_amount})));
        await app.click();assert.equal(app.nodes.total_amount.textContent,'—');
        assert.equal(app.nodes.pay_now.textContent,'合并付款');
    }
});

test('existing merchant order opens the combined amount and splits without creating more orders',async()=>{
    const app=await setup('pay',async()=>ok(payment()),'?order_id=tea-a');
    assert.equal(app.calls[0].url,'/v1/orders/buyer?type=5&order_id=tea-a');
    assert.equal(app.nodes.total_amount.textContent,'CNY 33.00');
    assert.equal(app.nodes.pay_now.textContent,'合并付款');
    assert.equal(app.nodes.order_id.children[1].children.length,2);
    assert.ok(!app.nodes.order_id.textContent.includes('pay-example'));
    await app.click();assert.equal(app.win.location.href,'https://example.invalid/combined');
    assert.equal(app.calls.length,1);
});

test('checkout link prepares its own group once and waits for the user to continue',async()=>{
    const app=await setup('pay',async()=>ok(payment()),'?checkout_id=21');
    assert.equal(app.calls[0].url,'/v1/pays/checkout-payment');
    assert.deepEqual(JSON.parse(app.calls[0].options.body),{checkout_id:'21'});
    assert.equal(app.win.location.href,undefined);
    await app.click();assert.equal(app.win.location.href,'https://example.invalid/combined');
    assert.equal(app.calls.length,1);
});

test('paid invalid and review results recover through orders even if a payment URL exists',async()=>{
    for(const [state,word] of [['paid',/已.*付|付款.*完成/],['invalid',/变化|失效/],['review',/核验/]]){
        const app=await setup('create',async(url,opt)=>!opt.method?preview():url==='/v1/pays/checkout-payment'?ok(payment({status:state})):ok(savedCheckout()));
        await app.click();await app.click();
        assert.equal(app.win.location.href,undefined);
        assert.match(app.nodes.order_id.children[0].textContent,word);
        await app.click();assert.equal(app.win.location.href,'buyer_orders.html');
        assert.equal(app.calls.length,3);
    }
});

test('combined payment refuses missing expired or unsafe data instead of following a stale link',async()=>{
    for(const extra of [{pay_url:null},{expires_at:'invalid'},{expires_at:'2001-01-01T00:00:00Z'},
        {currency:'USD'},{total_amount:'NaN'},{total_amount:'-1'},{total_amount:'0.00'},{total_amount:0},{pay_url:'javascript:alert(1)'},
        {status:'unknown'},{payment_exception:'duplicate_receipt'}]){
        const app=await setup('pay',async()=>ok(payment(extra)),'?order_id=tea-a');
        await app.click();assert.equal(app.win.location.href,'buyer_orders.html',JSON.stringify(extra));
        assert.equal(app.calls.length,1);
    }
});

test('payment failures show safe server errors and never retry order creation or payment',async()=>{
    for(const error_code of ['PAYMENT_GROUP_CHANGED','PAYMENT_REVIEW_REQUIRED','NO_PAYABLE_ORDERS','PAYMENT_NOT_CONFIGURED']){
        const app=await setup('create',async(url,opt)=>!opt.method?preview():url==='/v1/pays/checkout-payment'
            ?{ok:false,json:async()=>({code:503,error_code,error:'支付暂不可用，请查看订单'})}:ok(savedCheckout()));
        await app.click();await app.click();
        assert.match(app.nodes.order_id.children[0].textContent,/支付暂不可用/);
        assert.equal(app.win.location.href,undefined);
        await app.click();await app.click();assert.equal(app.win.location.href,'buyer_orders.html');
        assert.equal(app.calls.length,3);
    }
});

test('older create responses show orders without promising combined payment',async()=>{
    for(const extra of [{payment_mode:undefined},{checkout_id:undefined}]){
        const app=await setup('create',async(url,opt)=>!opt.method?preview():ok(savedCheckout(extra)));
        await app.click();assert.equal(app.nodes.pay_now.textContent,'查看我的订单');
        assert.doesNotMatch(app.nodes.order_id.children[0].textContent,/合并付款|分别付款/);
        assert(app.nodes.order_id.children[1].children.every(row=>row.children[0].textContent==='查看订单'));
        await app.click();assert.equal(app.calls.length,2);assert.equal(app.win.location.href,'buyer_orders.html');
    }
});

test('payment retry reuses the saved checkout without posting orders again',async()=>{
    let failed=true;
    const app=await setup('create',async(url,opt)=>{
        if(!opt.method)return preview();
        if(url!=='/v1/pays/checkout-payment')return ok(savedCheckout());
        if(failed)throw Error('连接中断，请重试');return ok(payment());
    });
    await app.click();await app.click();failed=false;await app.click();
    assert.equal(app.calls.filter(c=>c.url==='/v1/orders/buyer'&&c.options.method==='POST').length,1);
    const attempts=app.calls.filter(c=>c.url==='/v1/pays/checkout-payment');
    assert.equal(attempts.length,2);assert.equal(attempts[0].options.body,attempts[1].options.body);
    assert.equal(app.win.location.href,'https://example.invalid/combined');
});

test('in-flight payment double clicks and leaving or changing account cannot reveal or follow returned payment data',async()=>{
    for(const interrupt of ['none','account','leave']){
        let resolve;
        const app=await setup('create',async(url,opt)=>!opt.method?preview():url==='/v1/pays/checkout-payment'
            ?new Promise(r=>{resolve=r;}):ok(savedCheckout()));
        await app.click();const wait=app.click();await app.click();
        assert.equal(app.calls.length,3);
        if(interrupt==='account')app.signOut();if(interrupt==='leave')app.events.pagehide();
        resolve(ok(payment()));await wait;
        assert.equal(app.win.location.href,interrupt==='none'?'https://example.invalid/combined':undefined);
        if(interrupt!=='none'){
            assert.equal(app.nodes.total_amount.textContent,'');
            assert.equal(app.nodes.order_id.children[1].children.length,0);
        }
    }
});

test('fixed payment countdown reaches recovery without exposing raw timestamps or refreshing the deadline',async()=>{
    const realNow=Date.now;let now=Date.parse('2026-11-03T04:00:00Z');Date.now=()=>now;
    try{
        const app=await setup('pay',async()=>ok(payment({expires_at:'2026-11-03T04:01:00Z'})),'?order_id=tea-a');
        assert.match(app.nodes.clock.textContent,/1:00/);assert.doesNotMatch(app.nodes.clock.textContent,/刷新|2026-/);
        now+=61000;app.intervals[0]();await app.click();
        assert.equal(app.win.location.href,'buyer_orders.html');assert.equal(app.calls.length,1);
    }finally{Date.now=realNow;}
});

test('late preview after pagehide never restores amounts or submit action',async()=>{
    let resolve;const app=await setup('create',async()=>new Promise(r=>{resolve=r;}));
    app.events.pagehide();resolve(preview());await flush();
    assert.equal(app.nodes.total_amount.textContent,'');
    assert.equal(app.nodes.pay_now['aria-disabled'],'true');
    await app.click();assert.equal(app.calls.length,1);
});
