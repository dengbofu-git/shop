const {test} = require('node:test');
const assert = require('node:assert/strict');
const {createController, renderProducts, renderPrices, renderMonths, width} = require('../static/js/merchant-insights.js');
function fixture() { return {scope:'merchant_only',currency:'CNY',period:{code:'year'},generated_at:'2026-10-22T00:00:00Z',
    totals:{amount:'0.00',quantity:0,paid_orders:0},top_products:[],sales_top_products:[],
    monthly:['2026-05','2026-06','2026-07','2026-08','2026-09','2026-10'].map(month=>({month,amount:'0.00',order_count:0})),
    price_distribution:{quantity:0,excluded_lines:0,buckets:['under_80','80_to_120','120_to_280','280_plus'].map(code=>({code,quantity:0,percent:null}))}}; }
function defer() {let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
function docStub() {return {createElement(tag){return {tag,children:[],style:{},attrs:{},append(...nodes){this.children.push(...nodes);},
    replaceChildren(...nodes){this.children=[...nodes];},setAttribute(k,v){this.attrs[k]=v;},set innerHTML(_){throw Error('unsafe HTML');}};}};}
test('real empty data is ready; failed refresh clears previous facts and supports retry',async()=>{
    const states=[];let fail=false;const c=createController({token:()=>'shop',onState:s=>states.push(s),request:async()=>{if(fail)throw Error('offline');return fixture();}});
    await c.refresh();assert.equal(states.at(-1).status,'ready');assert.equal(states.at(-1).data.totals.paid_orders,0);
    fail=true;await c.refresh();assert.deepEqual(states.slice(-2).map(s=>s.status),['loading','error']);assert.equal(states.at(-1).data,undefined);
    fail=false;await c.refresh();assert.equal(states.at(-1).status,'ready');
});
test('latest refresh wins even when an older response arrives last',async()=>{
    const waits=[defer(),defer()],states=[];let call=0;
    const c=createController({token:()=>'shop',onState:s=>states.push(s),request:()=>waits[call++].promise});
    const old=c.refresh(),fresh=c.refresh();const updated=fixture();updated.totals.paid_orders=2;
    waits[1].resolve(updated);await fresh;waits[0].resolve(fixture());await old;
    assert.equal(states.at(-1).data.totals.paid_orders,2);assert.equal(states.filter(s=>s.status==='ready').length,1);
});
test('account switch, missing auth and page departure reject old merchant data',async()=>{
    const wait=defer(),states=[];let auth='a',calls=0;
    const c=createController({token:()=>auth,onState:s=>states.push(s),request:()=>{calls++;return wait.promise;}});
    const pending=c.refresh();auth='b';wait.resolve(fixture());await pending;
    assert.equal(states.at(-1).reason,'login');assert.equal(states.at(-1).data,undefined);
    auth='';await c.refresh();assert.equal(calls,1);
    const stopped=[],another=defer();const d=createController({token:()=>'a',onState:s=>stopped.push(s),request:()=>another.promise});
    const last=d.refresh();d.cancel();another.resolve(fixture());await last;assert.deepEqual(stopped.map(s=>s.status),['loading']);
});
test('permission and malformed aggregates show errors instead of invented zero values',async()=>{
    for(const response of [null,{...fixture(),scope:'global'},{...fixture(),currency:'USD'},
        {...fixture(),totals:{...fixture().totals,amount:'bad'}},
        {...fixture(),price_distribution:{...fixture().price_distribution,buckets:[]}}]) {
        const states=[];const c=createController({token:()=>'a',onState:s=>states.push(s),request:async()=>response});
        await c.refresh();assert.equal(states.at(-1).status,'error');assert.equal(states.at(-1).data,undefined);
    }
    const states=[];const c=createController({token:()=>'a',onState:s=>states.push(s),request:async()=>{throw {status:403};}});
    await c.refresh();assert.equal(states.at(-1).reason,'forbidden');
});
test('quantity bars match their labels rather than monetary proportions; names stay plain text',()=>{
    const doc=docStub(),target=doc.createElement('ul'),attack='<img src=x onerror=alert(1)>';
    renderProducts(doc,target,[{name:attack,quantity:80,amount:'1000.00'},{name:'另一茶品',quantity:40,amount:'10.00'}],'zh',false);
    assert.equal(target.children[0].children[0].textContent,attack);
    assert.equal(target.children[0].children[2].textContent,'80件');
    assert.equal(target.children[1].children[1].children[0].style.width,'50%');
    assert.equal(width(0,0),0);assert.equal(width(200,100),100);
});
test('revenue ranking preserves cents and uses revenue for bar widths',()=>{
    const doc=docStub(),target=doc.createElement('ul');
    renderProducts(doc,target,[{name:'甲',quantity:1,amount:'100.50'},{name:'乙',quantity:99,amount:'50.25'}],'zh',true);
    assert.match(target.children[0].children[2].textContent,/100\.50/);
    assert.equal(target.children[1].children[1].children[0].style.width,'50%');
});
test('price distribution shows real purchased units and explicit non-overlapping bounds',()=>{
    const doc=docStub(),target=doc.createElement('ul');
    renderPrices(doc,target,{quantity:10,buckets:[{code:'80_to_120',quantity:4,percent:40}]},'zh');
    assert.equal(target.children[0].children[0].children[0].textContent,'80 – 120');
    assert.equal(target.children[0].children[0].children[1].textContent,'元 / 件');
    assert.equal(target.children[0].children[2].children[0].textContent,'40%');
    assert.equal(target.children[0].children[2].children[1].textContent,'4件');
    assert.equal(target.children[0].children[1].children[0].style.width,'40%');
    renderPrices(doc,target,{quantity:0,buckets:[]},'en');assert.equal(target.children[0].textContent,'No paid items in this period');
});
test('price ranges retain CNY units and endpoint meaning across languages, including zero-count buckets',()=>{
    const doc=docStub(),target=doc.createElement('ul');
    for (const lang of ['zh','en','ar']) {
        renderPrices(doc,target,{quantity:306,buckets:[
            {code:'under_80',quantity:89,percent:29.1},{code:'80_to_120',quantity:0,percent:0},
            {code:'120_to_280',quantity:80,percent:26.1},{code:'280_plus',quantity:137,percent:44.8}]},lang);
        assert.equal(target.children.length,4);
        const labels=target.children.map(row=>row.children[0].children[0].textContent);
        assert.equal(labels[0],lang==='zh'?'低于 80':lang==='en'?'Below 80':'أقل من '+(80).toLocaleString('ar'));
        assert.equal(labels[3],lang==='zh'?'280 及以上':lang==='en'?'280 and above':(280).toLocaleString('ar')+' فأكثر');
        for (const row of target.children) assert.match(row.children[0].children[1].textContent,lang==='zh'?/元.*件/:/CNY/);
        assert.equal(target.children[1].children[1].children[0].style.width,'0%');
        assert.equal(target.children[1].children[0].children[0].attrs.dir,'ltr');
        assert.equal(target.children[3].children[1].children[0].style.width,'44.8%');
        assert.equal(target.children[3].children[2].children[0].textContent,(.448).toLocaleString(lang==='zh'?'zh-CN':lang,{style:'percent',maximumFractionDigits:1}));
    }
});
test('monthly values show full year-month and two decimal CNY; all three languages render',()=>{
    const doc=docStub(),target=doc.createElement('tbody');
    for(const lang of ['zh','en','ar']) {
        renderMonths(doc,target,[{month:'2026-02',order_count:2,amount:'28.11'}],lang);
        assert.equal(target.children.length,1);assert.equal(target.children[0].children[0].attrs.scope,'row');
        assert.notEqual(target.children[0].children[0].textContent,'Invalid Date');
        assert.equal(target.children[0].children[1].textContent,(2).toLocaleString(lang));
        assert.equal(target.children[0].children[2].textContent,Number('28.11').toLocaleString(lang==='zh'?'zh-CN':lang,{style:'currency',currency:'CNY'}));
    }
});
