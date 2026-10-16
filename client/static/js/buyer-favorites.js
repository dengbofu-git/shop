/** Shared favorite controls for dynamically rendered buyer product/recommendation cards. */
(function () {
    'use strict';
    var states = new Map();
    var currentToken = '';
    var words = {
        zh: {save: '收藏', saved: '已收藏', busy: '处理中…', error: '收藏操作失败，请点击重试', denied: '此功能仅供买家使用', missing: '商品不存在或已下架'},
        en: {save: 'Save', saved: 'Saved', busy: 'Saving…', error: 'Could not update favorites. Click to retry.', denied: 'This feature is for buyers.', missing: 'Product unavailable.'},
        ar: {save: 'حفظ', saved: 'محفوظ', busy: 'جار الحفظ…', error: 'تعذر تحديث المفضلة. حاول مرة أخرى.', denied: 'هذه الميزة للمشترين فقط.', missing: 'المنتج غير متاح.'}
    };
    function t(key) { return (words[localStorage.getItem('buyer_lang')] || words.zh)[key]; }
    function token() { return window.AuthStorage && AuthStorage.getToken() || ''; }
    function request(id, method, auth) {
        return fetch((typeof baseUrl === 'undefined' ? '' : baseUrl) + '/v1/goods/favorites/' + id, {
            method: method, headers: {Authorization: auth}, cache: 'no-store'
        }).then(function (response) {
            return response.json().then(function (body) {
                if (!response.ok || body.code !== 200) throw {status: response.status};
                return body.data.is_favorite;
            });
        });
    }
    function paint(id) {
        var state = states.get(id);
        if (!state) return;
        document.querySelectorAll('[data-favorite-sku="' + id + '"]').forEach(function (button) {
            var text = state.busy ? t('busy') : (state.saved ? '♥ ' + t('saved') : '♡ ' + t('save'));
            if (button.textContent !== text) button.textContent = text;
            button.setAttribute('aria-pressed', String(!!state.saved));
            button.disabled = state.busy;
            button.title = state.saved ? t('saved') : t('save');
        });
    }
    function loadState(id) {
        var state = states.get(id), auth = currentToken;
        if (state.pending) return state.pending;
        state.busy = true; paint(id);
        var pending = request(id, 'GET', auth).then(function (saved) {
            if (auth !== token()) return;
            state.saved = saved; state.known = true;
        }).finally(function () {
            state.busy = false; state.pending = null;
            if (states.get(id) === state) paint(id);
        });
        state.pending = pending;
        return pending;
    }
    function scan() {
        var auth = token();
        if (auth !== currentToken) { states.clear(); currentToken = auth; }
        document.querySelectorAll('.product-card[data-skuid], .product-card[data-sku-id], a.recommend-item[href]').forEach(function (card) {
            var id = card.getAttribute('data-skuid') || card.getAttribute('data-sku-id');
            if (!id && card.tagName === 'A') id = new URL(card.href, location.href).searchParams.get('skuid');
            if (!/^\d+$/.test(id || '')) return;
            var parent = card;
            if (card.tagName === 'A') {
                parent = card.parentElement;
                if (!parent.classList.contains('favorite-card-wrapper')) {
                    parent = document.createElement('div'); parent.className = 'favorite-card-wrapper';
                    card.parentNode.insertBefore(parent, card); parent.appendChild(card);
                }
            }
            var button = parent.querySelector('[data-favorite-sku="' + id + '"]');
            if (!button) {
                button = document.createElement('button'); button.type = 'button';
                button.className = 'btn-card-favorite'; button.setAttribute('data-favorite-sku', id);
                parent.appendChild(button);
            }
            if (!states.has(id)) {
                states.set(id, {saved: false, known: !auth, busy: false, pending: null});
                if (auth) loadState(id).catch(function () {});
            }
            paint(id);
        });
    }
    function showError(button, error) {
        var message = button.parentElement.querySelector('.card-favorite-message');
        if (!message) {
            message = document.createElement('span'); message.className = 'card-favorite-message';
            message.setAttribute('role', 'status'); button.parentElement.appendChild(message);
        }
        message.textContent = t(error.status === 403 ? 'denied' : error.status === 404 ? 'missing' : 'error');
    }
    document.addEventListener('click', function (event) {
        var button = event.target.closest && event.target.closest('[data-favorite-sku]');
        if (!button) return;
        // Stop the card's purchase/navigation handler before it sees this click.
        event.preventDefault(); event.stopImmediatePropagation();
        scan();
        if (!currentToken) { location.href = '/login.html'; return; }
        var id = button.getAttribute('data-favorite-sku'), state = states.get(id), auth = currentToken;
        if (!state || state.busy) return;
        var message = button.parentElement.querySelector('.card-favorite-message');
        if (message) message.textContent = '';
        var ready = state.known ? Promise.resolve() : loadState(id);
        ready.then(function () {
            if (auth !== token()) return;
            state.busy = true; paint(id);
            return request(id, state.saved ? 'DELETE' : 'PUT', auth).then(function (saved) {
                if (auth !== token()) return;
                state.saved = saved; state.known = true;
            });
        }).catch(function (error) {
            if (auth !== token()) return;
            if (error.status === 401) { location.href = '/login.html'; return; }
            showError(button, error);
        }).finally(function () { state.busy = false; if (states.get(id) === state) paint(id); });
    }, true);
    function init() {
        scan();
        new MutationObserver(scan).observe(document.body, {subtree: true, childList: true});
        new MutationObserver(scan).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
        window.addEventListener('pageshow', function (event) { if (event.persisted) { states.clear(); scan(); } });
        window.addEventListener('storage', function () { scan(); });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
