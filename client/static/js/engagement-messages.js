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
    var menu = document.getElementById('eng-conversation-menu'), hideButton = document.getElementById('eng-hide-conversation');
    var menuOwner = null, menuConversation = null, hiding = false;
    var dragging = null, suppressClickUntil = 0, orderedIds = [], pageOrders = {};
    var orderKey = 'tea_saas_conversation_order:' + role + ':' + AuthStorage.getUser();
    try {
        var storedOrder = JSON.parse(localStorage.getItem(orderKey) || '[]');
        if (Array.isArray(storedOrder)) orderedIds = Array.from(new Set(storedOrder.filter(function (id) {
            return Number.isSafeInteger(id) && id > 0;
        }))).slice(0, 200);
    } catch (_) { /* Invalid or unavailable storage falls back to recent messages. */ }
    function conversationItems() { return Array.from(list.querySelectorAll('button[data-conversation-id]')); }
    function canReorder() {
        var known = orderedIds.slice();
        for (var page = 1; page < listPage; page++) known = known.concat(pageOrders[page] || []);
        conversationItems().forEach(function (item) { known.push(Number(item.dataset.conversationId)); });
        if (new Set(known).size > 200) { status.textContent = E.t('conversationOrderLimit'); return false; }
        return true;
    }
    function positions() { return conversationItems().map(function (item) { return {item:item, top:item.getBoundingClientRect().top}; }); }
    function animateOrder(before) {
        before.forEach(function (entry) {
            var distance = entry.top - entry.item.getBoundingClientRect().top;
            if (distance && entry.item.animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                entry.item.animate([{transform:'translateY(' + distance + 'px)'}, {transform:'translateY(0)'}], {duration:180, easing:'ease-out'});
            }
        });
    }
    function saveOrder() {
        var visible = conversationItems().map(function (item) { return Number(item.dataset.conversationId); });
        // Keep this page in its existing global slot, including non-visible/hidden IDs.
        if (!orderedIds.length) {
            for (var page = 1; page < listPage; page++) orderedIds = orderedIds.concat(pageOrders[page] || []);
        }
        var first = orderedIds.findIndex(function (id) { return visible.includes(id); });
        var remaining = orderedIds.filter(function (id) { return !visible.includes(id); });
        var index = first < 0 ? remaining.length : first;
        orderedIds = remaining.slice(0, index).concat(visible, remaining.slice(index)).slice(0, 200);
        try { localStorage.setItem(orderKey, JSON.stringify(orderedIds)); status.textContent = E.t('conversationOrderSaved'); }
        catch (_) { status.textContent = E.t('conversationOrderNotSaved'); }
        ++listGeneration;
    }
    function finishDrag(commit) {
        if (!dragging) return;
        var state = dragging; dragging = null;
        state.item.classList.remove('eng-dragging'); list.classList.remove('eng-reordering');
        suppressClickUntil = Date.now() + 300;
        if (commit) saveOrder();
        else list.replaceChildren.apply(list, state.items);
    }
    list.addEventListener('dragover', function (event) {
        if (!dragging) return;
        event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
        var box = list.getBoundingClientRect();
        if (event.clientY < box.top + 36) list.scrollTop -= 12;
        else if (event.clientY > box.bottom - 36) list.scrollTop += 12;
    });
    list.addEventListener('drop', function (event) { if (dragging) { event.preventDefault(); finishDrag(true); } });
    document.addEventListener('dragover', function (event) { if (dragging) event.preventDefault(); });
    document.addEventListener('drop', function (event) {
        // Never insert the dragged ID into the composer or another text input.
        if (dragging && !list.contains(event.target)) { event.preventDefault(); finishDrag(false); }
    });
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && dragging) { event.preventDefault(); finishDrag(false); } });
    function closeMenu(restoreFocus) {
        var owner = menuOwner;
        menu.hidden = true; menuOwner = null; menuConversation = null;
        if (owner) { owner.setAttribute('aria-expanded', 'false'); if (restoreFocus && list.contains(owner)) owner.focus(); }
    }
    function openMenu(event, item, row, keyboard) {
        event.preventDefault();
        closeMenu(false);
        if (busy || hiding || dragging) return;
        menuOwner = item; menuConversation = row.id;
        menu.setAttribute('aria-label', E.t('conversationActions'));
        menu.hidden = false; item.setAttribute('aria-expanded', 'true');
        var rect = item.getBoundingClientRect(), box = menu.getBoundingClientRect();
        var x = keyboard ? rect.left + 12 : event.clientX;
        var y = keyboard ? rect.top + Math.min(rect.height, 48) : event.clientY;
        menu.style.left = Math.max(8, Math.min(x, window.innerWidth - box.width - 8)) + 'px';
        menu.style.top = Math.max(8, Math.min(y, window.innerHeight - box.height - 8)) + 'px';
        hideButton.focus();
    }
    function clearConversation() {
        ++generation; conversation = null; target = null; pending = null; loading = false;
        ids.clear(); newest = oldest = synced = otherRead = 0; shownContext = null; chatName = '';
        feed.replaceChildren(); document.getElementById('eng-context').replaceChildren();
        list.querySelectorAll('button[data-conversation-id]').forEach(function (item) { item.setAttribute('aria-current', 'false'); });
        form.hidden = true; older.hidden = true; area.value = ''; layout.classList.remove('chat-open');
        var heading = document.getElementById('eng-chat-title'); heading.dataset.engText = 'choose'; heading.textContent = E.t('choose');
        var url = new URL(location.href);
        ['conversation_id', 'sku_id', 'order_item_id', 'merchant_id'].forEach(function (key) { url.searchParams.delete(key); });
        window.history.replaceState(null, '', url.pathname + url.search + url.hash);
        syncComposer();
    }
    hideButton.addEventListener('click', async function () {
        if (!menuConversation || busy || hiding) return;
        var id = menuConversation;
        hiding = true; ++listGeneration; closeMenu(false); syncComposer();
        try {
            await E.api('conversations/' + id + '/hide', {});
            if (conversation === id) clearConversation();
            // The hide has succeeded even if the subsequent list refresh is offline.
            list.replaceChildren.apply(list, Array.from(list.children).filter(function (item) { return Number(item.dataset.conversationId) !== id; }));
            await loadList(); status.textContent = E.t('conversationHidden');
            var first = list.querySelectorAll('button[data-conversation-id]')[0];
            if (first) first.focus();
        } catch (error) { showError(error); }
        finally { hiding = false; syncComposer(); }
    });
    menu.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { event.preventDefault(); closeMenu(true); }
        else if (event.key === 'Tab') closeMenu(false);
        else if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Home' || event.key === 'End') {
            event.preventDefault(); hideButton.focus();
        }
    });
    document.addEventListener('pointerdown', function (event) { if (!menu.hidden && !menu.contains(event.target)) closeMenu(false); });
    list.addEventListener('scroll', function () { closeMenu(false); });
    window.addEventListener('resize', function () { closeMenu(false); });
    function syncComposer() { send.disabled = area.disabled = busy || loading || hiding; }
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
        try { data = await E.api('conversations?page=' + page + (orderedIds.length ? '&order=' + orderedIds.join(',') : '')); }
        catch (error) { if (request !== listGeneration || page !== listPage) return null; throw error; }
        if (request !== listGeneration || page !== listPage) return null;
        listPage = data.page;
        E.updateLanguage(E.language(), true);
        document.querySelectorAll('[data-eng-unread]').forEach(function (el) { el.textContent = data.unread_total || ''; });
        // Keep a focused context menu stable while background polling updates counts.
        if (!menu.hidden || dragging) return data;
        pageOrders[data.page] = data.items.map(function (row) { return row.id; });
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
            var item = E.button('', function () {
                if (dragging || Date.now() < suppressClickUntil) return;
                target = null; open(row.id, row.name).catch(showError);
            });
            delete item.dataset.engText;
            item.dataset.conversationId = row.id;
            item.draggable = true; item.title = E.t('dragConversation');
            item.addEventListener('dragstart', function (event) {
                if (hiding || !canReorder()) { event.preventDefault(); return; }
                closeMenu(false); ++listGeneration;
                dragging = {item:item, items:conversationItems()};
                item.classList.add('eng-dragging'); list.classList.add('eng-reordering');
                if (event.dataTransfer) { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', String(row.id)); }
            });
            item.addEventListener('dragover', function (event) {
                if (!dragging || dragging.item === item) return;
                event.preventDefault();
                var bounds = item.getBoundingClientRect(), before = positions();
                var items = conversationItems(), next = event.clientY > bounds.top + bounds.height / 2 ? items[items.indexOf(item) + 1] : item;
                if (next !== dragging.item) { list.insertBefore(dragging.item, next || null); animateOrder(before); }
            });
            item.addEventListener('dragend', function () { finishDrag(false); });
            item.setAttribute('aria-haspopup', 'menu'); item.setAttribute('aria-expanded', 'false');
            item.addEventListener('contextmenu', function (event) { openMenu(event, item, row, false); });
            item.addEventListener('keydown', function (event) {
                if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) openMenu(event, item, row, true);
                if (event.altKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown') && !hiding && !dragging) {
                    var items = conversationItems(), index = items.indexOf(item), before = positions();
                    var destination = event.key === 'ArrowUp' ? index - 1 : index + 1;
                    event.preventDefault();
                    if (destination < 0 || destination >= items.length) return;
                    if (!canReorder()) return;
                    list.insertBefore(item, event.key === 'ArrowUp' ? items[destination] : items[destination + 1] || null);
                    animateOrder(before); saveOrder(); item.focus();
                }
            });
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
        closeMenu(false);
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
        } catch (error) { if (current === generation) { if (error.code === 'CONVERSATION_HIDDEN') clearConversation(); showError(error); } }
        finally { if (current === generation) { loading = false; syncComposer(); } }
    }
    async function poll() {
        clearTimeout(timer);
        if (polling) return;
        polling = true;
        var current = generation;
        try {
            if (active() && !busy && !loading && !hiding) {
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
        } catch (error) { if (current === generation) { if (error.code === 'CONVERSATION_HIDDEN') clearConversation(); failures++; showError(error); } }
        finally { polling = false; }
        timer = setTimeout(poll, Math.min(30000, 4000 * Math.pow(2, failures)));
    }
    form.addEventListener('submit', async function (event) {
        event.preventDefault(); if (busy || loading || hiding || form.hidden || !area.value.trim()) return;
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
            if (data.conversation_id) await E.api('conversations/' + data.conversation_id + '/restore', {});
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
