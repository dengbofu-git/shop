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
        var pending=false,ready=false,finished=false,payUrl=null,deadline=null,timer=null;
        function label(text){button.textContent=text;button.setAttribute('role','button');button.tabIndex=0;}
        function disable(value){button.setAttribute('aria-disabled',String(value));button.style.opacity=value?'.55':'1';}
        async function api(path,options){
            if(!sameAccount())throw new Error('账号已改变，请重新打开结算页面');
            var response=await win.fetch(path,Object.assign({headers:{Authorization:token,'Content-Type':'application/json'},cache:'no-store'},options));
            var data=await response.json();
            if(!sameAccount())throw new Error('账号已改变，请重新打开结算页面');
            if(!response.ok||data.code!==200){var error=new Error(data.error||data.errmsg||'请求失败，请稍后重试');error.data=data;throw error;}
            return data.data;
        }
        function showError(error){status.textContent=error.message;var d=error.data||{};
            if(d.error_code==='BULK_CONFIRMATION_REQUIRED'&&d.sku_id){var a=doc.createElement('a');a.href='product_details.html?skuid='+encodeURIComponent(d.sku_id);a.textContent='查看商品并联系商家';status.append(' ',a);}
        }
        var identity=requestId(win.location.search,function(){return win.crypto.randomUUID();});
        if(mode==='create')win.history.replaceState(null,'',win.location.pathname+'?'+identity.query.toString());
        var payload={address_id:params.get('address_id'),settlement_type:params.get('settlement_type'),request_id:identity.id};
        if(payload.settlement_type==='1'){payload.sku_id=params.get('sku_id');payload.buy_count=params.get('buy_count');}
        function clock(){
            if(!deadline)return;
            var seconds=remaining(deadline,Date.now());
            var slot=doc.querySelector('.pay_leftTime');if(slot)slot.textContent='剩余付款时间 '+Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0')+'；刷新不会延长';
            if(!seconds){ready=false;disable(true);status.textContent='已到付款截止时间，请返回订单列表确认状态。';if(timer)win.clearInterval(timer);}
        }
        async function load(){
            disable(true);
            try{
                if(mode==='create'){
                    var query=new URLSearchParams({settlement_type:payload.settlement_type});
                    if(payload.sku_id){query.set('sku_id',payload.sku_id);query.set('buy_num',payload.buy_count);}
                    var preview=await api('/v1/orders/'+encodeURIComponent(user)+'/advance?'+query);
                    if(preview.reservation_checkout_version!==1)throw new Error('库存保护尚未启用，请稍后再结算');
                    title.textContent='确认采购并提交订单';status.textContent='提交后按商家分别生成订单并短时预留；超时自动释放，取消重下仍计入限制。';
                    var sum=preview.sku_list.reduce(function(total,row){return total+Math.round(Number(row.price)*100)*Number(row.count);},0);
                    amount.textContent='CNY '+(sum/100).toFixed(2);label('提交订单并预留库存');
                }else{
                    var data=await api('/v1/orders/'+encodeURIComponent(user)+'?type=5&order_id='+encodeURIComponent(params.get('order_id')||''));
                    if(!data.expires_at||!data.pay_url)throw new Error('该订单尚未启用库存保护，请联系商家');
                    payUrl=data.pay_url;deadline=data.expires_at;title.textContent='订单 '+data.order_id;amount.textContent='CNY '+Number(data.total_amount).toFixed(2);
                    status.textContent='仅支付平台确认的结果会更新订单状态。';label('前往支付平台');
                    timer=win.setInterval(clock,1000);
                }
                ready=true;disable(false);clock();
            }catch(error){showError(error);label('返回我的订单');finished=true;disable(false);}
        }
        async function submit(event){
            event.preventDefault();if(pending)return;
            if(finished){win.location.href='buyer_orders.html';return;}
            if(!ready||!sameAccount())return;
            if(mode==='pay'){if(remaining(deadline,Date.now())>0)win.location.href=payUrl;else clock();return;}
            pending=true;disable(true);status.textContent='正在核验库存并提交…';
            try{
                var data=await api('/v1/orders/'+encodeURIComponent(user),{method:'POST',body:JSON.stringify(payload)});
                var orders=data.orders;if(!Array.isArray(orders)||!orders.length)throw new Error('订单结果不完整，请使用原请求重试');
                list.replaceChildren();orders.forEach(function(order){var row=doc.createElement('p');var link=doc.createElement('a');
                    link.href='gopay.html?order_id='+encodeURIComponent(order.order_id);link.textContent=order.status===1?'去付款':'查看订单';
                    if(order.status!==1)link.href='buyer_orders.html';row.textContent='订单 '+order.order_id+' · CNY '+Number(order.total_amount).toFixed(2)+' ';row.append(link);list.append(row);
                });
                status.textContent='订单已保存。请分别付款；刷新本页不会重复预留或延长时限。';finished=true;label('查看我的订单');
            }catch(error){showError(error);}finally{pending=false;disable(false);}
        }
        button.addEventListener('click',submit);button.addEventListener('keydown',function(event){if(event.key==='Enter'||event.key===' ')submit(event);});
        var form=button.closest('form');if(form)form.addEventListener('submit',function(e){e.preventDefault();});
        win.addEventListener('pagehide',function(){if(timer)win.clearInterval(timer);});load();
    }
    return {requestId:requestId,remaining:remaining,mount:mount};
});
