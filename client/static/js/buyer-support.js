(function () {
    'use strict';
    var form = document.getElementById('bs-form');
    var input = document.getElementById('bs-input');
    var send = document.getElementById('bs-send');
    var messages = document.getElementById('bs-messages');
    var newConversation = document.getElementById('bs-new-conversation');
    var preferenceForm = document.getElementById('bs-preferences-form');
    var preferenceStatus = document.getElementById('bs-preference-status');
    var preferenceFields = {
        categories: document.getElementById('bs-pref-categories'),
        brands: document.getElementById('bs-pref-brands'),
        keywords: document.getElementById('bs-pref-keywords')
    };
    var labels = { recommendation: '商品推荐', recommendation_explanation: '推荐理由', question_answering: '咨询问答', product_details: '商品详情', after_sales: '售后服务', clarification: '补充信息', multi_intent: '多任务', unavailable: '其他问题' };
    var storageKey = 'support-conversation:' + (AuthStorage.getUser() || '');
    var conversation = null;
    var pending = null;
    var busy = false;
    var composing = false;
    var initialMessage = messages.innerHTML;
    var historyToggle = document.getElementById('bs-history-toggle');
    var historyPanel = document.getElementById('bs-history');
    var historyList = document.getElementById('bs-history-list');
    var historyStatus = document.getElementById('bs-history-status');
    var historyRefresh = document.getElementById('bs-history-refresh');
    var historyMore = document.getElementById('bs-history-more');
    var historyOlder = document.getElementById('bs-history-older');
    var currentLabel = document.getElementById('bs-current-conversation');
    var conversationStatus = document.getElementById('bs-conversation-status');
    var identityToken = AuthStorage.getToken();
    var identityUser = AuthStorage.getUser();
    var identityCleared = false;
    var historyCursor = null;
    var olderCursor = null;
    var historyLoaded = false;
    var restoreBlocked = false;
    var sessionTitle = '';
    var drafts = Object.create(null);

    function sameIdentity() {
        return identityToken === AuthStorage.getToken() && identityUser === AuthStorage.getUser();
    }

    function checkIdentity() {
        if (sameIdentity()) return;
        if (!identityCleared) {
            identityCleared = true;
            drafts = Object.create(null);
            conversation = pending = null;
            historyCursor = olderCursor = null;
            input.value = '';
            fillPreferences({});
            preferenceStatus.textContent = '登录账号已变化，请刷新页面后继续。';
            historyList.textContent = '';
            messages.innerHTML = initialMessage;
            sessionStorage.removeItem(storageKey);
            closeHistory();
            updateSession();
            conversationStatus.textContent = '登录账号已变化，请刷新页面后继续。';
            setBusy(true);
        }
        var error = new Error('登录账号已变化，请刷新页面后继续。');
        error.status = 401;
        throw error;
    }

    function ensureIdentity() {
        try { checkIdentity(); return true; }
        catch (error) { return false; }
    }

    async function api(path, method, data) {
        checkIdentity();
        var token = AuthStorage.getToken();
        if (!token) throw new Error('请先登录后再使用智能客服。');
        var response;
        try {
            response = await fetch('/v1/support/' + path, {
                method: method || 'GET',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: data === undefined ? undefined : JSON.stringify(data)
            });
        } catch (networkError) { checkIdentity(); throw networkError; }
        checkIdentity();
        var result;
        try { result = await response.json(); }
        catch (parseError) { checkIdentity(); throw new Error('服务响应异常，请稍后重试。'); }
        checkIdentity();
        if (!response.ok) {
            var error = new Error(result.error || '暂时无法回答，请稍后重试。');
            error.status = response.status;
            throw error;
        }
        return result;
    }

    function uuid() {
        var bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        var hex = Array.from(bytes, function (byte) { return byte.toString(16).padStart(2, '0'); }).join('');
        return hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' + hex.slice(16, 20) + '-' + hex.slice(20);
    }

    function setBusy(value) {
        busy = value || !sameIdentity();
        send.disabled = busy || restoreBlocked;
        newConversation.disabled = busy;
        historyToggle.disabled = busy;
        historyRefresh.disabled = busy;
        historyMore.disabled = busy;
        historyOlder.disabled = busy;
        historyList.querySelectorAll('button').forEach(function (button) { button.disabled = busy; });
    }

    function addMessage(text, kind, container) {
        var item = document.createElement('div');
        item.className = 'bs-message bs-' + kind;
        var body = document.createElement('div');
        var bubble = document.createElement('div');
        bubble.className = 'bs-bubble';
        bubble.textContent = text;
        body.appendChild(bubble);
        item.appendChild(body);
        (container || messages).appendChild(item);
        if (!container) messages.scrollTop = messages.scrollHeight;
        return bubble;
    }

    function showResult(bubble, result, historicalAt) {
        bubble.textContent = result.answer;
        var note = result.intents && result.intents.length ? result.intents.map(function (intent) { return labels[intent] || intent; }).join(' → ') : labels[result.intent] || '智能客服';
        if (result.pii_redacted) note += ' · 已脱敏';
        if (result.memory_used) note += ' · 使用了长期偏好';
        if (historicalAt) note += ' · 历史记录 · ' + displayTime(historicalAt) + ' · 价格、库存和状态可能已变化';
        var meta = document.createElement('small');
        meta.textContent = note;
        bubble.parentNode.appendChild(meta);
        if (result.knowledge_sources && result.knowledge_sources.length) {
            var sources = document.createElement('small');
            sources.className = 'bs-sources';
            sources.appendChild(document.createTextNode('参考资料：'));
            result.knowledge_sources.forEach(function (source, index) {
                try {
                    var sourceUrl = new URL(source.url);
                    if (sourceUrl.protocol !== 'https:') return;
                    if (index) sources.appendChild(document.createTextNode(' · '));
                    var link = document.createElement('a');
                    link.href = sourceUrl.href;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    link.textContent = source.title + (source.year ? ' (' + source.year + ')' : '');
                    sources.appendChild(link);
                } catch (error) {
                    // Ignore malformed source URLs in response data.
                }
            });
            bubble.parentNode.appendChild(sources);
        }
        if (result.recommendations && result.recommendations.length) {
            var cards = document.createElement('div');
            cards.className = 'bs-products';
            result.recommendations.forEach(function (product) {
                if (!Number.isInteger(product.sku_id) || product.sku_id <= 0) return;
                var card = document.createElement('a');
                card.className = 'bs-product';
                card.href = '/product_details.html?skuid=' + product.sku_id;
                var image = document.createElement('img');
                image.src = '/v1/goods/sku/' + product.sku_id + '/image';
                image.alt = product.product_name || product.name;
                image.loading = 'lazy';
                card.appendChild(image);
                var info = document.createElement('div');
                var title = document.createElement('strong');
                title.textContent = product.product_name || product.name;
                info.appendChild(title);
                if (product.product_name && product.name && product.name !== product.product_name) {
                    var specification = document.createElement('p');
                    specification.textContent = product.name;
                    info.appendChild(specification);
                }
                var price = document.createElement('p');
                price.textContent = 'USD $' + product.price + ' · ' + product.category;
                info.appendChild(price);
                var reason = document.createElement('p');
                reason.textContent = (product.reasons || []).join('、');
                info.appendChild(reason);
                card.appendChild(info);
                cards.appendChild(card);
            });
            bubble.parentNode.appendChild(cards);
        }
    }

    function displayTime(value) {
        var date = new Date(value);
        return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { hour12: false });
    }

    function closeHistory() {
        historyPanel.hidden = true;
        historyToggle.setAttribute('aria-expanded', 'false');
    }

    function updateSession() {
        currentLabel.textContent = conversation ? '当前咨询：' + (sessionTitle || '历史咨询') : '当前：新咨询';
        historyOlder.hidden = !conversation || !olderCursor;
        historyOlder.parentNode.hidden = historyOlder.hidden;
        historyList.querySelectorAll('[data-conversation-id]').forEach(function (button) {
            if (conversation && button.dataset.conversationId === conversation.conversation_id) button.setAttribute('aria-current', 'true');
            else button.removeAttribute('aria-current');
        });
    }

    function saveDraft() {
        drafts[conversation ? conversation.conversation_id : 'new'] = { text: input.value, pending: pending };
    }

    function renderTurns(turns, prepend) {
        var fragment = document.createDocumentFragment();
        turns.forEach(function (turn) {
            addMessage(turn.message, 'user', fragment);
            showResult(addMessage('', 'assistant', fragment), turn.response, turn.created_at || 'unknown');
        });
        if (prepend) messages.insertBefore(fragment, messages.firstChild);
        else messages.appendChild(fragment);
    }

    async function loadConversation(id) {
        var result = await api('conversations/' + encodeURIComponent(id) + '/?limit=20');
        saveDraft();
        conversation = { conversation_id: result.conversation_id, revision: result.revision };
        sessionTitle = result.title;
        var draft = drafts[result.conversation_id];
        input.value = draft ? draft.text : '';
        pending = draft ? draft.pending : null;
        sessionStorage.setItem(storageKey, JSON.stringify(conversation));
        olderCursor = result.next_before_sequence || null;
        restoreBlocked = false;
        messages.innerHTML = result.turns.length ? '' : initialMessage;
        renderTurns(result.turns, false);
        updateSession();
        conversationStatus.textContent = '已打开历史咨询；旧回复仅供回看，可继续提问。';
        messages.scrollTop = messages.scrollHeight;
    }

    async function switchConversation(id) {
        if (busy || !ensureIdentity()) return;
        setBusy(true);
        historyStatus.textContent = '正在打开咨询…';
        try {
            await loadConversation(id);
            closeHistory();
            input.focus();
        } catch (error) {
            historyStatus.textContent = error.message || '咨询加载失败，请重试。';
        } finally { setBusy(false); }
    }

    async function loadHistory(reset) {
        if (busy || !ensureIdentity()) return;
        setBusy(true);
        historyList.setAttribute('aria-busy', 'true');
        historyStatus.textContent = '正在加载历史咨询…';
        try {
            var path = 'conversations/?limit=20' + (!reset && historyCursor ? '&cursor=' + encodeURIComponent(historyCursor) : '');
            var result = await api(path);
            if (reset) historyList.textContent = '';
            result.conversations.forEach(function (item) {
                if (Array.from(historyList.children).some(function (row) { return row.dataset.conversationId === item.conversation_id; })) return;
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'bs-history-item';
                button.dataset.conversationId = item.conversation_id;
                var title = document.createElement('strong');
                title.textContent = item.title;
                var detail = document.createElement('small');
                detail.textContent = displayTime(item.updated_at) + ' · ' + item.turn_count + ' 轮';
                button.appendChild(title);
                button.appendChild(detail);
                button.addEventListener('click', function () { switchConversation(item.conversation_id); });
                historyList.appendChild(button);
            });
            historyCursor = result.next_cursor || null;
            historyMore.hidden = !historyCursor;
            historyLoaded = true;
            historyStatus.textContent = historyList.children.length ? '按最近更新时间排序，点击咨询可继续聊天。' : '还没有已保存的咨询，发送第一条消息后会自动保存。';
            updateSession();
        } catch (error) {
            historyStatus.textContent = error.message || '历史咨询加载失败，请刷新列表重试。';
        } finally {
            historyList.setAttribute('aria-busy', 'false');
            setBusy(false);
        }
    }

    async function loadOlder() {
        if (busy || !ensureIdentity() || !conversation || !olderCursor) return;
        setBusy(true);
        var previousHeight = messages.scrollHeight;
        var previousTop = messages.scrollTop;
        conversationStatus.textContent = '正在加载更早记录…';
        try {
            var result = await api('conversations/' + encodeURIComponent(conversation.conversation_id) + '/?limit=20&before_sequence=' + olderCursor);
            renderTurns(result.turns, true);
            olderCursor = result.next_before_sequence || null;
            updateSession();
            messages.scrollTop = previousTop + messages.scrollHeight - previousHeight;
            conversationStatus.textContent = olderCursor ? '已加载更早记录，可继续向前查看。' : '已显示该咨询的全部记录。';
            // Loading older pages does not advance the revision of the latest
            // messages shown here; an external update must still cause 409.
        } catch (error) {
            conversationStatus.textContent = error.message || '更早记录加载失败，请重试。';
        } finally { setBusy(false); }
    }

    async function restoreConversation() {
        var saved;
        try { saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null'); }
        catch (error) { sessionStorage.removeItem(storageKey); return; }
        if (!saved || !saved.conversation_id) return;
        try {
            await loadConversation(saved.conversation_id);
        } catch (error) {
            if (error.status === 404 || error.status === 401) {
                sessionStorage.removeItem(storageKey);
                conversation = null;
                restoreBlocked = false;
            } else {
                restoreBlocked = true;
                conversationStatus.textContent = '原咨询尚未恢复，请从历史咨询重新打开，或明确开始新对话。';
            }
            throw error;
        }
    }

    input.addEventListener('compositionstart', function () { composing = true; });
    input.addEventListener('compositionend', function () { composing = false; });
    input.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' || event.shiftKey || composing || event.isComposing || event.keyCode === 229) return;
        event.preventDefault();
        if (busy || restoreBlocked || event.repeat) return;
        form.requestSubmit(send);
    });

    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        var question = input.value.trim();
        if (busy || restoreBlocked || !question) return;
        try { checkIdentity(); }
        catch (error) { return; }
        if (!AuthStorage.getToken()) { addMessage('请先登录后再使用智能客服。', 'assistant'); return; }
        setBusy(true);
        input.value = '';
        addMessage(question, 'user');
        var waiting = addMessage('正在整理回复，请稍候…', 'assistant');
        try {
            if (!pending || pending.message !== question) {
                pending = { message: question, request_id: uuid() };
                if (conversation) {
                    pending.conversation_id = conversation.conversation_id;
                    pending.expected_revision = conversation.revision;
                }
            }
            var result = await api('chat/', 'POST', pending);
            if (!conversation) sessionTitle = question.replace(/\s+/g, ' ').slice(0, 60);
            conversation = { conversation_id: result.conversation_id, revision: result.revision };
            sessionStorage.setItem(storageKey, JSON.stringify(conversation));
            pending = null;
            showResult(waiting, result);
            updateSession();
            conversationStatus.textContent = '咨询已保存，可在“历史咨询”中找回。';
            historyLoaded = false;
        } catch (error) {
            if (!sameIdentity()) return;
            waiting.textContent = error.message || '网络连接失败，请稍后重试。';
            input.value = question;
            if (error.status === 409) {
                pending = null;
                try { await restoreConversation(); addMessage('会话已刷新，请重新发送问题。', 'assistant'); }
                catch (restoreError) { addMessage(restoreError.message, 'assistant'); }
            }
        } finally {
            setBusy(false);
            input.focus();
            messages.scrollTop = messages.scrollHeight;
            if (!historyPanel.hidden && !historyLoaded && sameIdentity()) loadHistory(true);
        }
    });

    newConversation.addEventListener('click', function () {
        if (busy || !ensureIdentity()) return;
        saveDraft();
        conversation = null;
        pending = null;
        restoreBlocked = false;
        sessionStorage.removeItem(storageKey);
        messages.innerHTML = initialMessage;
        sessionTitle = '';
        olderCursor = null;
        input.value = '';
        delete drafts.new;
        updateSession();
        conversationStatus.textContent = '已开启新咨询，旧咨询仍可从“历史咨询”进入。';
        historyLoaded = false;
        input.focus();
        if (!historyPanel.hidden) loadHistory(true);
    });

    historyToggle.addEventListener('click', function () {
        if (busy || !ensureIdentity()) return;
        if (!historyPanel.hidden) { closeHistory(); return; }
        historyPanel.hidden = false;
        historyToggle.setAttribute('aria-expanded', 'true');
        if (!historyLoaded) loadHistory(true);
    });
    historyRefresh.addEventListener('click', function () { loadHistory(true); });
    historyMore.addEventListener('click', function () { if (historyCursor) loadHistory(false); });
    historyOlder.addEventListener('click', loadOlder);
    historyPanel.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { closeHistory(); historyToggle.focus(); }
    });
    window.addEventListener('storage', function () {
        if (!sameIdentity()) { try { checkIdentity(); } catch (error) { /* Page awaits refresh. */ } }
    });

    function fillPreferences(values) {
        Object.keys(preferenceFields).forEach(function (field) {
            preferenceFields[field].value = (values[field] || []).join('，');
        });
    }

    async function updatePreferences(method) {
        var values = {};
        Object.keys(preferenceFields).forEach(function (field) {
            values[field] = preferenceFields[field].value.split(/[,，\n]/).map(function (term) { return term.trim(); }).filter(Boolean);
        });
        var buttons = preferenceForm.querySelectorAll('button');
        buttons.forEach(function (button) { button.disabled = true; });
        try {
            var result = await api('preferences/', method, method === 'DELETE' ? undefined : values);
            fillPreferences(result.preferences);
            preferenceStatus.textContent = method === 'DELETE' ? '长期偏好已清除。' : '长期偏好已保存。';
        } catch (error) { preferenceStatus.textContent = error.message; }
        finally { buttons.forEach(function (button) { button.disabled = false; }); }
    }
    preferenceForm.addEventListener('submit', function (event) { event.preventDefault(); updatePreferences('PUT'); });
    document.getElementById('bs-clear-preferences').addEventListener('click', function () { updatePreferences('DELETE'); });
    document.querySelectorAll('.bs-suggestions button').forEach(function (button) {
        button.addEventListener('click', function () { input.value = button.getAttribute('data-question') || ''; input.focus(); });
    });

    if (AuthStorage.getToken()) {
        setBusy(true);
        restoreConversation().catch(function (error) { addMessage(error.message, 'assistant'); }).finally(function () { setBusy(false); });
        api('preferences/').then(function (result) { fillPreferences(result.preferences); })
            .catch(function (error) { preferenceStatus.textContent = error.message; });
    }
    updateSession();
})();
