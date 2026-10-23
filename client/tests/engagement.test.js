/* Transport, privacy and text rendering tests; browser flows cover actual forms. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const path = require('node:path');

function setup() {
    class Element {
        constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.textContent = ''; }
        append(...values) { this.children.push(...values); }
        setAttribute(key, value) { this.attrs[key] = value; }
        addEventListener() {}
        querySelectorAll() { return []; }
        set innerHTML(_) { throw new Error('Unsafe HTML rendering'); }
    }
    const values = new Map(), requests = [], document = {
        body:{dataset:{engRole:'buyer'}}, documentElement:{lang:'zh-CN'},
        createElement:tag => new Element(tag), addEventListener() {}, querySelectorAll:() => []
    };
    const context = {document, window:{}, localStorage:{getItem:key => values.get(key), setItem:(k,v) => values.set(k,v)},
        AuthStorage:{getToken:() => 'synthetic-tab-token'}, CustomEvent:class {},
        fetch:async (url, options) => { requests.push({url, options}); return {ok:true, json:async () => ({code:200,data:{items:[]}})}; },
        Date, Math, Promise};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/engagement.js'), 'utf8'), context);
    return {E:context.window.Engagement, context, requests, values};
}

test('same-origin transport uses current tab token and stable request id', async () => {
    const {E, requests} = setup();
    await E.api('conversations', {text:'synthetic',request_id:'fixed-request-1'});
    await E.api('conversations', {text:'synthetic',request_id:'fixed-request-1'});
    assert.equal(requests[0].url, '/v1/engagement/conversations');
    assert.equal(requests[0].options.headers.Authorization, 'Bearer synthetic-tab-token');
    assert.equal(requests[0].options.body, requests[1].options.body);
    assert.equal(requests[0].options.cache, 'no-store');
});

test('authentication failures remain actionable without resetting other accounts', async () => {
    const {E, context} = setup();
    context.fetch = async () => ({ok:false,status:401,json:async () => ({error:'internal details'})});
    await assert.rejects(E.api('conversations'), error => error.status === 401 && error.message === '请先登录');
});

test('review and seller reply payloads are rendered exclusively as text', () => {
    const {E} = setup(), attack = '<img src=x onerror=alert(1)>';
    const card = E.reviewCard({buyer_name:attack,rating:1,text:attack,specification:attack,created_at:'2026-10-21T00:00:00Z',
        reply:{text:attack,created_at:'2026-10-21T00:00:00Z'}});
    const nodes = [];
    (function walk(node) { nodes.push(node); node.children.forEach(walk); })(card);
    assert.equal(nodes.filter(node => node.textContent === attack).length, 4);
    assert.equal(nodes.some(node => node.tag === 'img' || node.tag === 'script'), false);
    assert.equal(nodes.find(node => node.className === 'eng-stars').attrs['aria-label'], '商品评分: 1 / 5');
});

test('Arabic and merchant language preferences are selected independently', () => {
    const {E, context, values} = setup();
    values.set('buyer_lang','ar'); values.set('supplier_lang','en');
    assert.equal(E.t('send'),'إرسال');
    context.document.body.dataset.engRole = 'merchant';
    assert.equal(E.t('send'),'Send');
});

test('buyer chat guidance starts from products; review notices contain no private-chat guidance', () => {
    const {E, values} = setup();
    for (const [lang, product, order, chat] of [['zh','商品详情','订单','咨询'],['en','product detail','order','chat'],['ar','تفاصيل المنتج','الطلب','المحادثة']]) {
        values.set('buyer_lang',lang);
        assert(E.t('emptyBuyerChats').includes(product));
        assert(!E.t('emptyBuyerChats').includes(order));
        assert(!E.t('reviewHistory').includes(chat));
    }
});
