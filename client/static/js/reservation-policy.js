(function(){
    'use strict';
    var form=document.getElementById('reservation-policy');if(!form)return;
    var message=document.getElementById('reservation-policy-status'),button=form.querySelector('button');
    var fields=['max_unpaid_quantity','max_unpaid_amount','max_stock_percent'];
    var ttl=form.elements.ttl_seconds;ttl.value=900;ttl.readOnly=true;
    var token=AuthStorage.getToken();
    async function request(options){
        var response=await fetch('/v1/supplier/reservation-policy',Object.assign({headers:{Authorization:token,'Content-Type':'application/json'},cache:'no-store'},options));
        var data=await response.json();if(!response.ok||data.code!==200)throw new Error(data.error||'规则读取失败，请稍后重试');return data.data;
    }
    button.disabled=true;
    request().then(function(data){
        if(data.ttl_seconds!==900||data.ttl_editable!==false)throw new Error('平台统一15分钟预留尚未启用，请稍后刷新');
        fields.forEach(function(k){form.elements[k].value=data[k];});
        var note=document.getElementById('reservation-policy-ttl-note');
        if(note)note.textContent='平台统一预留15分钟（900秒），商家不可修改。'+(data.configured_ttl_seconds!=null?'历史店铺配置为'+data.configured_ttl_seconds+'秒，仅供记录，不决定当前预留时长。':'');
        button.disabled=false;
    }).catch(function(error){message.textContent=error.message;});
    form.addEventListener('submit',async function(event){event.preventDefault();if(button.disabled)return;button.disabled=true;
        try{if(AuthStorage.getToken()!==token)throw new Error('账号已改变，请刷新');var data={ttl_seconds:900};fields.forEach(function(k){data[k]=form.elements[k].value;});data.change_reason=form.elements.change_reason.value.trim();await request({method:'PUT',body:JSON.stringify(data)});message.textContent='规则已保存，变更依据已记录；仅影响新订单，已有预留不延期。';}
        catch(error){message.textContent=error.message;}finally{button.disabled=false;}
    });
})();
