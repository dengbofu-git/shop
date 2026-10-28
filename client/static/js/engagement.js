/* Shared, plain-text UI and authenticated same-origin transport. */
(function (root) {
    'use strict';
    var words = {
        zh: {orderReview:'订单商品评价', backOrders:'返回我的订单', messages:'消息中心', consultations:'买家咨询', reviews:'商品评价', myReviews:'我的评价', contact:'联系商家', pending:'待评价', review:'评价商品', viewReview:'查看评价',
            send:'发送', retry:'重试', loading:'正在加载…', empty:'暂无记录', choose:'请选择一个会话', draft:'发送第一条消息后保存会话', placeholder:'输入消息（最多 2000 字）',
            older:'更早消息', read:'已读', sent:'已发送', failed:'发送失败；重试会保留原发送标识', unread:'未读', previous:'上一页', next:'下一页', back:'返回工作台',
            text:'评价内容', stars:'商品评分', submit:'提交评价', close:'关闭', reply:'商家回复', report:'举报', reason:'原因（5～500 字）', saved:'已保存',
            all:'全部评价', current:'当前规格', latest:'最新', high:'评分从高到低', low:'评分从低到高', noReviews:'暂无评价', count:'条评价', score:'分',
            login:'请先登录', unavailable:'暂时无法加载，请重试', noPermission:'无权访问此功能', hidden:'此评价当前不公开', history:'历史订单购买信息尚未核验，暂不能执行此操作',
            notComplete:'订单完成后可评价', rated:'已经评价', reviewHint:'请填写 1～5 星评分和 5～1000 字评价。提交后不能修改。',
            replyHint:'最多 1000 字，每条评价回复一次。', moderation:'评价管理', hide:'隐藏评价', restore:'恢复公开', reports:'举报记录', audit:'处理记录',
            query:'搜索商品或评价内容', unreplied:'仅未回复', refresh:'刷新', allRatings:'全部星级', settings:'语言', buyer:'买家', product:'商品', order:'订单',
            gotoProduct:'查看商品', shop:'店铺', hiddenNotice:'从列表隐藏订单会保留交易与评价记录。', firstMessage:'向商家发送第一条消息，开始咨询。', sending:'正在发送…'},
        en: {orderReview:'Order item review', backOrders:'Back to my orders', messages:'Messages', consultations:'Buyer inquiries', reviews:'Product reviews', myReviews:'My reviews', contact:'Contact seller', pending:'To review', review:'Review product', viewReview:'View review',
            send:'Send', retry:'Retry', loading:'Loading…', empty:'No records yet', choose:'Select a conversation', draft:'Conversation is saved with your first message', placeholder:'Message (up to 2,000 characters)',
            older:'Older messages', read:'Read', sent:'Sent', failed:'Sending failed. Retry uses the same message ID.', unread:'Unread', previous:'Previous', next:'Next', back:'Back to workspace',
            text:'Review', stars:'Product rating', submit:'Submit review', close:'Close', reply:'Seller reply', report:'Report', reason:'Reason (5–500 characters)', saved:'Saved',
            all:'All reviews', current:'This variant', latest:'Latest', high:'Highest rating', low:'Lowest rating', noReviews:'No reviews yet', count:'reviews', score:'out of 5',
            login:'Please sign in', unavailable:'Unable to load. Please retry.', noPermission:'Access denied', hidden:'This review is not public', history:'This historical purchase has not been verified. This action is unavailable.',
            notComplete:'Review after the order is complete', rated:'Already reviewed', reviewHint:'Choose 1–5 stars and enter 5–1,000 characters. Reviews cannot be edited after submission.',
            replyHint:'Up to 1,000 characters. One reply per review.', moderation:'Review management', hide:'Hide review', restore:'Restore review', reports:'Reports', audit:'Moderation history',
            query:'Search products or reviews', unreplied:'Unreplied only', refresh:'Refresh', allRatings:'All ratings', settings:'Language', buyer:'Buyer', product:'Product', order:'Order',
            gotoProduct:'View product', shop:'Shop', hiddenNotice:'Hiding orders preserves purchases and reviews.', firstMessage:'Send your first message to contact this seller.', sending:'Sending…'},
        ar: {orderReview:'تقييم منتج الطلب', backOrders:'العودة إلى طلباتي', messages:'الرسائل', consultations:'استفسارات المشترين', reviews:'تقييمات المنتجات', myReviews:'تقييماتي', contact:'تواصل مع البائع', pending:'بانتظار التقييم', review:'تقييم المنتج', viewReview:'عرض التقييم',
            send:'إرسال', retry:'إعادة المحاولة', loading:'جارٍ التحميل…', empty:'لا توجد سجلات', choose:'اختر محادثة', draft:'تُحفظ المحادثة عند إرسال أول رسالة', placeholder:'اكتب رسالة (حتى 2000 حرف)',
            older:'رسائل أقدم', read:'مقروءة', sent:'أُرسلت', failed:'فشل الإرسال. تستخدم إعادة المحاولة المعرّف نفسه.', unread:'غير مقروءة', previous:'السابق', next:'التالي', back:'العودة إلى لوحة العمل',
            text:'نص التقييم', stars:'تقييم المنتج', submit:'إرسال التقييم', close:'إغلاق', reply:'رد البائع', report:'إبلاغ', reason:'السبب (5–500 حرف)', saved:'تم الحفظ',
            all:'كل التقييمات', current:'هذا الخيار', latest:'الأحدث', high:'الأعلى تقييماً', low:'الأقل تقييماً', noReviews:'لا توجد تقييمات بعد', count:'تقييمات', score:'من 5',
            login:'يرجى تسجيل الدخول', unavailable:'تعذر التحميل. حاول مجدداً.', noPermission:'الوصول غير مسموح', hidden:'هذا التقييم غير منشور', history:'لم يتم التحقق من بيانات الشراء القديمة. هذا الإجراء غير متاح.',
            notComplete:'يمكن التقييم بعد اكتمال الطلب', rated:'تم التقييم', reviewHint:'اختر 1–5 نجوم واكتب 5–1000 حرف. لا يمكن تعديل التقييم بعد إرساله.',
            replyHint:'حتى 1000 حرف. رد واحد لكل تقييم.', moderation:'إدارة التقييمات', hide:'إخفاء التقييم', restore:'إعادة النشر', reports:'البلاغات', audit:'سجل المعالجة',
            query:'ابحث في المنتجات أو التقييمات', unreplied:'دون رد فقط', refresh:'تحديث', allRatings:'كل النجوم', settings:'اللغة', buyer:'المشتري', product:'المنتج', order:'الطلب',
            gotoProduct:'عرض المنتج', shop:'المتجر', hiddenNotice:'إخفاء الطلب يحفظ بيانات الشراء والتقييمات.', firstMessage:'أرسل أول رسالة للتواصل مع البائع.', sending:'جارٍ الإرسال…'}
    };
    function language() {
        var key = document.body && document.body.dataset.engRole === 'merchant' ? 'supplier_lang' : 'buyer_lang';
        var value = localStorage.getItem(key) || document.documentElement.lang.split('-')[0];
        return words[value] ? value : 'zh';
    }
    function t(key) {
        var chats = {
            dragConversation:{zh:'按住拖动排序 · Alt+↑/↓ 调整位置', en:'Drag to reorder · Alt+↑/↓ to move', ar:'اسحب لإعادة الترتيب · Alt+↑/↓ للنقل'},
            conversationOrderSaved:{zh:'会话顺序已保存', en:'Conversation order saved', ar:'تم حفظ ترتيب المحادثات'},
            conversationOrderNotSaved:{zh:'顺序已调整，当前浏览器无法保存', en:'Order changed; browser storage is unavailable', ar:'تم تغيير الترتيب، لكن التخزين في المتصفح غير متاح'},
            conversationOrderLimit:{zh:'当前最多可记住200个会话的顺序', en:'Up to 200 conversations can have a saved order', ar:'يمكن حفظ ترتيب ما يصل إلى 200 محادثة'},
            conversationActions:{zh:'会话操作', en:'Conversation actions', ar:'خيارات المحادثة'},
            deleteConversation:{zh:'删除对话', en:'Delete conversation', ar:'حذف المحادثة'},
            conversationHidden:{zh:'对话已移出列表', en:'Conversation removed from the list', ar:'أُزيلت المحادثة من القائمة'},
            sendHint:{zh:'Enter 发送 · Shift+Enter 换行', en:'Enter to send · Shift+Enter for a new line', ar:'Enter للإرسال · Shift+Enter لسطر جديد'},
            buyerChats:{zh:'按商家分别沟通，消息自动保存，可随时继续咨询。', en:'Separate conversations with each seller. Messages are saved so you can return anytime.', ar:'محادثة مستقلة مع كل بائع. تُحفظ الرسائل للمتابعة في أي وقت.'},
            merchantChats:{zh:'按客户分别沟通，消息自动保存，选择会话即可回复。', en:'Separate conversations with each customer. Messages are saved; select a conversation to reply.', ar:'محادثة مستقلة مع كل عميل. تُحفظ الرسائل؛ اختر محادثة للرد.'},
            buyerChatWelcome:{zh:'好茶，值得聊一聊', en:'Good tea starts with a conversation', ar:'حديث طيب يبدأ مع الشاي'},
            emptyBuyerChats:{zh:'遇见心仪的茶，去商品详情点「联系商家」，聊聊茶香、规格和采购细节。发出第一条消息，就能在这里续聊。', en:'Found a tea you like? Use Contact seller on its product detail page to talk about flavour, sizes and sourcing. Send your first message to keep the conversation here.', ar:'وجدت شاياً يعجبك؟ تواصل مع البائع من صفحة تفاصيل المنتج واسأل عن النكهة والمواصفات واحتياجات الشراء. أرسل رسالتك الأولى لتتابع الحديث هنا.'},
            emptyMerchantChats:{zh:'暂无客户咨询。客户发送消息后，会按客户分别显示在这里。', en:'No inquiries yet. Each customer conversation appears here when they send a message.', ar:'لا توجد استفسارات بعد. تظهر محادثة مستقلة لكل عميل عند إرسال رسالة.'},
            conversation:{zh:'会话', en:'Conversation', ar:'المحادثة'}
        };
        if (chats[key]) return chats[key][language()];
        if (key === 'noContext') return {zh:'暂无关联商品或订单', en:'No linked product or order', ar:'لا يوجد منتج أو طلب مرتبط'}[language()];
        if (key === 'save') return {zh:'提交', en:'Submit', ar:'إرسال'}[language()];
        if (key === 'completed') return {zh:'订单完成', en:'Order complete', ar:'اكتمل الطلب'}[language()];
        if (key === 'reviewHistory') return {zh:'历史订单缺少已核验的购买信息，暂不可评价。', en:'This historical purchase has not been verified and cannot be reviewed yet.', ar:'لم يتم التحقق من بيانات الشراء القديمة، ولا يمكن تقييمها حالياً.'}[language()];
        if (key === 'backList') return {zh:'返回会话列表', en:'Back to conversations', ar:'العودة إلى المحادثات'}[language()];
        return words[language()][key] || words.zh[key] || key;
    }
    function node(tag, text, cls) {
        var el = document.createElement(tag);
        if (text != null) el.textContent = text;
        if (cls) el.className = cls;
        return el;
    }
    function button(label, action) {
        var el = node('button', t(label)); el.type = 'button'; el.dataset.engText = label;
        if (action) el.addEventListener('click', action);
        return el;
    }
    function translate(scope) {
        (scope || document).querySelectorAll('[data-eng-text]').forEach(function (el) { el.textContent = t(el.dataset.engText); });
        (scope || document).querySelectorAll('[data-eng-placeholder]').forEach(function (el) { el.placeholder = t(el.dataset.engPlaceholder); });
    }
    async function api(path, body) {
        var token = typeof AuthStorage !== 'undefined' && AuthStorage.getToken();
        var response = await fetch('/v1/engagement/' + path, {method: body === undefined ? 'GET' : 'POST', cache:'no-store',
            headers: Object.assign({'Content-Type':'application/json'}, token ? {Authorization:'Bearer ' + token} : {}),
            body: body === undefined ? undefined : JSON.stringify(body)});
        var result;
        try { result = await response.json(); } catch (_) { throw new Error(t('unavailable')); }
        if (!response.ok) {
            var error = new Error(response.status === 401 ? t('login') : response.status === 403 ? t('noPermission') :
                result.error_code === 'HISTORY_NOT_VERIFIED' ? t('history') : language() === 'zh' ? result.error || t('unavailable') : t('unavailable'));
            error.code = result.error_code; error.status = response.status; throw error;
        }
        return result.data;
    }
    function id() {
        if (root.crypto && root.crypto.randomUUID) return root.crypto.randomUUID();
        return 'msg-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
    }
    function date(value) { return new Date(value).toLocaleString(language()); }
    function reviewCard(row) {
        var article = node('article', null, 'eng-review');
        var heading = node('div', null, 'eng-review-head');
        var stars = node('span', '★'.repeat(row.rating) + '☆'.repeat(5 - row.rating), 'eng-stars');
        stars.setAttribute('aria-label', t('stars') + ': ' + row.rating + ' / 5');
        heading.append(node('strong', row.buyer_name), stars, node('time', date(row.created_at)));
        article.append(heading);
        if (row.product_name) article.append(node('h3', row.product_name));
        article.append(node('p', row.specification, 'eng-muted'), node('p', row.text, 'eng-prose'));
        if (row.is_visible === false) article.append(node('p', t('hidden'), 'eng-status'));
        if (row.reply) {
            var reply = node('div', null, 'eng-reply');
            reply.append(node('strong', t('reply')), node('p', row.reply.text, 'eng-prose'), node('time', date(row.reply.created_at)));
            article.append(reply);
        }
        return article;
    }
    function pager(host, page, pages, change) {
        host.replaceChildren();
        var prev = button('previous', function () { change(page - 1); }); prev.disabled = page <= 1;
        var next = button('next', function () { change(page + 1); }); next.disabled = page >= pages;
        host.append(prev, node('span', page + ' / ' + pages), next);
    }
    function ask(label, minimum, maximum, perform) {
        var dialog = node('dialog', null, 'eng-dialog'), form = node('form'), area = node('textarea'), status = node('p', '', 'eng-status');
        var title = node('h2', t(label)); title.id = 'eng-dialog-title'; dialog.setAttribute('aria-labelledby', title.id);
        area.required = true; area.minLength = minimum; area.maxLength = maximum; area.rows = 5; area.setAttribute('aria-label', t(label));
        var save = button('save'); save.type = 'submit';
        form.append(title, area, status, save, button('close', function () { dialog.close(); }));
        form.addEventListener('submit', async function (event) {
            event.preventDefault(); save.disabled = true;
            try { await perform(area.value); dialog.close(); } catch (error) { status.textContent = error.message; } finally { save.disabled = false; }
        });
        dialog.append(form); dialog.addEventListener('close', function () { dialog.remove(); }); document.body.append(dialog); dialog.showModal(); area.focus();
    }
    function updateLanguage(lang, quiet) {
        localStorage.setItem(document.body.dataset.engRole === 'merchant' ? 'supplier_lang' : 'buyer_lang', lang);
        document.documentElement.lang = lang; document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
        translate(); if (!quiet) document.dispatchEvent(new CustomEvent('eng:language'));
    }
    root.Engagement = {t:t, node:node, button:button, translate:translate, api:api, id:id, date:date,
        reviewCard:reviewCard, pager:pager, ask:ask, language:language, updateLanguage:updateLanguage};
    document.addEventListener('DOMContentLoaded', function () {
        translate();
        document.querySelectorAll('[data-eng-lang]').forEach(function (el) { el.onclick = function () {
            var shellButton = document.querySelector('.lang-btn[data-lang="' + el.dataset.engLang + '"]');
            if (shellButton) shellButton.click(); else updateLanguage(el.dataset.engLang);
        }; });
        document.querySelectorAll('.lang-btn').forEach(function (el) { el.addEventListener('click', function () { setTimeout(function () { translate(); document.dispatchEvent(new CustomEvent('eng:language')); }, 0); }); });
    });
})(window);
