(function () {
    'use strict';

    var statusText = document.getElementById('ma-status-text');
    var retry = document.getElementById('ma-retry');
    var login = document.getElementById('ma-login');
    var checking = false;
    if (new URLSearchParams(window.location.search).get('embed') === '1') {
        document.body.classList.add('ma-embedded');
    }

    async function loadStatus() {
        if (checking) return;
        retry.hidden = true;
        login.hidden = true;
        var token = AuthStorage.getToken();
        if (!token) {
            statusText.textContent = '请先登录商家账号后查看助手状态。';
            login.hidden = false;
            return;
        }
        checking = true;
        statusText.textContent = '正在确认入口状态…';
        var controller = new AbortController();
        var timeout = window.setTimeout(function () { controller.abort(); }, 10000);
        try {
            var response = await fetch('/v1/merchant-ai/status/', {
                headers: { 'Authorization': 'Bearer ' + token },
                cache: 'no-store',
                signal: controller.signal
            });
            if (response.status === 401) {
                statusText.textContent = '登录已失效，请重新登录商家账号。';
                login.hidden = false;
                return;
            }
            if (response.status === 403) {
                statusText.textContent = '此入口仅向已激活的商家或供应商账号开放。';
                login.hidden = false;
                return;
            }
            if (!response.ok) throw new Error('status unavailable');
            var result = await response.json();
            var data = result.data;
            if (result.code !== 200 || !data || data.module !== 'merchant_ai' ||
                    data.status !== 'initialized' || data.chat_enabled !== false ||
                    data.model_connected !== false || !Array.isArray(data.capabilities) ||
                    data.capabilities.length !== 0) {
                throw new Error('unsupported assistant status');
            }
            statusText.textContent = '入口已就绪 · 功能准备中';
        } catch (error) {
            statusText.textContent = '暂时无法确认入口状态，请稍后重试。';
            retry.hidden = false;
        } finally {
            window.clearTimeout(timeout);
            checking = false;
        }
    }

    retry.addEventListener('click', loadStatus);
    loadStatus();
}());
