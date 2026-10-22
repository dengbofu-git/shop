const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const summary = require('../static/js/product-detail-summary.js');
const workbench = fs.readFileSync('client/static/js/buyer-workbench.js','utf8');
const formatter = workbench.slice(workbench.indexOf('    function formatDisplayPrice('),workbench.indexOf('    function updatePrices('));
const catalogPrice = new Function('currentCurrency','value',formatter + '\nreturn formatDisplayPrice(value);');

class Element {
    constructor(tag) {this.tag=tag;this.children=[];this.attrs={};this.events={};this.textContent='';}
    setAttribute(k,v) {this.attrs[k]=String(v);}
    removeAttribute(k) {delete this.attrs[k];}
    addEventListener(k,fn) {this.events[k]=fn;}
    append(...items) {this.children.push(...items);}
    replaceChildren() {this.children=[];}
    set innerHTML(_) {throw new Error('Unsafe HTML');}
}
function setup(currency='USD') {
    const nodes=Object.fromEntries(['currency-select','detail-price-value','sku'].map(id=>[id,new Element('div')]));
    nodes['currency-select'].value=currency;
    const ui=summary.mount({getElementById:id=>nodes[id],createElement:tag=>new Element(tag)});
    return {ui,nodes,change(currency) {nodes['currency-select'].value=currency;nodes['currency-select'].events.change();}};
}
const fixture = {price:'66.50',sku_sale_attr_names:['净含量','包装'],sku_sale_attr_id:[1,2],sku_sale_attr_val_id:[11,21],
    sku_all_sale_attr_vals_id:{1:[11,12],2:[21,22]},sku_all_sale_attr_vals_name:{1:['100g','200g'],2:['袋装','礼盒']}};

test('currency and decimals match the procurement display without mutating the API price',()=>{
    const app=setup('AED'), original=JSON.stringify(fixture);
    app.ui.render(fixture);
    for(const currency of ['USD','AED','SAR','CNY','EUR','USD']) {
        app.change(currency);
        const displayed=Number(catalogPrice(currency,fixture.price).replace(/^[^\d]*/,''));
        assert.equal(app.nodes['detail-price-value'].textContent,currency+' '+displayed.toFixed(2));
        assert.equal(app.ui.basePrice(),66.5,'cart retains the exact base unit price');
    }
    assert.equal(JSON.stringify(fixture),original);
});

test('currency chosen before the API response is respected; unavailable price is never a fake zero',()=>{
    const app=setup();app.change('SAR');assert.equal(app.nodes['detail-price-value'].textContent,'—');
    app.ui.render(fixture);assert.equal(app.nodes['detail-price-value'].textContent,'SAR 34.58');
    for(const bad of [null,undefined,'', 'invalid',-1]) assert.equal(summary.price(bad,'USD'),'—');
    assert.equal(summary.price(0,'USD'),'USD 0.00');
    assert.equal(summary.price(66,'__proto__'),'USD 9.24');
});

test('net content displays only the selected value as text, while other specifications remain buttons',()=>{
    const app=setup();app.ui.render(fixture);
    const rows=app.nodes.sku.children, fixed=rows[0].children[1].children;
    assert.equal(fixed.length,1);assert.equal(fixed[0].tag,'span');assert.equal(fixed[0].textContent,'100g');
    assert.equal(fixed[0].attrs['data-id'],'11');assert.equal(fixed[0].attrs['data-value'],'100g');
    assert.equal(fixed[0].attrs.contenteditable,undefined);assert.deepEqual(fixed[0].events,{});
    const choices=rows[1].children[1].children;assert.equal(choices.length,2);
    assert(choices.every(el=>el.tag==='button' && el.type==='button'));
    assert.equal(choices[0].attrs['aria-pressed'],'true');
});

test('missing fixed values do not pick another package; supplied labels are rendered as plain text',()=>{
    const app=setup();
    app.ui.render({...fixture,sku_sale_attr_val_id:[999,21],sku_sale_attr_names:['净含量','<img src=x>']});
    assert.equal(app.nodes.sku.children[0].children[1].children[0].textContent,'—');
    assert.equal(app.nodes.sku.children[1].children[0].textContent,'<img src=x>：');
    app.ui.render({price:'10'});assert.equal(app.nodes.sku.children.length,0);
});

