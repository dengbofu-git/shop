/* Merchant-owned facts only; missing workflows remain explicit placeholders. */
(function (global, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (global.document) {
        if (global.document.readyState === 'loading') global.document.addEventListener('DOMContentLoaded', function () { api.mount(global); });
        else api.mount(global);
    }
})(typeof window === 'undefined' ? {} : window, function () {
    'use strict';
    var words = {
        zh: {heading:'当前待办与动态', todos:'待处理事项', messages:'最近动态', handle:'去处理 →', noTasks:'无待处理', refresh:'刷新', loading:'正在加载…', failed:'加载失败，请重试', login:'登录已过期，请重新登录', forbidden:'需要商家账号',
            total:'（共 {n} 项）', basis:'覆盖全部待发货订单、待结算账单及未读咨询，咨询按会话计数。', source:'本店订单、物流当前记录与买家咨询；时间为记录更新或消息发送时间',
            unshipped:'待发货订单', settlement:'待结算账单', consultations:'未读咨询', product_review:'待审核商品', after_sales:'待处理售后', unavailable:'未接入', empty:'暂无消息记录',
            order:'订单', shipping:'物流', inquiry:'咨询', orderText:'订单 {id} · {status}', shippingText:'运单 {id} · {status}', closed:'已关闭', unknown:'未知状态', updated:'更新于 {time}',
            standard:['待付款','待发货','待收货','订单完成'], trial:['待付款','待发货','待收货','试用中','试用完成','退货中','已退货','订单完成'],
            presale:['待付定金','已付定金','待付尾款','待发货','待收货','订单完成','已取消'], logistics:['待发货','已发货','运输中','派送中','已签收','异常']},
        en: {heading:'Current tasks and activity', todos:'Action required', messages:'Recent activity', handle:'Handle →', noTasks:'All clear', refresh:'Refresh', loading:'Loading…', failed:'Could not load. Please retry.', login:'Please sign in again', forbidden:'Merchant account required',
            total:'({n} tasks)', basis:'All pending shipments, settlements and unread conversations, regardless of order date.', source:'Your orders, shipments and buyer inquiries. Times show record updates or messages sent.',
            unshipped:'Pending shipments', settlement:'Pending settlements', consultations:'Unread inquiries', product_review:'Products awaiting approval', after_sales:'After-sales requests', unavailable:'Not connected', empty:'No message records yet',
            order:'Order', shipping:'Shipping', inquiry:'Inquiry', orderText:'Order {id} · {status}', shippingText:'Shipment {id} · {status}', closed:'Closed', unknown:'Unknown status', updated:'Updated {time}',
            standard:['Unpaid','Awaiting shipment','Awaiting receipt','Completed'], trial:['Unpaid','Awaiting shipment','Awaiting receipt','In trial','Trial finished','Returning','Returned','Completed'],
            presale:['Deposit due','Deposit paid','Balance due','Awaiting shipment','Awaiting receipt','Completed','Cancelled'], logistics:['Awaiting shipment','Shipped','In transit','Out for delivery','Delivered','Exception']},
        ar: {heading:'المهام الحالية والنشاط', todos:'مهام تتطلب إجراء', messages:'آخر النشاطات', handle:'معالجة ←', noTasks:'لا مهام معلقة', refresh:'تحديث', loading:'جارٍ التحميل…', failed:'تعذر التحميل. يرجى المحاولة مجدداً.', login:'يرجى تسجيل الدخول مجدداً', forbidden:'يلزم حساب تاجر',
            total:'({n} مهام)', basis:'جميع الشحنات والتسويات المعلقة والمحادثات غير المقروءة، دون تقييد بتاريخ الطلب.', source:'طلباتك وشحناتك واستفسارات المشترين. الوقت لتحديث السجل أو إرسال الرسالة.',
            unshipped:'طلبات بانتظار الشحن', settlement:'تسويات معلقة', consultations:'استفسارات غير مقروءة', product_review:'منتجات بانتظار المراجعة', after_sales:'طلبات ما بعد البيع', unavailable:'غير متصل', empty:'لا توجد رسائل حالياً',
            order:'طلب', shipping:'شحن', inquiry:'استفسار', orderText:'الطلب {id} · {status}', shippingText:'الشحنة {id} · {status}', closed:'مغلق', unknown:'حالة غير معروفة', updated:'تم التحديث {time}',
            standard:['غير مدفوع','بانتظار الشحن','بانتظار الاستلام','مكتمل'], trial:['غير مدفوع','بانتظار الشحن','بانتظار الاستلام','قيد التجربة','انتهت التجربة','قيد الإرجاع','تم الإرجاع','مكتمل'],
            presale:['العربون مستحق','دفع العربون','الرصيد مستحق','بانتظار الشحن','بانتظار الاستلام','مكتمل','ملغى'], logistics:['بانتظار الشحن','تم الشحن','قيد النقل','قيد التسليم','تم التسليم','استثناء']}
    };
    function panelAllowed(panel) {
        return typeof panel === 'string' && /^(?:merchant_orders\.html(?:\?filter=unshipped)?|merchant_settlement\.html|merchant_messages\.html(?:\?conversation_id=[1-9]\d{0,17})?)$/.test(panel);
    }
    function createController(options) {
        var generation = 0;
        return {
            refresh: async function () {
                var current = ++generation, token = options.token();
                options.onState({status:'loading', token:token});
                if (!token) { options.onState({status:'error', reason:'login', token:token}); return; }
                try {
                    var data = await options.request(token);
                    if (current !== generation) return;
                    if (options.token() !== token) { options.onState({status:'error', reason:'login'}); return; }
                    if (!data || !data.todos || !Array.isArray(data.messages) || !Number.isInteger(data.total)) throw new Error('invalid');
                    options.onState({status:'ready', data:data, token:token});
                } catch (error) {
                    if (current !== generation) return;
                    options.onState({status:'error', reason:error.status === 401 ? 'login' : error.status === 403 ? 'forbidden' : 'failed', token:token});
                }
            },
            cancel: function () { generation++; }
        };
    }
    function renderMessage(doc, row, language) {
        var t = words[language] || words.zh, li = doc.createElement('li'), tag = doc.createElement('span'), link = doc.createElement('a');
        li.className = 'message-item'; tag.className = 'msg-tag' + (row.kind === 'order' ? ' warn' : row.kind === 'shipping' ? ' info' : '');
        tag.textContent = t[row.kind] || t.order; link.className = 'feed-message-link';
        if (panelAllowed(row.panel)) { link.href = row.panel; link.dataset.workbenchPanel = row.panel; }
        var text = doc.createElement('span'); text.className = 'msg-text';
        var states = t[row.kind === 'shipping' ? 'logistics' : row.order_type] || [];
        var state = row.kind === 'order' && row.order_type === 'standard' && row.status != null && Number(row.status) === 0 ? t.closed : states[Number(row.status) - 1] || t.unknown;
        text.textContent = row.kind === 'inquiry' ? row.text : (row.kind === 'shipping' ? t.shippingText : t.orderText)
            .replace('{id}', row.kind === 'shipping' ? row.tracking_number : row.order_id).replace('{status}', state);
        var time = doc.createElement('time'); time.className = 'feed-time'; time.dateTime = row.created_at;
        time.textContent = new Date(row.created_at).toLocaleString(language === 'ar' ? 'ar' : language === 'en' ? 'en' : 'zh-CN');
        link.append(text, time); li.append(tag, link); return li;
    }
    function mount(win) {
        var doc = win.document, root = doc.getElementById('merchant-workbench-feed');
        if (!root) return;
        var state = {status:'loading'}, button = doc.getElementById('workbench-feed-refresh'), timer;
        var token = function () { return win.AuthStorage && win.AuthStorage.getToken(); };
        function render(next) {
            state = next;
            var lang = doc.documentElement.lang.split('-')[0], t = words[lang] || words.zh;
            root.querySelectorAll('[data-workbench-text]').forEach(function (el) { el.textContent = t[el.dataset.workbenchText]; });
            var ready = state.status === 'ready' && state.token === token(), data = ready ? state.data : null;
            root.setAttribute('aria-busy', String(state.status === 'loading')); button.disabled = state.status === 'loading';
            ['unshipped','settlement','consultations'].forEach(function (key) {
                var n = data && data.todos[key], badge = doc.getElementById('todo-' + key);
                badge.textContent = Number.isInteger(n) && n >= 0 ? n : '—';
                var row = badge.parentElement;
                row.classList.toggle('is-clear', !!data && n === 0);
                var action = row.querySelector('.todo-action');
                if (action) action.textContent = data && n === 0 ? t.noTasks : t.handle;
            });
            doc.getElementById('todo-total-count').textContent = data ? t.total.replace('{n}', data.total) : state.status === 'loading' ? t.loading : '—';
            var list = doc.getElementById('workbench-message-list'); list.replaceChildren();
            if (data && data.messages.length) data.messages.slice(0, 5).forEach(function (row) { list.append(renderMessage(doc, row, lang)); });
            else { var empty = doc.createElement('li'); empty.className = 'feed-note'; empty.textContent = data ? t.empty : state.status === 'loading' ? t.loading : t[state.reason || 'failed']; list.append(empty); }
            doc.getElementById('workbench-feed-status').textContent = data ? t.updated.replace('{time}', new Date(data.generated_at).toLocaleTimeString()) : state.status === 'error' ? t[state.reason || 'failed'] : t.loading;
        }
        var controller = createController({token:token, onState:render, request:async function (auth) {
            var abort = new win.AbortController(), timeout = win.setTimeout(function () { abort.abort(); }, 12000);
            try {
                var response = await win.fetch('/v1/supplier/workbench-feed', {headers:{Authorization:'Bearer ' + auth}, cache:'no-store', signal:abort.signal});
                if (!response.ok) { var error = new Error('request'); error.status = response.status; throw error; }
                var body = await response.json(); if (body.code !== 200) throw new Error('envelope'); return body.data;
            } finally { win.clearTimeout(timeout); }
        }});
        button.addEventListener('click', controller.refresh);
        root.addEventListener('click', function (event) {
            var link = event.target.closest('a[data-workbench-panel]');
            if (link && root.contains(link) && panelAllowed(link.dataset.workbenchPanel)) {
                event.preventDefault(); doc.dispatchEvent(new win.CustomEvent('supplier:open-panel', {detail:{panel:link.dataset.workbenchPanel}}));
            }
        });
        new win.MutationObserver(function () { render(state); }).observe(doc.documentElement, {attributes:true, attributeFilter:['lang']});
        doc.addEventListener('visibilitychange', function () { if (!doc.hidden && root.offsetParent !== null) controller.refresh(); });
        doc.addEventListener('supplier:panel-changed', function (event) { if (event.detail.panel === 'dashboard') controller.refresh(); });
        win.addEventListener('pagehide', function () { controller.cancel(); win.clearInterval(timer); });
        win.addEventListener('pageshow', function (event) { if (event.persisted) { win.clearInterval(timer); start(); } });
        function start() { controller.refresh(); timer = win.setInterval(function () { if (!doc.hidden && root.offsetParent !== null) controller.refresh(); }, 60000); }
        start();
    }
    return {createController:createController, renderMessage:renderMessage, panelAllowed:panelAllowed, mount:mount};
});
