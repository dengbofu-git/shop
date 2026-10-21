(function () {
    'use strict';
    var E = window.Engagement, host = document.getElementById('eng-product-reviews');
    if (!host) return;
    var sku = new URLSearchParams(location.search).get('skuid'), page = 1, generation = 0;
    var list = document.getElementById('eng-review-items'), status = document.getElementById('eng-review-status');
    var contact = document.getElementById('eng-contact');
    if (contact && sku) {
        contact.href = '/buyer_messages.html?sku_id=' + encodeURIComponent(sku);
        contact.hidden = typeof AuthStorage !== 'undefined' && AuthStorage.getUserType() === 'merchant';
    }
    async function load() {
        if (!sku) return;
        var current = ++generation;
        status.textContent = E.t('loading');
        var scope = document.getElementById('eng-review-scope').value, sort = document.getElementById('eng-review-sort').value;
        var data = await E.api('products/' + encodeURIComponent(sku) + '/reviews?page=' + page + '&scope=' + scope + '&sort=' + sort);
        if (current !== generation) return;
        var summary = document.getElementById('eng-rating-summary'); summary.replaceChildren();
        if (data.summary.total) {
            summary.append(E.node('strong', data.summary.average.toFixed(1) + ' / 5', 'eng-score'), E.node('span', data.summary.total + ' ' + E.t('count')));
            var bars = E.node('div', null, 'eng-distribution');
            for (var n = 5; n >= 1; n--) {
                var row = E.node('div'), meter = E.node('meter'); meter.min = 0; meter.max = data.summary.total; meter.value = data.summary.distribution[n];
                meter.setAttribute('aria-label', n + ' / 5: ' + data.summary.distribution[n]);
                row.append(E.node('span', n + ' ★'), meter, E.node('span', data.summary.distribution[n])); bars.append(row);
            }
            summary.append(bars);
        } else summary.append(E.node('p', E.t('noReviews'), 'eng-muted'));
        list.replaceChildren();
        data.items.forEach(function (row) {
            var article = E.reviewCard(row);
            article.append(E.button('report', function () {
                if (!AuthStorage.getToken()) { status.textContent = E.t('login'); return; }
                E.ask('reason', 5, 500, async function (reason) { await E.api('reviews/' + row.id + '/report', {reason:reason}); status.textContent = E.t('saved'); });
            })); list.append(article);
        });
        E.pager(document.getElementById('eng-review-pager'), data.page, data.pages, function (value) { page = value; load().catch(showError); }); status.textContent = '';
    }
    function showError(error) { status.textContent = error.message; }
    ['eng-review-scope','eng-review-sort'].forEach(function (id) { document.getElementById(id).onchange = function () { page = 1; load().catch(showError); }; });
    document.getElementById('eng-review-retry').onclick = function () { load().catch(showError); };
    document.addEventListener('eng:language', function () { load().catch(showError); });
    load().catch(showError);
})();
