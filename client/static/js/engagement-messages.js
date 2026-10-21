(function () {
    'use strict';
    var E = window.Engagement, role = document.body.dataset.engRole;
    var conversation = null, target = null, ids = new Set(), newest = 0, oldest = 0, listPage = 1;
    var generation = 0, busy = false, pending = null, timer = null, failures = 0, otherRead = 0;
    var shownContext = null;
    var list = document.getElementById('eng-conversations'), feed = document.getElementById('eng-messages');
    var form = document.getElementById('eng-compose'), area = document.getElementById('eng-message-text');
    var status = document.getElementById('eng-status'), layout = document.getElementById('eng-layout');
    var send = document.getElementById('eng-send'), older = document.getElementById('eng-older');
    function active() {
        return !document.hidden && (!window.frameElement || getComputedStyle(window.frameElement).display !== 'none');
    }
    function draftKey() { return 'tea_saas_message_draft:' + AuthStorage.getUser() + ':' + (target ? JSON.stringify(references()) : conversation || 'inbox'); }
    function references() {
        if (!target) return {};
        if (target.order_item_id) return {order_item_id:target.order_item_id};
        if (target.sku_id) return {sku_id:target.sku_id};
        return {merchant_id:target.merchant_id};
    }
    function card(value) {
        var el = E.node('div', null, 'eng-card');
        el.append(E.node('strong', value.product_name || E.t('shop')));
        if (value.specification) el.append(E.node('small', value.specification));
        if (value.type === 'order') el.append(E.node('small', E.t('order') + ': ' + value.order_id));
        if (value.sku_id) {
            var link = E.node('a', E.t('gotoProduct'));
            link.href = '/product_details.html?skuid=' + encodeURIComponent(value.sku_id);
            if (role === 'buyer') el.append(link);
        }
        return el;
    }
    function showContext(value) {
        shownContext = value;
        var host = document.getElementById('eng-context'); host.replaceChildren();
        if (value && value.type) host.append(card(value));
        else host.append(E.node('p', E.t(conversation ? 'noContext' : 'draft'), 'eng-muted'));
    }
    function markDelivery() {
        feed.querySelectorAll('[data-own-message]').forEach(function (el) {
            el.textContent = E.t(Number(el.dataset.ownMessage) <= otherRead ? 'read' : 'sent');
        });
    }
    function append(rows, prepend) {
        var fragment = document.createDocumentFragment();
        rows.forEach(function (row) {
            if (ids.has(row.id)) return;
            ids.add(row.id); newest = Math.max(newest, row.id); oldest = oldest ? Math.min(oldest, row.id) : row.id;
            var el = E.node('article', null, 'eng-message' + (row.is_mine ? ' mine' : ''));
            if (row.context && row.context.type) { el.append(card(row.context)); if (!prepend) showContext(row.context); }
            el.append(E.node('p', row.text), E.node('small', E.date(row.created_at) + ' '));
            if (row.is_mine) { var receipt = E.node('small'); receipt.dataset.ownMessage = row.id; el.append(receipt); }
            fragment.append(el);
        });
        if (prepend) feed.prepend(fragment); else feed.append(fragment);
        markDelivery();
    }
    async function markRead() {
        if (!conversation || !newest || !active() || !document.hasFocus() || feed.scrollHeight - feed.scrollTop - feed.clientHeight > 80) return;
        await E.api('conversations/' + conversation + '/read', {message_id:newest});
    }
    async function loadList() {
        var data = await E.api('conversations?page=' + listPage);
        document.querySelectorAll('[data-eng-unread]').forEach(function (el) { el.textContent = data.unread_total || ''; });
        list.replaceChildren();
        if (!data.items.length) list.append(E.node('p', E.t('empty'), 'eng-muted'));
        data.items.forEach(function (row) {
            var item = E.button('', function () { target = null; open(row.id, row.name).catch(showError); });
            delete item.dataset.engText;
            item.setAttribute('aria-current', String(row.id === conversation));
            item.append(E.node('strong', row.name));
            if (row.unread) item.append(E.node('span', row.unread, 'eng-badge'));
            item.append(E.node('small', row.last_text), E.node('small', E.date(row.updated_at)));
            list.append(item);
            if (row.id === conversation) { otherRead = row.other_read_id; markDelivery(); }
        });
        E.pager(document.getElementById('eng-list-pager'), data.page, data.pages, function (page) { listPage = page; loadList().catch(showError); });
    }
    function showError(error) { status.textContent = error.message; }
    async function open(id, name) {
        var current = ++generation;
        conversation = id; ids.clear(); newest = 0; oldest = 0; pending = null; otherRead = 0;
        feed.replaceChildren(); older.hidden = true; form.hidden = false; layout.classList.add('chat-open');
        var heading = document.getElementById('eng-chat-title'); delete heading.dataset.engText;
        heading.textContent = name || E.t('messages');
        showContext(target && target.context); status.textContent = E.t('loading');
        try {
            area.value = sessionStorage.getItem(draftKey()) || '';
            pending = JSON.parse(sessionStorage.getItem(draftKey() + ':pending') || 'null');
        } catch (_) { area.value = ''; pending = null; }
        if (!id) { status.textContent = E.t('firstMessage'); return; }
        var data = await E.api('conversations/' + id + '/messages');
        if (current !== generation) return;
        otherRead = data.other_read_id; append(data.items); older.hidden = !data.has_more;
        feed.scrollTop = feed.scrollHeight; status.textContent = '';
        await markRead(); await loadList();
    }
    async function poll() {
        clearTimeout(timer);
        try {
            if (active() && !busy) {
                var current = generation, id = conversation;
                if (id && newest) {
                    var bottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
                    var data = await E.api('conversations/' + id + '/messages?after=' + newest);
                    if (current === generation) {
                        otherRead = data.other_read_id; append(data.items);
                        if (bottom) feed.scrollTop = feed.scrollHeight;
                        await markRead();
                    }
                }
                await loadList(); failures = 0;
            }
        } catch (error) { failures++; showError(error); }
        timer = setTimeout(poll, Math.min(30000, 4000 * Math.pow(2, failures)));
    }
    form.addEventListener('submit', async function (event) {
        event.preventDefault(); if (busy || !area.value.trim()) return;
        busy = true; send.disabled = true; area.disabled = true;
        var current = generation, originalKey = draftKey(), text = area.value.trim(), ref = references();
        if (!pending || pending.text !== text || JSON.stringify(pending.refs) !== JSON.stringify(ref)) pending = {text:text, refs:ref, id:E.id()};
        try { sessionStorage.setItem(originalKey + ':pending', JSON.stringify(pending)); } catch (_) { /* Id stays in memory. */ }
        var payload = Object.assign({text:text, request_id:pending.id}, ref);
        status.textContent = E.t('sending');
        try {
            var data = await E.api(conversation ? 'conversations/' + conversation + '/messages' : 'conversations', payload);
            try { sessionStorage.removeItem(originalKey); sessionStorage.removeItem(originalKey + ':pending'); } catch (_) { /* Draft is optional. */ }
            if (current !== generation) return;
            conversation = data.conversation_id; append([data.message]); area.value = ''; pending = null; target = null;
            feed.scrollTop = feed.scrollHeight; status.textContent = ''; await loadList();
        } catch (error) { status.textContent = error.message + '\n' + E.t('failed'); }
        finally { busy = false; send.disabled = false; area.disabled = false; }
    });
    area.addEventListener('input', function () { try { sessionStorage.setItem(draftKey(), area.value); } catch (_) { /* Draft is optional. */ } });
    older.addEventListener('click', async function () {
        var current = generation; older.disabled = true;
        try {
            var data = await E.api('conversations/' + conversation + '/messages?before=' + oldest);
            if (current !== generation) return;
            var height = feed.scrollHeight; append(data.items, true); feed.scrollTop += feed.scrollHeight - height; older.hidden = !data.has_more;
        } catch (error) { showError(error); } finally { older.disabled = false; }
    });
    document.getElementById('eng-back-list').onclick = function () { layout.classList.remove('chat-open'); };
    document.getElementById('eng-refresh').onclick = function () { if (conversation) open(conversation, document.getElementById('eng-chat-title').textContent).catch(showError); else loadList().catch(showError); };
    feed.addEventListener('scroll', function () { markRead().catch(showError); });
    window.addEventListener('focus', function () { markRead().catch(showError); });
    document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
    document.addEventListener('eng:language', function () { markDelivery(); showContext(shownContext); loadList().catch(showError); });
    window.addEventListener('pagehide', function () { clearTimeout(timer); });
    (async function () {
        E.updateLanguage(E.language(), true);
        var me = await E.api('identity');
        if (me.portal !== role) { location.replace(me.portal === 'buyer' ? '/buyer_messages.html' : '/merchant_messages.html'); return; }
        await loadList();
        var params = new URLSearchParams(location.search), query = new URLSearchParams();
        ['sku_id','order_item_id','merchant_id'].forEach(function (key) { if (params.has(key)) query.set(key, params.get(key)); });
        if (role === 'buyer' && query.toString()) {
            var data = await E.api('conversations/resolve?' + query);
            target = Object.assign(Object.fromEntries(query), {merchant_id:data.merchant_id, context:data.context});
            await open(data.conversation_id, data.merchant_name);
        } else if (params.has('conversation_id')) await open(Number(params.get('conversation_id')));
        poll();
    })().catch(function (error) { showError(error); poll(); });
})();
