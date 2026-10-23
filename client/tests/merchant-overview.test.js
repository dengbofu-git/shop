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
    doc.documentElement.lang='en'; languageChanged();
    assert.equal(labels.find(item => item.dataset.overviewText==='heading').textContent,'Business overview');
    controller.error(); assert.equal(nodes['overview-sales'].textContent,'—'); assert.equal(nodes['overview-retry'].hidden,false);
    nodes['overview-retry'].events.click(); assert.equal(dispatched,'supplier:refresh-overview');
    controller.loading(); assert.equal(nodes['overview-retry'].hidden,true);
    controller.render({...fixture, completed:undefined}); assert.equal(nodes['overview-retry'].hidden,false);
    controller.render(fixture); assert.equal(nodes['overview-retry'].hidden,true);
});
