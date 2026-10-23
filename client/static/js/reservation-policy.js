(function(){
    'use strict';
    var form=document.getElementById('reservation-policy');if(!form)return;
    var message=document.getElementById('reservation-policy-status'),button=form.querySelector('button');
    var fields=['ttl_seconds','max_unpaid_quantity','max_unpaid_amount','max_stock_percent'];
    var token=AuthStorage.getToken();
    async function request(options){
        var response=await fetch('/v1/supplier/reservation-policy',Object.assign({headers:{Authorization:token,'Content-Type':'application/json'},cache:'no-store'},options));
        var data=await response.json();if(!response.ok||data.code!==200)throw new Error(data.error||'规则读取失败，请稍后重试');return data.data;
    }
    button.disabled=true;
    request().then(function(data){fields.forEach(function(k){form.elements[k].value=data[k];});button.disabled=false;}).catch(function(error){message.textContent=error.message;});
    form.addEventListener('submit',async function(event){event.preventDefault();if(button.disabled)return;button.disabled=true;
        try{if(AuthStorage.getToken()!==token)throw new Error('账号已改变，请刷新');var data={};fields.forEach(function(k){data[k]=form.elements[k].value;});await request({method:'PUT',body:JSON.stringify(data)});message.textContent='规则已保存，仅影响新订单，已有预留不延期。';}
        catch(error){message.textContent=error.message;}finally{button.disabled=false;}
    });
})();
