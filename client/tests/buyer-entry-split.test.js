/* Exercise the real order renderer: a contact-capable item must still lead only to reviews. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function renderOrders(goods, completed=true) {
    const nodes=new Map();
    const $=selector=>{
        if(typeof selector==='function'){selector();return;}
        if(!nodes.has(selector))nodes.set(selector,{value:'',markup:'',textValue:'',
            on(){return this;},val(){return this.value;},html(v){this.markup=v;return this;},
            text(v){this.textValue=v;return this;},append(v){this.markup+=v;return this;},
            removeClass(){return this;},addClass(){return this;}});
        return nodes.get(selector);
    };
    $.ajax=()=>({done(callback){callback({code:200,data:{orders_list:[{order_id:'test-order',order_type:'standard',
        order_time:'2026-10-22',status:completed?4:1,is_completed:completed,order_total_amount:28.11,
        order_total_count:1,order_freight:0,order_sku:goods}]}});return this;},fail(){return this;}});
    const context={TeaMoney:require('../static/js/currency.js'),$,window:{},document:{},AuthStorage:{getUser:()=>'testbuyer',getToken:()=>'synthetic'},console};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/js/buyer-orders.js'),'utf8'),context);
    return nodes.get('#bo-list').markup;
}
test('completed order links go to review or existing review even when contact is allowed',()=>{
    const html=renderOrders([{id:101,sku:11,name:'茶品',price:28.11,count:1,can_contact:true,can_review:true},
        {id:102,sku:12,name:'另一茶品',price:10,count:1,can_contact:true,can_review:false,review_id:77}]);
    assert.match(html,/buyer_reviews\.html\?order_item_id=101/);
    assert.match(html,/buyer_reviews\.html\?order_item_id=102/);
    assert.match(html,/评价商品/);assert.match(html,/查看评价/);
    assert.doesNotMatch(html,/buyer_messages|联系商家|data-eng-text="contact"/);
});
test('pending and unverified items gain neither chat nor review actions',()=>{
    const html=renderOrders([{id:103,sku:13,name:'旧茶品',price:10,count:1,can_contact:true,can_review:false}],false);
    assert.doesNotMatch(html,/buyer_messages|buyer_reviews|联系商家/);
    assert.match(html,/gopay\.html\?order_id=test-order/);
});
