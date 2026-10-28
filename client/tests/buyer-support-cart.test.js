const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(require.resolve('../static/js/buyer-support.js'),'utf8');
const helper = source.slice(source.indexOf('    function cartAction('),source.indexOf('    function amountCents('));
function setup(fetch) {
    const all=[]; let ids=0; let storedCount;
    const badges = [{textContent:'0'}, {textContent:'0'}];
    function node(tag) {
        const value={tag,children:[],attributes:{},events:{},textContent:'',disabled:false,
            appendChild(c){this.children.push(c);c.parentNode=this;},
            setAttribute(k,v){this.attributes[k]=v;},addEventListener(k,f){this.events[k]=f;}};
        all.push(value);return value;
    }
    const context={document:{createElement:node,querySelectorAll:()=>badges},AuthStorage:{setCount:value=>{storedCount=value;}},cartOperations:Object.create(null),uuid:()=>`operation-${++ids}`,
        identityUser:'synthetic-buyer',identityToken:'synthetic-token',ensureIdentity:()=>true,
        checkIdentity:()=>{},sameIdentity:()=>true,fetch};
    vm.createContext(context);vm.runInContext(helper+';this.action=cartAction;',context);
    const result={request_id:'11111111-1111-4111-8111-111111111111'};
    return {context,all,result,badges,get storedCount(){return storedCount;},create:(selection={},editable=true)=>context.action(result,selection,'加入采购车',2,editable)};
}
test('rendering does not write; click submits bound reference and visible quantity',async()=>{
    const calls=[];const app=setup(async(url,options)=>{calls.push({url,payload:JSON.parse(options.body)});return {ok:true,json:async()=>({code:200,data:{carts_count:3}})};});
    app.create({sku_id:7});assert.equal(calls.length,0);
    const button=app.all.find(n=>n.tag==='button');await button.events.click();
    assert.equal(calls.length,1);assert.match(calls[0].url,/\/v1\/carts\/synthetic-buyer\/recommendations$/);
    assert.equal(calls[0].payload.sku_id,7);assert.equal(calls[0].payload.count,2);
    assert.equal(calls[0].payload.recommendation_request_id,app.result.request_id);
    assert.equal(button.textContent,'已加入');assert.equal(button.disabled,true);
    assert.equal(app.storedCount,3);assert(app.badges.every(n=>n.textContent==='3'));
});
test('network retry reuses operation ID; repeated click cannot double submit',async()=>{
    const ids=[];let attempt=0;
    const app=setup(async(url,options)=>{ids.push(JSON.parse(options.body).request_id);if(++attempt===1)throw Error('network');return {ok:true,json:async()=>({code:200,replayed:true})};});
    app.create({sku_id:7});const button=app.all.find(n=>n.tag==='button');
    await button.events.click();assert.equal(button.disabled,false);
    await button.events.click();await button.events.click();
    assert.equal(ids.length,2);assert.equal(ids[0],ids[1]);
});
test('whole bundle submits only saved bundle identity, never client item list',async()=>{
    let payload;const app=setup(async(url,options)=>{payload=JSON.parse(options.body);return {ok:true,json:async()=>({code:200,data:{carts_count:3}})};});
    app.create({bundle_id:'bundle-aaaaaaaaaaaa'},false);
    await app.all.find(n=>n.tag==='button').events.click();
    assert.equal(payload.bundle_id,'bundle-aaaaaaaaaaaa');assert.equal(payload.count,undefined);assert.equal(payload.items,undefined);
    assert.equal(app.storedCount,3);assert(app.badges.every(n=>n.textContent==='3'));
});
test('invalid quantity does not submit and stale history has no action',async()=>{
    let count=0;const app=setup(async()=>{count++;});
    assert.equal(app.context.action({}, {}, '加入',1,true),null);
    app.create({sku_id:7});app.all.find(n=>n.tag==='input').value='0';
    await app.all.find(n=>n.tag==='button').events.click();assert.equal(count,0);
});
test('backend refusal is shown without success or losing retry identity',async()=>{
    const app=setup(async()=>({ok:false,json:async()=>({code:409,error:'商品已下架'})}));
    app.create({sku_id:7});const button=app.all.find(n=>n.tag==='button');await button.events.click();
    assert.equal(button.disabled,false);assert.equal(button.textContent,'加入采购车');
    assert(app.all.some(n=>n.textContent==='商品已下架'));
});

test('storage failure does not prevent immediate badge update after a successful add',async()=>{
    const app=setup(async()=>({ok:true,json:async()=>({code:200,data:{carts_count:4}})}));
    app.context.AuthStorage.setCount=()=>{throw Error('blocked');};
    app.create({sku_id:7});await app.all.find(n=>n.tag==='button').events.click();
    assert(app.badges.every(n=>n.textContent==='4'));
    assert.equal(app.all.find(n=>n.tag==='button').textContent,'已加入');
});
test('identity change before response cannot overwrite the next account badge',async()=>{
    const app=setup(async()=>{
        app.context.checkIdentity=()=>{throw Error('identity changed');};
        app.context.sameIdentity=()=>false;
        return {ok:true,json:async()=>({code:200,data:{carts_count:9}})};
    });
    app.create({sku_id:7});await app.all.find(n=>n.tag==='button').events.click();
    assert.equal(app.storedCount,undefined);assert(app.badges.every(n=>n.textContent==='0'));
});
