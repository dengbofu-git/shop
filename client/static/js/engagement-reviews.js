(function () {
    'use strict';
    var E = window.Engagement, role = document.body.dataset.engRole, page = 1, opened = false, generation = 0;
    var itemId = new URLSearchParams(location.search).get('order_item_id');
    if (role === 'buyer' && !/^[1-9]\d*$/.test(itemId || '')) { location.replace('/buyer_orders.html'); return; }
    var host = document.getElementById('eng-review-list'), status = document.getElementById('eng-status');
    function notify(error) { status.textContent = error.message; }
    function reviewDialog(item) {
        var dialog = E.node('dialog', null, 'eng-dialog'), form = E.node('form'), heading = E.node('h2', E.t('review'));
        heading.id = 'eng-review-dialog-heading'; dialog.setAttribute('aria-labelledby', heading.id);
        var select = E.node('select'), area = E.node('textarea'), message = E.node('p', '', 'eng-status');
        select.id = 'eng-review-stars'; select.required = true; select.append(new Option('—', ''));
        for (var i = 1; i <= 5; i++) select.append(new Option('★'.repeat(i) + ' (' + i + '/5)', String(i)));
        var stars = E.node('label', E.t('stars')); stars.htmlFor = select.id;
        var text = E.node('label', E.t('text')); area.id = 'eng-review-text'; text.htmlFor = area.id; area.required = true; area.minLength = 5; area.maxLength = 1000; area.rows = 6;
        var submit = E.button('submit'); submit.type = 'submit'; submit.className = 'eng-primary';
        form.append(heading, E.node('p', item.product_name + ' · ' + item.specification), E.node('p', E.t('reviewHint'), 'eng-muted'), stars, select, text, area, message, submit,
            E.button('close', function () { dialog.close(); }));
        form.addEventListener('submit', async function (event) {
            event.preventDefault(); submit.disabled = true;
            try { await E.api('reviews', {order_item_id:item.id, rating:Number(select.value), text:area.value}); status.textContent = E.t('saved'); dialog.close(); await load(); }
            catch (error) { message.textContent = error.message; } finally { submit.disabled = false; }
        });
        dialog.append(form); dialog.addEventListener('close', function () { dialog.remove(); }); document.body.append(dialog); dialog.showModal(); select.focus();
    }
    function itemCard(item) {
        var article = E.node('article', null, 'eng-item'), image = E.node('img'); image.src = item.image_url; image.alt = ''; image.loading = 'lazy';
        var info = E.node('div', null, 'eng-item-info');
        info.append(E.node('h3', item.product_name), E.node('p', item.specification, 'eng-muted'), E.node('small', item.order_id + ' · ' + E.t('completed')));
        article.append(image, info);
        if (item.can_review) article.append(E.button('review', function () { reviewDialog(item); }));
        else article.append(E.node('p', E.t(item.review_reason === 'HISTORY_NOT_VERIFIED' ? 'reviewHistory' : item.review_id ? 'rated' : 'notComplete'), 'eng-muted'));
        return article;
    }
    function reviewCard(row) {
        var article = E.reviewCard(row), actions = E.node('div', null, 'eng-toolbar');
        if (role === 'merchant' && row.is_visible && !row.reply) actions.append(E.button('reply', function () {
            E.ask('reply', 1, 1000, async function (text) { await E.api('reviews/' + row.id + '/reply', {text:text}); await load(); });
        }));
        if (role !== 'platform' && row.is_visible) actions.append(E.button('report', function () {
            E.ask('reason', 5, 500, async function (reason) { await E.api('reviews/' + row.id + '/report', {reason:reason}); status.textContent = E.t('saved'); });
        }));
        if (role === 'platform') {
            actions.append(E.button(row.is_visible ? 'hide' : 'restore', function () {
                E.ask('reason', 5, 500, async function (reason) { await E.api('moderation/' + row.id, {reason:reason, is_visible:!row.is_visible}); await load(); });
            }));
            if (row.reports && row.reports.length) {
                var reports = E.node('details'); reports.append(E.node('summary', E.t('reports') + ' (' + row.report_count + ')'));
                row.reports.forEach(function (report) { reports.append(E.node('p', report.reason, 'eng-prose')); }); article.append(reports);
            }
            if (row.moderations && row.moderations.length) {
                var audits = E.node('details'); audits.append(E.node('summary', E.t('audit')));
                row.moderations.forEach(function (audit) { audits.append(E.node('p', E.t(audit.is_visible ? 'restore' : 'hide') + ' · ' + audit.reason + ' · ' + E.date(audit.created_at), 'eng-prose')); }); article.append(audits);
            }
        }
        article.append(actions); return article;
    }
    async function load() {
        var current = ++generation, params = new URLSearchParams({page:page}), path;
        status.textContent = E.t('loading');
        if (role === 'buyer') {
            var itemData = await E.api('reviewable-items?order_item_id=' + encodeURIComponent(itemId));
            var item = itemData.items[0], reviews = item && item.review_id
                ? await E.api('reviews/mine?order_item_id=' + encodeURIComponent(itemId)) : {items:[]};
            if (current !== generation) return;
            host.replaceChildren();
            if (item) {
                host.append(itemCard(item));
                reviews.items.forEach(function (row) { host.append(reviewCard(row)); });
            } else host.append(E.node('p', E.t('empty'), 'eng-muted'));
            document.getElementById('eng-pager').replaceChildren();
            status.textContent = '';
            if (item && item.can_review && !opened) { opened = true; reviewDialog(item); }
            return;
        }
        else {
            path = role === 'platform' ? 'moderation' : 'reviews/mine';
            var rating = document.getElementById('eng-rating').value, query = document.getElementById('eng-query').value.trim();
            if (rating) params.set('rating', rating);
            if (query) params.set('q', query);
            if (document.getElementById('eng-unreplied').checked) params.set('unreplied', '1');
            if (document.getElementById('eng-reported').checked) params.set('reported', '1');
        }
        var data = await E.api(path + '?' + params);
        if (current !== generation) return;
        host.replaceChildren();
        if (!data.items.length) host.append(E.node('p', E.t('empty'), 'eng-muted'));
        data.items.forEach(function (row) { host.append(reviewCard(row)); });
        E.pager(document.getElementById('eng-pager'), data.page, data.pages, function (value) { page = value; load().catch(notify); });
        status.textContent = '';
    }
    document.getElementById('eng-filters').addEventListener('submit', function (event) { event.preventDefault(); page = 1; load().catch(notify); });
    document.getElementById('eng-refresh').onclick = function () { load().catch(notify); };
    document.addEventListener('eng:language', function () { load().catch(notify); });
    (async function () {
        E.updateLanguage(E.language(), true);
        if (role === 'platform') { if (!await PlatformAccess.requirePermission('goods_manage')) return; }
        else { var me = await E.api('identity'); if (me.portal !== role) { location.replace(me.portal === 'buyer' ? '/buyer_orders.html' : '/' + me.portal + '_reviews.html'); return; } }
        document.getElementById('eng-filters').hidden = role === 'buyer';
        await load();
    })().catch(notify);
})();
