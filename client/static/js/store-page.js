(function () {
    'use strict';
    var root = document.getElementById('store-main');
    if (!root) return;
    var params = new URLSearchParams(location.search), id = params.get('merchant_id');
    var state = {page: 1, pages: 1}, sequence = 0, hasFeatured = false;
    var feedback = document.getElementById('store-feedback');
    var content = document.getElementById('store-content');
    var favoriteActions = document.getElementById('store-favorite-actions');
    async function api(path) {
        var response = await fetch('/v1/stores/' + id + path, {cache: 'no-store'});
        var result;
        try { result = await response.json(); }
        catch (error) { throw new Error('店铺服务暂时不可用，请稍后重试。'); }
        if (!response.ok || result.code !== 200) throw new Error(result.error || '店铺加载失败，请重试。');
        return result;
    }
    function fail(message) { feedback.textContent = message; feedback.hidden = false; }
    async function products() {
        var current = ++sequence, grid = document.getElementById('product-grid');
        grid.setAttribute('aria-busy', 'true');
        document.getElementById('store-product-message').textContent = '正在加载本店商品…';
        document.getElementById('store-prev').disabled = true;
        document.getElementById('store-next').disabled = true;
        try {
            var search = new URLSearchParams({q: document.getElementById('store-search').value,
                catalog_id: document.getElementById('store-catalog').value,
                sort: document.getElementById('store-sort').value, page: state.page});
            var result = await api('/products?' + search);
            if (current !== sequence) return;
            state.page = result.pagination.page; state.pages = result.pagination.pages;
            Storefront.cards(grid, result.data, false);
            document.getElementById('store-product-message').textContent = '共 ' + result.pagination.total + ' 件本店商品';
            document.getElementById('store-page-number').textContent = state.page + ' / ' + state.pages;
            document.getElementById('store-prev').disabled = state.page <= 1;
            document.getElementById('store-next').disabled = state.page >= state.pages;
        } catch (error) {
            if (current !== sequence) return;
            grid.replaceChildren();
            document.getElementById('store-product-message').textContent = error.message + ' 可点击“搜索”重试。';
        } finally { if (current === sequence) grid.setAttribute('aria-busy', 'false'); }
    }
    async function load() {
        content.hidden = true; feedback.hidden = false; feedback.textContent = '正在打开店铺…';
        if (!id || !/^\d+$/.test(id)) { fail('请选择一家店铺，或返回平台浏览商品。'); return; }
        try {
            var result = await api(''), data = result.data;
            Storefront.hero(document.getElementById('store-hero'), data.content, favoriteActions);
            document.title = data.content.name + ' · tea_saas';
            Storefront.cards(document.getElementById('store-featured-grid'), data.featured, false);
            hasFeatured = data.featured.length > 0;
            document.getElementById('store-featured').hidden = !hasFeatured;
            document.getElementById('store-story').textContent = data.content.story || '商家尚未填写店铺故事。';
            var select = document.getElementById('store-catalog'); select.length = 1;
            data.catalogs.forEach(function (row) {
                var option = document.createElement('option'); option.value = row.spu__catalog_id;
                option.textContent = row.spu__catalog__name; select.appendChild(option);
            });
            content.hidden = false; feedback.hidden = true;
            if (window.BuyerActivity) BuyerActivity.initMerchant(data.merchant_id);
            await products();
        } catch (error) { fail(error.message); }
    }
    document.getElementById('store-retry').addEventListener('click', load);
    document.getElementById('store-filter').addEventListener('submit', function (event) { event.preventDefault(); state.page = 1; products(); });
    ['store-sort', 'store-catalog'].forEach(function (key) { document.getElementById(key).addEventListener('change', function () { state.page = 1; products(); }); });
    document.getElementById('store-prev').addEventListener('click', function () { if (state.page > 1) { state.page--; products(); } });
    document.getElementById('store-next').addEventListener('click', function () { if (state.page < state.pages) { state.page++; products(); } });
    document.querySelectorAll('[data-store-tab]').forEach(function (tab) {
        tab.addEventListener('click', function () {
            document.querySelectorAll('[data-store-tab]').forEach(function (item) { item.setAttribute('aria-pressed', String(item === tab)); });
            var name = tab.dataset.storeTab;
            document.getElementById('store-featured').hidden = name !== 'home' || !hasFeatured;
            document.getElementById('store-products').hidden = name === 'about';
            document.getElementById('store-about').hidden = name !== 'about';
        });
    });
    load();
}());
