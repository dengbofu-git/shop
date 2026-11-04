const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {createController, renderProducts, renderPrices, renderMonths, width, mount} = require('../static/js/merchant-insights.js');
function fixture() { return {scope:'merchant_only',currency:'CNY',period:{code:'year'},generated_at:'2026-10-22T00:00:00Z',
    totals:{amount:'0.00',quantity:0,paid_orders:0},top_products:[],sales_top_products:[],
    monthly:['2026-05','2026-06','2026-07','2026-08','2026-09','2026-10'].map(month=>({month,amount:'0.00',order_count:0})),
    price_distribution:{quantity:0,excluded_lines:0,buckets:['under_80','80_to_120','120_to_280','280_plus'].map(code=>({code,quantity:0,percent:null}))}}; }
function defer() {let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};}
function docStub() {return {createElement(tag){return {tag,children:[],style:{},attrs:{},append(...nodes){this.children.push(...nodes);},
    replaceChildren(...nodes){this.children=[...nodes];},setAttribute(k,v){this.attrs[k]=v;},set innerHTML(_){throw Error('unsafe HTML');}};}};}
function scopeFixture(cny=0,unknown=94,other=0) {return {currency:'CNY',status_order_count:cny+unknown+other,
    cny_order_count:cny,unknown_currency_order_count:unknown,other_currency_order_count:other,
    financial_state:unknown+other?(cny?'partial':'unavailable'):'complete'};}
