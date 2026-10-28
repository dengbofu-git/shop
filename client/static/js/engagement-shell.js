(function () {
    'use strict';
    var E = window.Engagement, timer;
    async function refresh() {
        clearTimeout(timer);
        if (!document.hidden && typeof AuthStorage !== 'undefined' && AuthStorage.getToken()) {
            try {
                var data = await E.api('conversations?page=1');
                document.querySelectorAll('[data-eng-unread]').forEach(function (el) {
                    el.textContent = data.unread_total || ''; el.title = E.t('unread') + ': ' + data.unread_total;
                });
            } catch (_) { /* Keep navigation usable; message center presents actionable errors. */ }
        }
        timer = setTimeout(refresh, 30000);
    }
    document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
    window.addEventListener('pagehide', function () { clearTimeout(timer); });
    refresh();
})();
