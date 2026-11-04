// node --test client/tests/merchant-overview.test.js
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {values, mount} = require('../static/js/merchant-overview.js');
const fixture = {total_sales:60209.01, paid_order_count:94, avg_order_amount:640.52, completion_rate:25.2, completed:27, order_count:107};
test('four historical metrics use the API paid-order basis, not shipment tasks', () => {
    const result = values({...fixture, pending_ship:29, unpaid:13}, 'zh');
    assert.equal(result.sales, '¥60,209.01'); assert.equal(result.paid, '94');
    assert.equal(result.average, '¥640.52'); assert.equal(result.completion, '25.2%');
    assert.equal(result.completion_note, '已完成 27 / 全部 107 笔');
    assert.equal(values(fixture, 'en').completion_note, '27 completed / 107 total orders');
    assert(values(fixture, 'ar').completion_note.includes('إجمالي الطلبات'));
});
test('empty merchant is true zero, missing/invalid data is never fabricated as zero', () => {
    const empty = Object.fromEntries(Object.keys(fixture).map(key => [key,0]));
    assert.equal(values(empty,'zh').sales, '¥0.00'); assert.equal(values(empty,'zh').completion, '0.0%');
    assert.throws(() => values(null,'zh'));
    assert.throws(() => values({...fixture, avg_order_amount:undefined},'zh'));
    assert.throws(() => values({...fixture, total_sales:'not a number'},'zh'));
});