test('the real template binds price/attributes and guest cart uses the raw decimal price',()=>{
    const html=fs.readFileSync('client/templates/product_details.html','utf8');
    assert(html.includes('ProductDetailSummary.render(result.data)'));
    assert(html.includes('id="detail-price-value"'));
    assert(html.includes("$('#sku button.spu_value').click"));
    assert(html.includes("$(this).attr('data-value') || $(this).val()"));
    assert(html.includes('unit_price:window.ProductDetailSummary.basePrice()'));
    assert(!html.includes("parseInt($('#pro_price')"));
});

function quantitySetup(stock=143) {
    const nodes=Object.fromEntries(['buy-num','detail-quantity-minus','detail-quantity-plus'].map(id=>[id,new Element('div')]));
    const input=nodes['buy-num']; input.value='1';
    const control=summary.quantityControl({getElementById:id=>nodes[id]});control.setStock(stock);
    return {control,input,minus:nodes['detail-quantity-minus'],plus:nodes['detail-quantity-plus'],
        type(text) {input.value=text;input.events.input();},blur() {input.events.blur();}};
}

test('quantity supports direct typing and the integrated buttons each step once',()=>{
    const app=quantitySetup();assert.equal(app.input.value,'1');assert.equal(app.minus.disabled,true);
    app.type('5');app.blur();assert.equal(app.input.value,'5');assert.equal(app.input.attrs['aria-valuenow'],'5');
    app.plus.events.click();assert.equal(app.input.value,'6');
    app.minus.events.click();assert.equal(app.input.value,'5');
    app.type('');assert.equal(app.input.value,'','allow replacing an existing value');
    app.blur();assert.equal(app.input.value,'5','empty input restores the previous valid quantity');
});

test('quantity cannot exceed stock, drop below one or accept partial/fractional numbers',()=>{
    const app=quantitySetup();app.type('5');app.blur();
    for(const invalid of ['2.5','3abc','1e2']) {app.type(invalid);assert.equal(app.input.attrs['aria-invalid'],'true');app.blur();assert.equal(app.input.value,'5');}
    for(const below of ['0','-8']) {app.type(below);app.blur();assert.equal(app.input.value,'1');}
    app.type('999');assert.equal(app.control.commit(),143);assert.equal(app.input.value,'143');
    assert.equal(app.plus.disabled,true);assert.equal(app.input.attrs['aria-valuemax'],'143');
});

test('quantity keyboard steps, stock updates and zero-stock disabling use the same committed value',()=>{
    const app=quantitySetup();let prevented=0;
    const key=key=>app.input.events.keydown({key,preventDefault(){prevented++;}});
    app.type('10');key('ArrowUp');assert.equal(app.input.value,'11');
    key('ArrowDown');assert.equal(app.input.value,'10');
    app.type('999');key('Enter');assert.equal(app.input.value,'143');assert.equal(prevented,3);
    app.control.setStock(8);assert.equal(app.control.commit(),8);
    app.control.setStock(0);assert.equal(app.control.commit(),0);assert.equal(app.input.disabled,true);
    assert.equal(app.minus.disabled,true);assert.equal(app.plus.disabled,true);
    app.control.setStock(1);assert.equal(app.input.value,'1');assert.equal(app.input.disabled,false);
    assert.equal(app.minus.disabled,true);assert.equal(app.plus.disabled,true);
});

test('purchase handlers normalize direct quantity input and do not keep the old delegated step handlers',()=>{
    const html=fs.readFileSync('client/templates/product_details.html','utf8');
    assert(html.includes('class="detail-quantity" role="group"'));
    const input=html.match(/<input[^>]+id="buy-num"[^>]*>/)[0];
    assert(input.includes('inputmode="numeric"'));assert(!input.includes('readonly'));
    assert.equal((html.match(/var buyNum = window\.ProductDetailSummary\.quantity\(\)/g)||[]).length,2);
    assert(!html.includes("on('click', '.numberMinus'"));assert(!html.includes("on('click', '.numberAdd'"));
});
