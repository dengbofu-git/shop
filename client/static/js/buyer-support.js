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
    var labels = { recommendation: '商品推荐', question_answering: '咨询问答', after_sales: '售后服务', unavailable: '其他问题' };
    var storageKey = 'support-conversation:' + (AuthStorage.getUser() || '');
    var conversation = null;
    var pending = null;
    var busy = false;
    var initialMessage = messages.innerHTML;

    async function api(path, method, data) {
        var token = AuthStorage.getToken();
        if (!token) throw new Error('请先登录后再使用智能客服。');
        var response = await fetch('/v1/support/' + path, {
            method: method || 'GET',
            headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
            body: data === undefined ? undefined : JSON.stringify(data)
        });
        var result = await response.json();
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
        busy = value;
        send.disabled = value;
        newConversation.disabled = value;
    }

    function addMessage(text, kind) {
        var item = document.createElement('div');
        item.className = 'bs-message bs-' + kind;
        var body = document.createElement('div');
        var bubble = document.createElement('div');
        bubble.className = 'bs-bubble';
        bubble.textContent = text;
        body.appendChild(bubble);
        item.appendChild(body);
        messages.appendChild(item);
        messages.scrollTop = messages.scrollHeight;
        return bubble;
    }

    function showResult(bubble, result) {
        bubble.textContent = result.answer;
        var note = labels[result.intent] || '智能客服';
        if (result.pii_redacted) note += ' · 已脱敏';
        if (result.memory_used) note += ' · 使用了长期偏好';
        var meta = document.createElement('small');
        meta.textContent = note;
        bubble.parentNode.appendChild(meta);
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
                title.textContent = product.name;
                info.appendChild(title);
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

    async function restoreConversation() {
        var saved;
        try { saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null'); }
        catch (error) { sessionStorage.removeItem(storageKey); return; }
        if (!saved || !saved.conversation_id) return;
        try {
            var result = await api('conversations/' + encodeURIComponent(saved.conversation_id) + '/');
            conversation = { conversation_id: result.conversation_id, revision: result.revision };
            sessionStorage.setItem(storageKey, JSON.stringify(conversation));
            messages.innerHTML = initialMessage;
            result.turns.forEach(function (turn) {
                addMessage(turn.message, 'user');
                showResult(addMessage('', 'assistant'), turn.response);
            });
        } catch (error) {
            if (error.status === 404 || error.status === 401) {
                sessionStorage.removeItem(storageKey);
                conversation = null;
            }
            throw error;
        }
    }

    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        var question = input.value.trim();
        if (busy || !question) return;
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
            conversation = { conversation_id: result.conversation_id, revision: result.revision };
            sessionStorage.setItem(storageKey, JSON.stringify(conversation));
            pending = null;
            showResult(waiting, result);
        } catch (error) {
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
        }
    });

    newConversation.addEventListener('click', function () {
        if (busy) return;
        conversation = null;
        pending = null;
        sessionStorage.removeItem(storageKey);
        messages.innerHTML = initialMessage;
        input.focus();
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
})();
