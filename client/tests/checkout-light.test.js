const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const utils=require('../static/js/checkout-utils.js');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function confirmation(data,error){
    const nodes=new Map();let ready;const calls=[];
    function element(){return {children:[],events:{},value:'',textContent:'',append(...nodes){this.children.push(...nodes);},
        appendChild(node){this.children.push(node);},replaceChildren(){this.children=[];},addEventListener(k,fn){this.events[k]=fn;}};}
    function get(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);}
    const context={CheckoutUtils:utils,URLSearchParams,baseUrl:'',
        document:{getElementById:get,createElement:element,querySelectorAll:()=>[],addEventListener:(key,fn)=>{ready=fn;}},
        AuthStorage:{getToken:()=> 'synthetic',getUser:()=> 'buyer',clear(){}},localStorage:{getItem(){return null;}},
        location:{search:'',href:''},fetch:async(url,options)=>{calls.push({url,options});return {ok:!error,status:error?400:200,
            json:async()=>error?{code:400,error_code:'CHECKOUT_SKU_LIMIT',error,checkout_sku_limit:2}:{code:200,data,base_url:'/media/'}};}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/js/orderconfirm.js'),'utf8'),context);
    ready();await flush();return {get,context,calls};
}
function preview(count,limit,units=1){return {checkout_sku_limit:limit,
    sku_list:Array.from({length:count},(_,i)=>({id:i+1,name:'Tea',price:'1.00',count:units})),
    addresses:[{id:1,name:'Test',mobile:'synthetic',address:'Test road'}]};}
test('confirmation rejects too many SKU rows with the actual limit and preserves cart recovery',async()=>{
    for(const [limit,count] of [[20,21],[2,3]]){
        const app=await confirmation(preview(count,limit));
        assert.equal(app.get('go_pay').disabled,true);
        assert.equal(app.get('checkout-status').textContent,'单次最多结算'+limit+'种商品，请减少勾选数量后分批结算');
        assert.ok(app.get('checkout-status').children.some(n=>n.href==='cart.html'));
        app.get('go_pay').events.click();assert.equal(app.context.location.href,'');assert.equal(app.calls.length,1);
    }
});
test('confirmation counts SKU rows rather than units and keeps old previews compatible',async()=>{
    for(const data of [preview(1,20,99),preview(20,20),preview(21,undefined)]){
        const app=await confirmation(data);assert.equal(app.get('go_pay').disabled,false);
        app.get('go_pay').events.click();assert.equal(app.context.location.href,'payment.html?address_id=1&settlement_type=0');
    }
});
test('server preview limit errors keep confirmation disabled and point to cart',async()=>{
    const app=await confirmation(null,'单次最多结算2种商品，请减少勾选数量后分批结算');
    assert.equal(app.get('go_pay').disabled,true);
    assert.ok(app.get('checkout-status').children.some(n=>n.href==='cart.html'));
});

async function policy(data){
    const elements=Object.fromEntries(['ttl_seconds','max_unpaid_quantity','max_unpaid_amount','max_stock_percent','change_reason'].map(k=>[k,{value:''}]));
    const button={},message={},note={},events={},calls=[];
    const form={elements,querySelector:()=>button,addEventListener:(key,fn)=>{events[key]=fn;}};
    const context={document:{getElementById:id=>({'reservation-policy':form,'reservation-policy-status':message,'reservation-policy-ttl-note':note}[id])},
        AuthStorage:{getToken:()=> 'synthetic'},fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({code:200,data})};}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/js/reservation-policy.js'),'utf8'),context);
    await flush();return {elements,button,message,note,calls,submit:()=>events.submit({preventDefault(){}})};
}
test('merchant TTL is read-only platform 900 while the three shop limits remain editable',async()=>{
    const app=await policy({ttl_seconds:900,ttl_editable:false,ttl_source:'platform_fixed',configured_ttl_seconds:300,
        max_unpaid_quantity:70,max_unpaid_amount:'3000.00',max_stock_percent:50});
    assert.equal(app.button.disabled,false);assert.equal(app.elements.ttl_seconds.readOnly,true);
    assert.equal(Number(app.elements.ttl_seconds.value),900);assert.match(app.note.textContent,/15分钟/);assert.match(app.note.textContent,/300/);
    app.elements.ttl_seconds.value='60';app.elements.max_unpaid_quantity.value='80';app.elements.max_unpaid_amount.value='4000.00';
    app.elements.max_stock_percent.value='60';app.elements.change_reason.value=' 调整供货额度 ';
    await app.submit();
    const saved=JSON.parse(app.calls[1].options.body);
    assert.deepEqual(saved,{ttl_seconds:900,max_unpaid_quantity:'80',max_unpaid_amount:'4000.00',max_stock_percent:'60',change_reason:'调整供货额度'});
});
test('merchant cannot write platform TTL to an older backend that still exposes editable shop TTL',async()=>{
    const app=await policy({ttl_seconds:300,max_unpaid_quantity:70,max_unpaid_amount:'3000.00',max_stock_percent:50});
    assert.equal(app.button.disabled,true);await app.submit();assert.equal(app.calls.length,1);
    assert.match(app.message.textContent,/15分钟/);
});
