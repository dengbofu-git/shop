(function () {
    'use strict';
    var form = document.getElementById('bs-form');
    var input = document.getElementById('bs-input');
    var send = document.getElementById('bs-send');
    var messages = document.getElementById('bs-messages');
    var busy = false;
    var labels = { recommendation: '商品推荐', question_answering: '咨询问答', after_sales: '售后服务', unavailable: '其他问题' };

    function addMessage(text, kind, label) {
        var item = document.createElement('div');
        item.className = 'bs-message bs-' + kind;
        var body = document.createElement('div');
        var bubble = document.createElement('div');
        bubble.className = 'bs-bubble';
        bubble.textContent = text;
        body.appendChild(bubble);
        if (label) {
            var meta = document.createElement('small');
            meta.textContent = label;
            body.appendChild(meta);
        }
        item.appendChild(body);
        messages.appendChild(item);
        messages.scrollTop = messages.scrollHeight;
        return bubble;
    }

    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        var question = input.value.trim();
        if (busy || !question) return;
        var token = AuthStorage.getToken();
        if (!token) {
            addMessage('请先登录后再使用智能客服。', 'assistant');
            return;
        }
        busy = true;
        send.disabled = true;
        input.value = '';
        addMessage(question, 'user');
        var waiting = addMessage('正在整理回复，请稍候…', 'assistant');
        try {
            var response = await fetch('/v1/support/chat/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify({ message: question })
            });
            var result = await response.json();
            waiting.textContent = response.ok ? result.answer : (result.error || '暂时无法回答，请稍后重试。');
            if (response.ok) {
                var note = labels[result.intent] || '智能客服';
                if (result.pii_redacted) note += ' · 已脱敏';
                var meta = document.createElement('small');
                meta.textContent = note;
                waiting.parentNode.appendChild(meta);
            }
        } catch (error) {
            waiting.textContent = '网络连接失败，请稍后重试。';
        } finally {
            busy = false;
            send.disabled = false;
            input.focus();
            messages.scrollTop = messages.scrollHeight;
        }
    });

    document.querySelectorAll('.bs-suggestions button').forEach(function (button) {
        button.addEventListener('click', function () {
            input.value = button.getAttribute('data-question') || '';
            input.focus();
        });
    });
})();
