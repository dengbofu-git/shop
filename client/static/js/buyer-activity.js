(function () {
    'use strict';
    var words = {
        zh: { favorites: '我的收藏', recent: '最近浏览', favorite: '收藏商品', saved: '已收藏 · 取消收藏', remove: '取消收藏', erase: '删除足迹', clear: '清空足迹', confirm: '确定清空全部浏览足迹？', view: '查看商品', loading: '正在加载…', empty: '还没有收藏商品，去发现喜欢的茶品吧。', emptyRecent: '暂无浏览足迹，查看商品详情后会自动记录。', error: '加载失败，请稍后重试。', actionError: '操作失败，请重试。', retry: '重试', browse: '去逛逛', prev: '上一页', next: '下一页', unavailable: '商品已下架', login: '请先登录后使用收藏与足迹', denied: '此功能仅供买家使用', count: '件商品', note: '按收藏时间排序，随时回来查看喜欢的商品。价格以当前商品为准。', recentNote: '最近查看的商品排在前面，最多保留 100 件；可随时删除或清空。', recorded: '记录时间：', historyError: '足迹保存失败，刷新页面可重试。' },
        en: { favorites: 'Favorites', recent: 'Recently viewed', favorite: 'Save product', saved: 'Saved · Unsave', remove: 'Unsave', erase: 'Remove history', clear: 'Clear history', confirm: 'Clear all browsing history?', view: 'View product', loading: 'Loading…', empty: 'No favorites yet. Discover your next tea.', emptyRecent: 'No browsing history yet. Open a product to start.', error: 'Could not load products. Please retry.', actionError: 'Action failed. Please retry.', retry: 'Retry', browse: 'Browse products', prev: 'Previous', next: 'Next', unavailable: 'Unavailable', login: 'Please sign in to use favorites and history', denied: 'This feature is for buyers', count: 'products', note: 'Your favorites, newest first. Prices reflect the current catalog.', recentNote: 'Your 100 most recently viewed products. Remove items or clear the list at any time.', recorded: 'Recorded: ', historyError: 'Could not save browsing history. Refresh to retry.' },
        ar: { favorites: 'المفضلة', recent: 'المشاهدة الأخيرة', favorite: 'حفظ المنتج', saved: 'محفوظ · إلغاء الحفظ', remove: 'إلغاء الحفظ', erase: 'حذف السجل', clear: 'مسح السجل', confirm: 'هل تريد مسح سجل التصفح بالكامل؟', view: 'عرض المنتج', loading: 'جار التحميل…', empty: 'لا توجد منتجات مفضلة بعد.', emptyRecent: 'لا يوجد سجل تصفح بعد. افتح صفحة منتج للبدء.', error: 'تعذر التحميل. حاول مرة أخرى.', actionError: 'فشلت العملية. حاول مرة أخرى.', retry: 'إعادة المحاولة', browse: 'تصفح المنتجات', prev: 'السابق', next: 'التالي', unavailable: 'غير متاح', login: 'يرجى تسجيل الدخول لاستخدام المفضلة والسجل', denied: 'هذه الميزة للمشترين فقط', count: 'منتجات', note: 'المفضلة من الأحدث إلى الأقدم. الأسعار حسب الكتالوج الحالي.', recentNote: 'آخر 100 منتج شاهدته. يمكنك حذف العناصر أو مسح السجل.', recorded: 'وقت التسجيل: ', historyError: 'تعذر حفظ سجل التصفح. أعد تحميل الصفحة للمحاولة.' }
    };
    function t(key) { return (words[localStorage.getItem('buyer_lang')] || words.zh)[key]; }
    function token() { return window.AuthStorage && AuthStorage.getToken(); }
    function message(el, value) { if (el) el.textContent = value; }
    function api(path, method) {
        if (!token()) return Promise.reject({status: 401});
        return fetch((typeof baseUrl === 'undefined' ? '' : baseUrl) + '/v1/goods/' + path, {
            method: method || 'GET', headers: {Authorization: token()}, cache: 'no-store'
        }).then(function (response) {
            return response.json().then(function (body) {
                if (!response.ok || body.code !== 200) throw {status: response.status};
                return body;
            });
        });
    }
    function errorText(error, fallback) {
        if (error.status === 401) return t('login');
        if (error.status === 403) return t('denied');
        return t(fallback);
    }
    function element(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (text != null) el.textContent = text;
        return el;
    }
    function observeLanguage(render) {
        new MutationObserver(render).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
    }
    function initList() {
        var grid = document.getElementById('activity-grid');
        if (!grid) return;
        var recent = /\/recent\.html$/.test(location.pathname);
        var endpoint = recent ? 'recent' : 'favorites';
        var page = 1, pages = 1, total = 0, rows = [], loading = false, failed = null, busy = false, actionError = null;
        var status = document.getElementById('activity-message');
        var feedback = document.getElementById('activity-feedback');
        var emptyIcon = document.getElementById('activity-empty-icon');
        var pagination = document.getElementById('activity-pagination');
        var clear = document.getElementById('activity-clear');
        var retry = document.getElementById('activity-retry');
        var browse = document.getElementById('activity-browse');
        var prev = document.getElementById('activity-prev');
        var next = document.getElementById('activity-next');
        function action(path, method) {
            if (busy) return;
            busy = true;
            actionError = null;
            render();
            api(path, method).then(function () { busy = false; load(); }).catch(function (error) {
                busy = false; actionError = error; render();
            });
        }
        function render() {
            var empty = !loading && !failed && !total;
            feedback.classList.toggle('is-empty', empty);
            feedback.hidden = !loading && !failed && !actionError && total > 0;
            emptyIcon.hidden = !empty;
            pagination.hidden = loading || !!failed || pages <= 1 || !total;
            grid.hidden = loading || !!failed || !total;
            var title = t(recent ? 'recent' : 'favorites');
            document.title = title + ' · 茗越山关';
            message(document.getElementById('activity-title'), title);
            message(document.getElementById('activity-description'), t(recent ? 'recentNote' : 'note'));
            message(document.getElementById('activity-count'), failed || loading ? '' : total + ' ' + t('count'));
            message(clear, t('clear')); clear.hidden = !recent || !total || !!failed; clear.disabled = loading || busy;
            message(retry, t('retry')); retry.hidden = !failed || failed.status === 401 || failed.status === 403;
            message(browse, t('browse')); browse.hidden = loading || !!failed || total > 0;
            message(prev, t('prev')); message(next, t('next'));
            prev.disabled = loading || busy || !!failed || page <= 1;
            next.disabled = loading || busy || !!failed || page >= pages;
            message(document.getElementById('activity-page'), loading || failed ? '' : page + ' / ' + pages);
            message(status, loading ? t('loading') : failed ? errorText(failed, 'error') : actionError ? errorText(actionError, 'actionError') : !total ? t(recent ? 'emptyRecent' : 'empty') : '');
            if ((failed && failed.status === 401) || (actionError && actionError.status === 401)) {
                var login = element('a', '', ' ' + t('login')); login.href = 'login.html'; status.appendChild(login);
            }
            grid.setAttribute('aria-busy', String(loading || busy));
            grid.replaceChildren();
            if (loading || failed) return;
            rows.forEach(function (row) {
                var card = element('article', 'activity-card');
                var img = element('img'); img.src = (typeof baseUrl === 'undefined' ? '' : baseUrl) + row.image_url; img.alt = row.product_name || row.name; img.loading = 'lazy';
                img.onerror = function () { img.onerror = null; img.src = '/static/images/cart/product_normal.png'; };
                card.appendChild(img);
                var body = element('div', 'activity-card-body');
                body.appendChild(element('h2', '', row.product_name || row.name));
                body.appendChild(element('p', '', row.name));
                body.appendChild(element('p', 'activity-price', '¥ ' + row.price));
                body.appendChild(element('p', 'activity-meta', t('recorded') + new Date(row.recorded_at).toLocaleString(document.documentElement.lang)));
                var actions = element('div', 'activity-actions');
                if (row.is_launched) {
                    var link = element('a', 'activity-view', t('view')); link.href = 'product_details.html?skuid=' + row.skuid; actions.appendChild(link);
                } else body.appendChild(element('p', 'activity-unavailable', t('unavailable')));
                var remove = element('button', '', t(recent ? 'erase' : 'remove')); remove.type = 'button'; remove.disabled = busy;
                remove.addEventListener('click', function () { action(endpoint + '/' + row.skuid, 'DELETE'); }); actions.appendChild(remove);
                if (recent && (row.is_launched || row.is_favorite)) {
                    var save = element('button', '', t(row.is_favorite ? 'saved' : 'favorite')); save.type = 'button'; save.disabled = busy;
                    save.setAttribute('aria-pressed', String(row.is_favorite));
                    save.addEventListener('click', function () { action('favorites/' + row.skuid, row.is_favorite ? 'DELETE' : 'PUT'); }); actions.appendChild(save);
                }
                body.appendChild(actions); card.appendChild(body); grid.appendChild(card);
            });
        }
        function load() {
            loading = true; failed = null; actionError = null; render();
            api(endpoint + '?page=' + page).then(function (result) {
                rows = result.data; page = result.paginator.page; pages = result.paginator.pages; total = result.paginator.total;
                loading = false; render();
            }).catch(function (error) { failed = error; loading = false; rows = []; render(); });
        }
        clear.addEventListener('click', function () { if (confirm(t('confirm'))) { page = 1; action('recent', 'DELETE'); } });
        retry.addEventListener('click', load);
        prev.addEventListener('click', function () { page--; load(); });
        next.addEventListener('click', function () { page++; load(); });
        observeLanguage(render); load();
    }
    function initDetail(skuId) {
        var button = document.getElementById('favorite-toggle');
        if (!button) return;
        var status = document.getElementById('favorite-message');
        var saved = false, ready = false, busy = false;
        function render() {
            message(button, t(saved ? 'saved' : 'favorite'));
            button.setAttribute('aria-pressed', String(saved));
            button.disabled = busy;
        }
        function refresh() {
            busy = true; render();
            api('favorites/' + skuId).then(function (result) {
                saved = result.data.is_favorite; ready = true; busy = false; render();
            }).catch(function (error) {
                busy = false; render();
                message(status, errorText(error, 'actionError'));
            });
        }
        button.addEventListener('click', function () {
            if (!token()) { location.href = 'login.html'; return; }
            if (!ready) { refresh(); return; }
            busy = true; render();
            api('favorites/' + skuId, saved ? 'DELETE' : 'PUT').then(function (result) {
                saved = result.data.is_favorite; busy = false; message(status, ''); render();
            }).catch(function (error) {
                busy = false; render(); message(status, errorText(error, 'actionError'));
                if (error.status === 401) location.href = 'login.html';
            });
        });
        observeLanguage(render); render();
        if (token()) {
            refresh();
            api('recent/' + skuId, 'POST').catch(function (error) { message(status, errorText(error, 'historyError')); });
        }
    }
    window.BuyerActivity = {initDetail: initDetail};
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initList);
    else initList();
})();
