(function () {
    'use strict';
    var E = window.Engagement, role = document.body.dataset.engRole;
    var conversation = null, target = null, ids = new Set(), newest = 0, oldest = 0, synced = 0, listPage = 1;
    var generation = 0, busy = false, pending = null, timer = null, failures = 0, otherRead = 0;
    var shownContext = null, chatName = '', listGeneration = 0, loading = false, polling = false, composing = false;
    var list = document.getElementById('eng-conversations'), feed = document.getElementById('eng-messages');
    var form = document.getElementById('eng-compose'), area = document.getElementById('eng-message-text');
    var status = document.getElementById('eng-status'), layout = document.getElementById('eng-layout');
    var send = document.getElementById('eng-send'), older = document.getElementById('eng-older');
    function syncComposer() { send.disabled = area.disabled = busy || loading; }
    function rememberConversation() {
        if (!conversation) return;
        var url = new URL(location.href);
        ['sku_id', 'order_item_id', 'merchant_id'].forEach(function (key) { url.searchParams.delete(key); });
        url.searchParams.set('conversation_id', conversation);
        window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    }
    function chatTitle(name, id) {
        chatName = name || E.t('messages');
        var heading = document.getElementById('eng-chat-title'); delete heading.dataset.engText;
        heading.textContent = chatName + (id ? ' · #' + id : '');
    }
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
        var skuId = String(value.sku_id || '');
        var hasProduct = /^[1-9]\d*$/.test(skuId) && Number.isSafeInteger(Number(skuId));
        var el = E.node(hasProduct ? 'a' : 'div', null, 'eng-card');
        if (hasProduct) {
            el.href = '/product_details.html?skuid=' + encodeURIComponent(skuId);
            // Merchant conversations can run inside the workbench iframe.
            el.target = '_top';
        }
        el.append(E.node('strong', value.product_name || E.t('shop')));
        if (value.specification) el.append(E.node('small', value.specification));
        if (value.type === 'order') el.append(E.node('small', E.t('order') + ': ' + value.order_id));
        if (hasProduct) {
            var action = E.node('span', E.t('gotoProduct'), 'eng-card-action');
            action.dataset.engText = 'gotoProduct';
            el.append(action);
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
        rows.forEach(function (row) {
            if (ids.has(row.id)) return;
            ids.add(row.id); newest = Math.max(newest, row.id); oldest = oldest ? Math.min(oldest, row.id) : row.id;
            var el = E.node('article', null, 'eng-message' + (row.is_mine ? ' mine' : ''));
            el.dataset.messageId = row.id;
            if (row.context && row.context.type) { el.append(card(row.context)); if (!prepend) showContext(row.context); }
            el.append(E.node('p', row.text), E.node('small', E.date(row.created_at) + ' '));
            if (row.is_mine) { var receipt = E.node('small'); receipt.dataset.ownMessage = row.id; el.append(receipt); }
            var next = Array.from(feed.querySelectorAll('[data-message-id]')).find(function (item) {
                return Number(item.dataset.messageId) > row.id;
            });
            feed.insertBefore(el, next || null);
        });
        markDelivery();
    }
    async function markRead() {
        if (!conversation || loading || !synced || !layout.classList.contains('chat-open') || !active() || !document.hasFocus() || feed.scrollHeight - feed.scrollTop - feed.clientHeight > 80) return;
        await E.api('conversations/' + conversation + '/read', {message_id:synced});
    }
    async function loadList() {
        var request = ++listGeneration, page = listPage;
        var data;
        try { data = await E.api('conversations?page=' + page); }
        catch (error) { if (request !== listGeneration || page !== listPage) return null; throw error; }
        if (request !== listGeneration || page !== listPage) return null;
        E.updateLanguage(E.language(), true);
        document.querySelectorAll('[data-eng-unread]').forEach(function (el) { el.textContent = data.unread_total || ''; });
        list.replaceChildren();
        if (!data.items.length) {
            if (role === 'buyer') {
                var welcome = E.node('div', null, 'eng-chat-welcome');
                var tea = E.node('span', '🍵', 'eng-chat-welcome-icon'); tea.setAttribute('aria-hidden', 'true');
                welcome.append(tea, E.node('strong', E.t('buyerChatWelcome')), E.node('p', E.t('emptyBuyerChats')));
                list.append(welcome);
            } else list.append(E.node('p', E.t('emptyMerchantChats'), 'eng-muted'));
        }
        data.items.forEach(function (row) {
            var item = E.button('', function () { target = null; open(row.id, row.name).catch(showError); });
            delete item.dataset.engText;
            item.dataset.conversationId = row.id;
            item.setAttribute('aria-current', String(row.id === conversation));
            item.append(E.node('strong', row.name));
            item.append(E.node('small', E.t('conversation') + ' #' + row.id, 'eng-conversation-ref'));
            if (row.unread) item.append(E.node('span', row.unread, 'eng-badge'));
            item.append(E.node('small', row.last_text), E.node('small', E.date(row.updated_at)));
            list.append(item);
            if (row.id === conversation) { chatTitle(row.name, row.id); otherRead = Math.max(otherRead, row.other_read_id); markDelivery(); }
        });
        var pager = document.getElementById('eng-list-pager'); pager.hidden = data.pages <= 1;
        E.pager(pager, data.page, data.pages, function (page) { listPage = page; loadList().catch(showError); });
        return data;
    }
    function showError(error) { status.textContent = error.message; }
    async function open(id, name) {
        var current = ++generation;
        loading = true; syncComposer();
        conversation = id; ids.clear(); newest = 0; oldest = 0; synced = 0; pending = null; otherRead = 0;
        feed.replaceChildren(); older.hidden = true; older.disabled = false; form.hidden = true; layout.classList.add('chat-open');
        chatTitle(name, id);
        list.querySelectorAll('button[data-conversation-id]').forEach(function (item) {
            item.setAttribute('aria-current', String(Number(item.dataset.conversationId) === id));
        });
        showContext(target && target.context); status.textContent = E.t('loading');
        try {
            area.value = sessionStorage.getItem(draftKey()) || '';
            pending = JSON.parse(sessionStorage.getItem(draftKey() + ':pending') || 'null');
        } catch (_) { area.value = ''; pending = null; }
        if (!id) { loading = false; syncComposer(); form.hidden = false; status.textContent = E.t('firstMessage'); return; }
        try {
            var data = await E.api('conversations/' + id + '/messages');
            if (current !== generation) return;
            chatTitle(data.name || name, id); rememberConversation();
            otherRead = data.other_read_id; append(data.items); older.hidden = !data.has_more;
            synced = newest;
            loading = false; syncComposer(); form.hidden = false;
            feed.scrollTop = feed.scrollHeight; status.textContent = '';
            await markRead(); await loadList();
        } catch (error) { if (current === generation) showError(error); }
        finally { if (current === generation) { loading = false; syncComposer(); } }
    }
    async function poll() {
        clearTimeout(timer);
        if (polling) return;
        polling = true;
        var current = generation;
        try {
            if (active() && !busy && !loading) {
                var id = conversation;
                if (id && newest) {
                    var bottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
                    // A local send may overtake an incoming message; only advance the
                    // receive cursor after reading history from the server.
                    var data = await E.api('conversations/' + id + '/messages' + (synced ? '?after=' + synced : ''));
                    if (current === generation) {
                        otherRead = data.other_read_id; append(data.items);
                        data.items.forEach(function (row) { synced = Math.max(synced, row.id); });
                        if (bottom) feed.scrollTop = feed.scrollHeight;
                        await markRead();
                    }
                }
                await loadList(); failures = 0;
            }
        } catch (error) { if (current === generation) { failures++; showError(error); } }
        finally { polling = false; }
        timer = setTimeout(poll, Math.min(30000, 4000 * Math.pow(2, failures)));
    }
    form.addEventListener('submit', async function (event) {
        event.preventDefault(); if (busy || loading || form.hidden || !area.value.trim()) return;
        busy = true; syncComposer();
        var current = generation, originalKey = draftKey(), text = area.value.trim(), ref = references();
        if (!pending || pending.text !== text || JSON.stringify(pending.refs) !== JSON.stringify(ref)) pending = {text:text, refs:ref, id:E.id()};
        try { sessionStorage.setItem(originalKey + ':pending', JSON.stringify(pending)); } catch (_) { /* Id stays in memory. */ }
        var payload = Object.assign({text:text, request_id:pending.id}, ref);
        status.textContent = E.t('sending');
        try {
            var data = await E.api(conversation ? 'conversations/' + conversation + '/messages' : 'conversations', payload);
            try { sessionStorage.removeItem(originalKey); sessionStorage.removeItem(originalKey + ':pending'); } catch (_) { /* Draft is optional. */ }
            if (current !== generation) { await loadList(); return; }
            conversation = data.conversation_id; append([data.message]); area.value = ''; pending = null; target = null;
            chatTitle(chatName, conversation); rememberConversation();
            feed.scrollTop = feed.scrollHeight; status.textContent = ''; await loadList();
        } catch (error) { if (current === generation) status.textContent = error.message + '\n' + E.t('failed'); }
        finally { busy = false; syncComposer(); }
    });
    area.addEventListener('input', function () { try { sessionStorage.setItem(draftKey(), area.value); } catch (_) { /* Draft is optional. */ } });
    area.addEventListener('compositionstart', function () { composing = true; });
    area.addEventListener('compositionend', function () { composing = false; });
    area.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' || event.shiftKey || event.isComposing || composing || event.keyCode === 229) return;
        event.preventDefault();
        if (event.repeat || busy || loading || area.disabled || form.hidden || !area.value.trim()) return;
        // Use the same validated form submission as the Send button.
        form.requestSubmit(send);
    });
    older.addEventListener('click', async function () {
        var current = generation; older.disabled = true;
        try {
            var data = await E.api('conversations/' + conversation + '/messages?before=' + oldest);
            if (current !== generation) return;
            var height = feed.scrollHeight; append(data.items, true); feed.scrollTop += feed.scrollHeight - height; older.hidden = !data.has_more;
        } catch (error) { if (current === generation) showError(error); }
        finally { if (current === generation) older.disabled = false; }
    });
    document.getElementById('eng-back-list').onclick = function () { layout.classList.remove('chat-open'); };
    document.getElementById('eng-refresh').onclick = function () { if (conversation) open(conversation, chatName).catch(showError); else loadList().catch(showError); };
    feed.addEventListener('scroll', function () { markRead().catch(showError); });
    window.addEventListener('focus', function () { markRead().catch(showError); });
    document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
    document.addEventListener('eng:language', function () { markDelivery(); showContext(shownContext); loadList().catch(showError); });
    window.addEventListener('pagehide', function () { clearTimeout(timer); });
    (async function () {
        document.getElementById('eng-inbox-hint').dataset.engText = role === 'buyer' ? 'buyerChats' : 'merchantChats';
        document.getElementById('eng-page-title').dataset.engText = role === 'buyer' ? 'messages' : 'consultations';
        E.updateLanguage(E.language(), true);
        var me = await E.api('identity');
        if (me.portal !== role) { location.replace(me.portal === 'buyer' ? '/buyer_messages.html' : '/merchant_messages.html'); return; }
        var inbox = await loadList();
        var params = new URLSearchParams(location.search), query = new URLSearchParams();
        ['sku_id','order_item_id','merchant_id'].forEach(function (key) { if (params.has(key)) query.set(key, params.get(key)); });
        if (role === 'buyer' && query.toString()) {
            var data = await E.api('conversations/resolve?' + query);
            target = Object.assign(Object.fromEntries(query), {merchant_id:data.merchant_id, context:data.context});
            await open(data.conversation_id, data.merchant_name);
        } else if (params.has('conversation_id')) {
            var selected = inbox && inbox.items.find(function (row) { return row.id === Number(params.get('conversation_id')); });
            await open(Number(params.get('conversation_id')), selected && selected.name);
        }
        else if (inbox && inbox.items.length) await open(inbox.items[0].id, inbox.items[0].name);
        poll();
    })().catch(function (error) { showError(error); poll(); });
})();