function scope(cny=0, unknown=94, other=0) {
    return {currency:'CNY',status_order_count:cny+unknown+other,cny_order_count:cny,
        unknown_currency_order_count:unknown,other_currency_order_count:other,
        financial_state:unknown+other ? (cny ? 'partial' : 'unavailable') : 'complete'};
}
test('excluded historical orders never appear as true zero CNY revenue; completion uses all orders', () => {
    const result = values({...fixture,total_sales:0,paid_order_count:0,avg_order_amount:0,sales_scope:scope()},'zh');
    assert.equal(result.sales,'暂无可统计');assert.equal(result.average,'暂无可统计');assert.equal(result.paid,'0');
    assert.equal(result.completion,'25.2%');assert.equal(result.completion_note,'已完成 27 / 全部 107 笔');
    assert.match(result.scope_message,/94.*币种未记录.*未计入人民币/);
    assert.equal(result.scope_state,'unavailable');
});
test('partial CNY facts and true empty shop keep real values; missing scope discloses fallback', () => {
    const partial = values({...fixture,sales_scope:scope(94,2,3)},'zh');
    assert.equal(partial.sales,'¥60,209.01');assert.equal(partial.paid,'94');
    assert.match(partial.scope_message,/2.*币种未记录/);assert.match(partial.scope_message,/3.*其他币种/);
    const empty = values({...fixture,total_sales:0,paid_order_count:0,avg_order_amount:0,sales_scope:scope(0,0,0)},'en');
    assert.equal(empty.sales,'¥0.00');assert.equal(empty.scope_state,'complete');assert.equal(empty.scope_message,'');
    assert.match(values(fixture,'zh').scope_message,/范围信息暂不可用/);
});
test('a real zero-amount CNY order remains zero revenue when other historical currency is unrecorded', () => {
    const result=values({...fixture,total_sales:0,paid_order_count:1,avg_order_amount:0,sales_scope:scope(1,1,0)},'zh');
    assert.equal(result.scope_state,'partial');assert.equal(result.paid,'1');
    assert.equal(result.sales,'¥0.00');assert.equal(result.average,'¥0.00');
    assert.match(result.scope_message,/1笔历史订单币种未记录.*未计入人民币统计/);
});
test('all three languages disclose the currency exclusion instead of an empty transaction history', () => {
    for (const lang of ['zh','en','ar']) {
        const result=values({...fixture,total_sales:0,paid_order_count:0,avg_order_amount:0,sales_scope:scope()},lang);
        assert.notEqual(result.sales,'¥0.00');assert.equal(result.scope_state,'unavailable');
        assert.match(result.scope_message,lang==='zh'?/94.*币种未记录/:lang==='en'?/94.*currency.*not recorded/:/(?:94|٩٤).*عملة/);
    }
});
test('invalid scope never claims coverage or invents exclusion numbers', () => {
    for (const invalid of [null,{},'94', {...scope(),currency:'USD'}, {...scope(),status_order_count:93},
        {...scope(),unknown_currency_order_count:-1}, {...scope(),unknown_currency_order_count:'94'},
        {...scope(),financial_state:'complete'}, {...scope(),financial_state:'partial'},
        {...scope(94,0,0),cny_order_count:93,status_order_count:93},
        {...scope(),status_order_count:Infinity}, {...scope(),unknown_currency_order_count:94.5}]) {
        const result=values({...fixture,sales_scope:invalid},'zh');
        assert.equal(result.scope_state,'unknown');assert.match(result.scope_message,/范围信息暂不可用/);
        assert.doesNotMatch(result.scope_message,/94|93|未计入/);
    }
});
test('loading, errors, recovery, language changes and retry are visible in the real renderer', () => {
    const template = fs.readFileSync('client/templates/merchant_dashboard.html','utf8');
    const nodes = Object.fromEntries([...template.matchAll(/id="([^"]+)"/g)].map(match => [match[1], {attrs:{},events:{},
        setAttribute(key,value) {this.attrs[key]=value;}, addEventListener(key,fn) {this.events[key]=fn;}}]));
    const labels = [...template.matchAll(/data-overview-text="([^"]+)"/g)].map(match => ({dataset:{overviewText:match[1]}}));
    nodes['merchant-overview'].querySelectorAll = () => labels;
    let languageChanged, dispatched;
    const doc = {documentElement:{lang:'zh'},getElementById:id => nodes[id],dispatchEvent:event => {dispatched=event.type;}};
    const win = {document:doc, MutationObserver:class {constructor(fn) {languageChanged=fn;} observe() {}}, CustomEvent:class {constructor(type) {this.type=type;}}};
    const controller = mount(win);
    assert.equal(nodes['merchant-overview'].attrs['aria-busy'],'true'); assert.equal(nodes['overview-sales'].textContent,'—');
    controller.render(fixture); assert.equal(nodes['overview-status'].hidden,true);
    assert.equal(nodes['overview-sales'].textContent,'¥60,209.01');
    assert.match(labels.find(item => item.dataset.overviewText==='sales').textContent,/CNY/);
    assert.match(labels.find(item => item.dataset.overviewText==='paid').textContent,/CNY/);
    controller.render({...fixture,total_sales:0,paid_order_count:0,avg_order_amount:0,sales_scope:scope()});
    assert.equal(nodes['overview-sales'].textContent,'暂无可统计');
    assert.equal(nodes['overview-scope-status'].hidden,false);assert.match(nodes['overview-scope-status'].textContent,/94.*币种未记录/);
    doc.documentElement.lang='en'; languageChanged();
    assert.equal(labels.find(item => item.dataset.overviewText==='heading').textContent,'Business overview');
    assert.match(nodes['overview-scope-status'].textContent,/94.*currency/);
    controller.error(); assert.equal(nodes['overview-sales'].textContent,'—'); assert.equal(nodes['overview-retry'].hidden,false);
    assert.equal(nodes['overview-scope-status'].hidden,true);assert.equal(nodes['overview-scope-status'].textContent,'');
    nodes['overview-retry'].events.click(); assert.equal(dispatched,'supplier:refresh-overview');
    controller.loading(); assert.equal(nodes['overview-retry'].hidden,true);
    assert.equal(nodes['overview-scope-status'].hidden,true);assert.equal(nodes['overview-scope-status'].textContent,'');
    controller.render({...fixture, completed:undefined}); assert.equal(nodes['overview-retry'].hidden,false);
    controller.render(fixture); assert.equal(nodes['overview-retry'].hidden,true);
});
