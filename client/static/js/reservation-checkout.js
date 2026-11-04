(function (global,factory) {
    var api=factory();if(typeof module==='object'&&module.exports)module.exports=api;
    if(global.document)global.addEventListener('DOMContentLoaded',function(){api.mount(global);});
})(typeof window==='undefined'?{}:window,function(){
    'use strict';
    function requestId(search,generate){var q=new URLSearchParams(search);var id=q.get('checkout_request_id');if(!/^[A-Za-z0-9_-]{16,64}$/.test(id||'')){id=generate();q.set('checkout_request_id',id);}return {id:id,query:q};}
    function remaining(deadline,now){return Math.max(0,Math.ceil((Date.parse(deadline)-now)/1000))||0;}
    function mount(win){
        var doc=win.document,token=win.AuthStorage.getToken(),user=win.AuthStorage.getUser();
        if(!token||!user){win.location.href='login.html';return;}
        var account={token:token,user:user};
        function sameAccount(){return win.AuthStorage.getToken()===account.token&&win.AuthStorage.getUser()===account.user;}
        var mode=doc.body.dataset.reservationMode,params=new URLSearchParams(win.location.search);
        var button=doc.getElementById('pay_now'),amount=doc.getElementById('total_amount'),title=doc.getElementById('order_id');
        var status=doc.createElement('p');status.setAttribute('role','status');status.id='reservation-status';
        var list=doc.createElement('div');list.id='reservation-orders';title.parentNode.append(status,list);
        var pending=false,ready=false,finished=false,active=true,redirected=false;
        var payUrl=null,deadline=null,timer=null,checkoutId=null,recoveryUrl='buyer_orders.html';
        function label(text){button.textContent=text;button.setAttribute('role','button');button.tabIndex=0;}
        function disable(value){button.setAttribute('aria-disabled',String(value));button.style.opacity=value?'.55':'1';}
        function message(text){status.replaceChildren();status.textContent=text;}
        function stopClock(){if(timer)win.clearInterval(timer);timer=null;}
        function clearPayment(){payUrl=null;deadline=null;stopClock();}
        function recover(text,action){clearPayment();ready=false;finished=true;message(text);label(action||'查看我的订单');disable(false);}
        function discard(){clearPayment();checkoutId=null;ready=false;finished=true;amount.textContent='';title.textContent='';list.replaceChildren();message('账号或页面已改变，请重新打开结算页面');label('返回我的订单');disable(true);}
        async function api(path,options){
            if(!sameAccount())throw new Error('账号已改变，请重新打开结算页面');
            var response=await win.fetch(path,Object.assign({headers:{Authorization:token,'Content-Type':'application/json'},cache:'no-store'},options));
            var data=await response.json();
            if(!sameAccount())throw new Error('账号已改变，请重新打开结算页面');
            if(!response.ok||data.code!==200){var error=new Error(data.error||data.errmsg||'请求失败，请稍后重试');error.data=data;throw error;}
            return data.data;
        }
        function showError(error){payUrl=null;message(error.message);var d=error.data||{};
            if(['PAYMENT_GROUP_CHANGED','PAYMENT_REVIEW_REQUIRED','NO_PAYABLE_ORDERS','PAYMENT_NOT_CONFIGURED'].indexOf(d.error_code)!==-1){
                recover(error.message,'返回我的订单');return;
            }
            if(d.error_code==='CHECKOUT_SKU_LIMIT'){
                var cartLink=doc.createElement('a');cartLink.href='cart.html';cartLink.textContent='返回采购车减少勾选';status.append(' ',cartLink);
                ready=false;finished=true;recoveryUrl='cart.html';label('返回采购车减少勾选');
            }
            if(d.error_code==='UNPAID_CHECKOUT_LIMIT'&&Number.isInteger(d.pending_checkout_groups)&&Number.isInteger(d.max_unpaid_checkouts)){
                status.textContent+=' 当前有'+d.pending_checkout_groups+'次含有效未付预留的提交，最多'+d.max_unpaid_checkouts+'次；按一次提交统计，不按商家订单数统计。';
            }
            if(d.error_code==='RESERVATION_COOLDOWN'){
                status.textContent+=(d.cooldown_reason==='timeout'?' 上次预留超时。':d.cooldown_reason==='cancel'?' 上次订单取消。':'');
                if(d.cooldown_until&&Number.isFinite(Date.parse(d.cooldown_until)))status.textContent+=' 可恢复时间：'+new Date(d.cooldown_until).toLocaleString()+'。';
                if(Number.isInteger(d.retry_after)&&d.retry_after>=0)status.textContent+=' 请等待'+d.retry_after+'秒后重新打开结算页面。';
            }
            if(['UNPAID_CHECKOUT_LIMIT','RESERVATION_COOLDOWN','UNPAID_ORDER_LIMIT','UNPAID_QUANTITY_LIMIT','UNPAID_AMOUNT_LIMIT','SKU_ALREADY_RESERVED'].indexOf(d.error_code)!==-1){
                var ordersLink=doc.createElement('a');ordersLink.href='buyer_orders.html';ordersLink.textContent='查看待付款订单';status.append(' ',ordersLink);
                finished=true;label('处理待付款订单');
            }
            if(d.error_code==='BULK_CONFIRMATION_REQUIRED'&&d.sku_id){var a=doc.createElement('a');a.href='product_details.html?skuid='+encodeURIComponent(d.sku_id);a.textContent='查看商品并联系商家';status.append(' ',a);}
        }
        var identity=requestId(win.location.search,function(){return win.crypto.randomUUID();});
        if(mode==='create')win.history.replaceState(null,'',win.location.pathname+'?'+identity.query.toString());
        var payload={address_id:params.get('address_id'),settlement_type:params.get('settlement_type'),request_id:identity.id};
        if(payload.settlement_type==='1'){payload.sku_id=params.get('sku_id');payload.buy_count=params.get('buy_count');}
        function renderOrders(orders){
            list.replaceChildren();orders.forEach(function(order){
                var row=doc.createElement('p'),link=doc.createElement('a');
                link.href='buyer_orders.html';link.textContent='查看订单';
                var value=Number(order.total_amount),total=Number.isFinite(value)&&value>=0?value.toFixed(2):'待确认';
                row.textContent=(order.merchant_name||'商家订单')+' · 订单 '+order.order_id+' · '+(order.currency||'币种未记录')+' '+total+' ';
                row.append(link);list.append(row);
            });
        }
        function clock(){
            if(!active||!deadline)return;
            if(!sameAccount()){discard();return;}
            var seconds=remaining(deadline,Date.now());
            var slot=doc.querySelector('.pay_leftTime');if(slot)slot.textContent='剩余付款时间 '+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
            if(!seconds)recover('已到付款截止时间，请返回订单列表确认状态。');
        }
        function startClock(value){stopClock();deadline=value;if(deadline){timer=win.setInterval(clock,1000);clock();}}
        function paymentReady(data,combined){
            clearPayment();
            if(Array.isArray(data.orders))renderOrders(data.orders);
            var total=Number(data.total_amount);
            if(Number.isFinite(total)&&total>=0&&data.currency==='CNY')amount.textContent='CNY '+total.toFixed(2);
            else amount.textContent='';
            if(combined){
                title.textContent='';
                if(data.status==='paid'){recover('付款已完成，请查看订单。');return false;}
                if(data.status==='review'||data.payment_exception){recover('付款结果需要核验，请联系平台并查看订单。');return false;}
                if(data.status==='invalid'){recover('付款信息已变化，请返回订单查看。');return false;}
                if(data.status!=='pending'){recover('付款状态暂不可用，请查看订单。');return false;}
            }else title.textContent='订单 '+(data.order_id||data.originalorder_id||'');
            if(!Number.isFinite(total)||total<=0||data.currency!=='CNY'||!data.expires_at||
                remaining(data.expires_at,Date.now())<=0||typeof data.pay_url!=='string'||!/^https?:\/\//i.test(data.pay_url)){
                recover('该订单暂不可付款，请返回订单列表确认状态。');return false;
            }
            payUrl=data.pay_url;ready=true;finished=false;
            message(combined?'一次付款，各店分别发货。':'请在付款时间内完成支付。');
            label(combined?'合并付款':'前往支付平台');startClock(data.expires_at);disable(false);return true;
        }
        function goPay(){
            if(!payUrl||!sameAccount()||!active)return;
            if(remaining(deadline,Date.now())<=0){clock();return;}
            redirected=true;disable(true);win.location.href=payUrl;
        }
        function preparePayment(){return api('/v1/pays/checkout-payment',{method:'POST',body:JSON.stringify({checkout_id:checkoutId})});}
        async function load(){
            disable(true);
            try{
                if(mode==='create'){
                    var query=new URLSearchParams({settlement_type:payload.settlement_type});
                    if(payload.sku_id){query.set('sku_id',payload.sku_id);query.set('buy_num',payload.buy_count);}
                    var preview=await api('/v1/orders/'+encodeURIComponent(user)+'/advance?'+query);
                    if(!active)return;
                    if(preview.reservation_checkout_version!==1)throw new Error('库存保护尚未启用，请稍后再结算');
                    if(Number.isInteger(preview.checkout_sku_limit)&&preview.checkout_sku_limit>0&&preview.sku_list.length>preview.checkout_sku_limit){
                        var limitError=new Error('单次最多结算'+preview.checkout_sku_limit+'种商品，请减少勾选数量后分批结算');
                        limitError.data={error_code:'CHECKOUT_SKU_LIMIT'};throw limitError;
                    }
                    title.textContent='';message('');
                    var sum=preview.sku_list.reduce(function(total,row){return total+Math.round(Number(row.price)*100)*Number(row.count);},0);
                    amount.textContent='CNY '+(sum/100).toFixed(2);label('提交订单');
                }else{
                    checkoutId=params.get('checkout_id');
                    var data=checkoutId?await preparePayment():await api('/v1/orders/'+encodeURIComponent(user)+'?type=5&order_id='+encodeURIComponent(params.get('order_id')||''));
                    if(!active)return;
                    paymentReady(data,!!(checkoutId||data.payment_id||data.checkout_id));return;
                }
                ready=true;disable(false);clock();
            }catch(error){
                if(!active)return;if(!sameAccount()){discard();return;}
                showError(error);if(!finished)recover(error.message,'返回我的订单');disable(false);
            }
        }
        async function submit(event){
            event.preventDefault();if(pending||!active||redirected)return;
            if(!sameAccount()){discard();return;}
            if(finished){win.location.href=recoveryUrl;return;}
            if(!ready)return;
            if(payUrl){goPay();return;}
            pending=true;disable(true);message(checkoutId?'正在准备合并付款…':'正在提交订单…');
            try{
                if(checkoutId){
                    var prepared=await preparePayment();if(!active)return;
                    if(paymentReady(prepared,true))goPay();return;
                }
                var data=await api('/v1/orders/'+encodeURIComponent(user),{method:'POST',body:JSON.stringify(payload)});
                if(!active)return;
                var orders=data.orders;if(!Array.isArray(orders)||!orders.length)throw new Error('订单结果不完整，请使用原请求重试');
                renderOrders(orders);
                if(data.payment_mode==='combined'&&data.checkout_id){
                    checkoutId=data.checkout_id;message('订单已保存。一次付款，各店分别发货。');label('合并付款');
                    var savedTotal=data.checkout_total_amount,total=Number(savedTotal);
                    amount.textContent=savedTotal!==null&&savedTotal!==undefined&&String(savedTotal).trim()!==''&&Number.isFinite(total)&&total>=0?'CNY '+total.toFixed(2):'—';
                    startClock(data.checkout_expires_at);
                }else recover('订单已保存，请在我的订单中查看。');
            }catch(error){
                if(!active)return;if(!sameAccount()){discard();return;}showError(error);
            }finally{pending=false;if(active&&sameAccount()&&!redirected)disable(false);}
        }
        button.addEventListener('click',submit);button.addEventListener('keydown',function(event){if(event.key==='Enter'||event.key===' ')submit(event);});
        var form=button.closest('form');if(form)form.addEventListener('submit',function(e){e.preventDefault();});
        win.addEventListener('pagehide',function(){active=false;discard();});load();
    }
    return {requestId:requestId,remaining:remaining,mount:mount};
});