function surface(data) {
    const doc=docStub(),template=fs.readFileSync('client/templates/merchant_dashboard.html','utf8'),events={},nodes={};
    function node(tag='div') {const item=doc.createElement(tag);Object.assign(item,{events:{},hidden:false,
        classList:{toggle(){}},addEventListener(k,v){this.events[k]=v;},getAttribute(k){return this.attrs[k];},focus(){}});return item;}
    for (const match of template.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) {
        const item=node(match[1]);for(const attr of match[0].matchAll(/([\w-]+)="([^"]*)"/g))item.attrs[attr[1]]=attr[2];nodes[match[2]]=item;
    }
    const labels=[...template.matchAll(/data-insight-text="([^"]+)"/g)].map(m=>Object.assign(node(),{dataset:{insightText:m[1]}}));
    const dataNodes=[...template.matchAll(/data-insight-data/g)].map(()=>node());
    const tabs=Object.values(nodes).filter(item=>item.attrs.role==='tab');
    nodes['merchant-insights'].querySelectorAll=selector=>selector==='[role=tab]'?tabs:selector==='[data-insight-text]'?labels:dataNodes;
    let auth='merchant-a',reply=data,fail=false,languageChanged;
    Object.assign(doc,{documentElement:{lang:'zh',dir:'ltr'},getElementById:id=>nodes[id],addEventListener(k,v){events[k]=v;}});
    const win={document:doc,AuthStorage:{getToken:()=>auth},MutationObserver:class{constructor(fn){languageChanged=fn;}observe(){}},
        AbortController,clearTimeout(){},setTimeout(){},addEventListener(){},fetch:async()=>{if(fail)throw Error('offline');return {ok:true,json:async()=>({code:200,data:reply})};}};
    mount(win);
    return {nodes,labels,doc,flush:()=>new Promise(resolve=>setImmediate(resolve)),
        language(lang){doc.documentElement.lang=lang;doc.documentElement.dir=lang==='ar'?'rtl':'ltr';languageChanged();},
        refresh(next,failed=false){reply=next;fail=failed;events['supplier:panel-changed']({detail:{panel:'dashboard'}});},
        account(next){auth=next;languageChanged();}};
}
test('insights disclose excluded annual history while monthly zero stays explicitly included CNY, in three languages',async()=>{
    const data={...fixture(),sales_scope:scopeFixture()};
    // Annual unknown orders may all precede these six months. No per-month exclusion can be inferred.
    const page=surface(data);await page.flush();
    for(const lang of ['zh','en','ar']) {
        page.language(lang);
        const warning=page.nodes['insights-scope-status'];assert.ok(warning,'scope warning exists');
        assert.equal(warning.hidden,false);assert.match(warning.textContent,lang==='zh'?/94.*币种未记录/:lang==='en'?/94.*currency.*not recorded/:/(?:94|٩٤).*عملة/);
        assert.match(page.nodes['insights-summary'].textContent,/CNY/);
        assert.match(page.nodes['insights-top-products'].children[0].textContent,/CNY/);
        assert.match(page.nodes['insights-sales-top'].children[0].textContent,/CNY/);
        assert.match(page.nodes['insights-price-list'].children[0].textContent,/CNY/);
        assert.equal(page.nodes['insights-months'].children.length,6);
        for (const row of page.nodes['insights-months'].children) {
            assert.equal(row.children[1].textContent,(0).toLocaleString(lang));
            assert.equal(row.children[2].textContent,(0).toLocaleString(lang==='zh'?'zh-CN':lang,{style:'currency',currency:'CNY'}));
        }
        assert.match(page.labels.find(n=>n.dataset.insightText==='amount').textContent,lang==='zh'?/已计入.*CNY/:lang==='en'?/Included.*CNY/:/CNY/);
        assert.match(page.labels.find(n=>n.dataset.insightText==='monthlyNote').textContent,lang==='zh'?/0.*不代表.*历史交易/:lang==='en'?/0.*history/:/0.*تاريخ/);
    }
});
test('insights partial data preserves CNY facts and separates known foreign currencies from unrecorded currencies',async()=>{
    const data={...fixture(),sales_scope:scopeFixture(2,3,4),totals:{amount:'28.11',quantity:2,paid_orders:2},
        top_products:[{product_id:1,name:'<img src=x onerror=alert(1)>',quantity:2,amount:'28.11'}]};
    const page=surface(data);await page.flush();
    assert.match(page.nodes['insights-scope-status']?.textContent || '',/3.*币种未记录/);
    assert.match(page.nodes['insights-scope-status'].textContent,/4.*其他币种/);
    assert.equal(page.nodes['insights-top-products'].children[0].children[0].textContent,data.top_products[0].name);
    assert.match(page.nodes['insights-summary'].textContent,/2.*CNY/);
    page.refresh({...fixture(),sales_scope:scopeFixture(0,0,0)});await page.flush();
    assert.equal(page.nodes['insights-scope-status'].hidden,true);assert.equal(page.nodes['insights-scope-status'].textContent,'');
});
test('insights missing or invalid scope shows fallback without fabricated counts and clears on loading, error, account switch',async()=>{
    const page=surface({...fixture(),sales_scope:scopeFixture()});await page.flush();
    for(const sales_scope of [undefined,null,{}, {...scopeFixture(),financial_state:'complete'}, {...scopeFixture(),status_order_count:999},
        {...scopeFixture(),unknown_currency_order_count:'94'},scopeFixture(2,0,0)]) {
        page.refresh({...fixture(),sales_scope});
        assert.equal(page.nodes['insights-scope-status']?.textContent || '','');await page.flush();
        assert.match(page.nodes['insights-scope-status']?.textContent || '',/范围信息暂不可用/);
        assert.doesNotMatch(page.nodes['insights-scope-status'].textContent,/94|999|未计入/);
    }
    page.refresh({...fixture(),sales_scope:scopeFixture()},true);
    assert.equal(page.nodes['insights-scope-status'].textContent,'');assert.equal(page.nodes['insights-months'].children.length,0);
    await page.flush();assert.equal(page.nodes['insights-scope-status'].hidden,true);assert.equal(page.nodes['insights-summary'].textContent,'');
    page.refresh({...fixture(),sales_scope:scopeFixture()});await page.flush();
    assert.equal(page.nodes['insights-scope-status'].hidden,false);
    page.account('merchant-b');assert.equal(page.nodes['insights-scope-status'].textContent,'');
    assert.equal(page.nodes['insights-months'].children.length,0);assert.equal(page.nodes['insights-summary'].textContent,'');
});
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
