/* Nickname is display data. It must never replace the login account or token. */
(function (global, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (global.document) global.NicknameEditor = api.mount(global);
})(typeof window === 'undefined' ? {} : window, function () {
    'use strict';
    var words = {
        zh:{label:'昵称',hint:'最多30个字符，可重名。用于咨询时展示；清空后显示默认脱敏名称，登录账号不变。',save:'保存昵称',loading:'正在加载昵称…',saving:'正在保存…',saved:'昵称已保存',cleared:'已恢复默认脱敏名称',invalid:'昵称最多30个字符，不能包含换行或控制字符',failed:'昵称保存失败，请重试',unavailable:'昵称信息无法加载，请刷新页面',disabled:'昵称功能尚未启用',login:'登录已过期，请重新登录'},
        en:{label:'Nickname',hint:'Up to 30 characters; duplicates allowed. Shown in conversations. Clear it to use the masked default. Your login account stays the same.',save:'Save nickname',loading:'Loading nickname…',saving:'Saving…',saved:'Nickname saved',cleared:'Masked default restored',invalid:'Use up to 30 characters without line breaks or control characters',failed:'Could not save nickname. Please retry.',unavailable:'Could not load nickname. Please reload.',disabled:'Nicknames are not enabled yet',login:'Please sign in again'},
        ar:{label:'الاسم المستعار',hint:'حتى 30 حرفاً، ويمكن تكراره. يظهر في المحادثات. امسحه لاستعادة الاسم الافتراضي المخفي. لا يتغير حساب تسجيل الدخول.',save:'حفظ الاسم المستعار',loading:'جارٍ تحميل الاسم المستعار…',saving:'جارٍ الحفظ…',saved:'تم حفظ الاسم المستعار',cleared:'تمت استعادة الاسم الافتراضي المخفي',invalid:'حتى 30 حرفاً دون أسطر جديدة أو محارف تحكم',failed:'تعذر حفظ الاسم. حاول مجدداً.',unavailable:'تعذر تحميل الاسم. أعد تحميل الصفحة.',disabled:'لم يتم تفعيل الأسماء المستعارة بعد',login:'يرجى تسجيل الدخول مجدداً'}
    };
    function normalized(value) {
        if (typeof value !== 'string') throw new Error('invalid');
        var name = value.trim();
        if (Array.from(name).length > 30 || /[\u0000-\u001f\u007f-\u009f]/.test(name)) throw new Error('invalid');
        return name;
    }
    function createController(options) {
        var saving = false, revision = 0;
        return {
            save: async function (value) {
                if (saving) return;
                var name, identity = options.identity(), current = ++revision;
                try {name = normalized(value);} catch (_) {options.onState({status:'error',message:'invalid'});return;}
                if (!identity.token || !identity.username) {options.onState({status:'error',message:'login'});return;}
                saving = true; options.onState({status:'saving'});
                try {
                    var response = await options.request(identity, name), now = options.identity();
                    if (current !== revision) return;
                    if (now.token !== identity.token || now.username !== identity.username) {options.onState({status:'error',message:'login'});return;}
                    if (!response || response.code !== 200 || !response.data || response.data.nickname !== name) throw new Error('failed');
                    options.onState({status:'saved',nickname:name,message:name ? 'saved' : 'cleared'});
                } catch (error) {
                    if (current === revision) options.onState({status:'error',message:error.status === 401 || error.status === 403 ? 'login' : 'failed'});
                } finally {saving = false;}
            },
            cancel: function () {revision++;saving=false;}
        };
    }
    function mount(win) {
        var doc = win.document, root = doc.getElementById('nickname-editor'); if (!root) return null;
        var input = doc.getElementById('pf-nickname'), button = doc.getElementById('nickname-save'), message = doc.getElementById('nickname-msg');
        var state = {status:'loading',message:'loading'}, ready = false;
        function identity() {return {username:win.AuthStorage.getUser(),token:win.AuthStorage.getToken()};}
        var owner = identity();
        function sameOwner() {var now=identity();return now.username===owner.username && now.token===owner.token;}
        function render(next) {
            state = next;
            var preference = doc.body.classList.contains('supplier-account-page') ? 'supplier_lang' : 'buyer_lang';
            var language = win.localStorage.getItem(preference) || doc.documentElement.lang.split('-')[0], t = words[language] || words.zh;
            root.querySelectorAll('[data-nickname-text]').forEach(function (node) {node.textContent=t[node.dataset.nicknameText];});
            var busy = state.status === 'loading' || state.status === 'saving';
            root.setAttribute('aria-busy',String(busy));button.disabled=input.disabled=busy || !ready;
            message.className='ba-msg' + (state.status === 'saved' ? ' ok' : state.status === 'error' ? ' err' : '');
            message.textContent=t[state.message || (state.status === 'saving' ? 'saving' : '')] || '';
            if (state.status === 'saved') input.value=state.nickname;
        }
        var controller = createController({identity:identity,onState:render,request:async function (account, nickname) {
            var abort = new win.AbortController(), timeout = win.setTimeout(function () {abort.abort();},12000);
            try {
                var response=await win.fetch('/v1/users/' + encodeURIComponent(account.username) + '/profile',{
                    method:'PATCH',headers:{Authorization:'Bearer ' + account.token,'Content-Type':'application/json'},
                    body:JSON.stringify({nickname:nickname}),cache:'no-store',signal:abort.signal});
                if(!response.ok){var error=new Error('request');error.status=response.status;throw error;}
                return await response.json();
            } finally {win.clearTimeout(timeout);}
        }});
        function saveNickname() {if(!sameOwner()){ready=false;render({status:'error',message:'login'});return;}controller.save(input.value);}
        button.addEventListener('click',saveNickname);
        input.addEventListener('keydown',function (event) {if(event.key === 'Enter'){event.preventDefault();if(!button.disabled)saveNickname();}});
        new win.MutationObserver(function () {render(state);}).observe(doc.documentElement,{attributes:true,attributeFilter:['lang']});
        win.addEventListener('pagehide',controller.cancel);
        render(state);
        return {
            load:function (value) {if(!sameOwner()){ready=false;render({status:'error',message:'login'});return;}if(typeof value !== 'string'){ready=false;render({status:'error',message:'disabled'});return;}input.value=value;ready=true;render({status:'ready'});},
            unavailable:function () {ready=false;render({status:'error',message:'unavailable'});}
        };
    }
    return {normalized:normalized,createController:createController,mount:mount};
});
