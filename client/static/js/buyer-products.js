/* Complete procurement catalog; homepage discovery lives in buyer-catalog-preview.js. */
(function () {
    'use strict';
    var model = window.BuyerCatalogModel;
    var state = model.read(window.location.search), categories = [], ready = false;
    var i18n = {
        zh: {title: '商品采购', intro: '按茶类、价格与店铺查找商品，核对规格后加入采购车。',
            all: '全部产品', keyword: '商品关键词', keyword_hint: '商品名、规格或店铺名', min_price: '最低价格', max_price: '最高价格',
            merchant: '店铺名称', store_hint: '搜索店铺名称', sort: '排序', default_sort: '茶类均衡',
            price_asc: '价格从低到高', price_desc: '价格从高到低', apply: '应用筛选', reset: '重置',
            note: '仅展示可售商品；价格为参考换算，最终金额以结算页为准。',
            loading: '正在加载商品目录…', error: '商品目录加载失败，请重试。', retry: '重新加载', empty: '没有符合条件的商品，请调整筛选。',
            summary: '当前显示 {start}–{end} 件，共 {total} 件商品', prev: '上一页', next: '下一页',
            add: '加入采购车', invalid: '最高价格不能低于最低价格', pages: '商品分页'},
        en: {title: 'Product procurement', intro: 'Find tea by category, price and store. Check specifications before adding to your cart.',
            all: 'All products', keyword: 'Keywords', keyword_hint: 'Product, specification or store', min_price: 'Minimum price', max_price: 'Maximum price',
            merchant: 'Store name', store_hint: 'Search store name', sort: 'Sort', default_sort: 'Balanced categories',
            price_asc: 'Price: low to high', price_desc: 'Price: high to low', apply: 'Apply filters', reset: 'Reset',
            note: 'Available products only. Converted prices are estimates; checkout determines the final amount.',
            loading: 'Loading product catalog…', error: 'Could not load the catalog. Please retry.', retry: 'Retry', empty: 'No matching products. Adjust your filters.',
            summary: 'Showing {start}–{end} of {total} products', prev: 'Previous', next: 'Next',
            add: 'Add to cart', invalid: 'Maximum price must be at least the minimum price', pages: 'Product pages'},
        ar: {title: 'شراء المنتجات', intro: 'ابحث حسب فئة الشاي والسعر والمتجر، وتحقق من المواصفات قبل الإضافة للسلة.',
            all: 'جميع المنتجات', keyword: 'كلمات البحث', keyword_hint: 'المنتج أو المواصفات أو المتجر', min_price: 'أقل سعر', max_price: 'أعلى سعر',
            merchant: 'اسم المتجر', store_hint: 'ابحث باسم المتجر', sort: 'الترتيب', default_sort: 'توازن الفئات',
            price_asc: 'السعر من الأقل للأعلى', price_desc: 'السعر من الأعلى للأقل', apply: 'تطبيق', reset: 'إعادة ضبط',
            note: 'منتجات معروضة ومتوفرة فقط. الأسعار المحولة تقديرية؛ المبلغ النهائي عند الدفع.',
            loading: 'جار تحميل المنتجات…', error: 'تعذر تحميل المنتجات. أعد المحاولة.', retry: 'إعادة المحاولة', empty: 'لا توجد نتائج مطابقة. عدّل المرشحات.',
            summary: 'عرض {start}–{end} من أصل {total} منتجاً', prev: 'السابق', next: 'التالي',
            add: 'أضف للسلة', invalid: 'يجب ألا يقل أعلى سعر عن أقل سعر', pages: 'صفحات المنتجات'}
    };
    function t(key) { return (i18n[localStorage.getItem('buyer_lang')] || i18n.zh)[key] || key; }
    function node(id) { return document.getElementById(id); }
    function element(tag, className, text) {
        var item = document.createElement(tag); item.className = className || '';
        if (text !== undefined) item.textContent = text;
        return item;
    }
    function button(text, action, disabled) {
        var item = element('button', 'catalog-tab', text); item.type = 'button'; item.disabled = !!disabled;
        item.addEventListener('click', action); return item;
    }
    function url() { return 'buyer_products.html?' + model.search(state); }
    function saveScroll() {
        history.replaceState(Object.assign({}, history.state, {procurementScrollY: window.scrollY}), '', window.location.href);
    }
    function restoreScroll() {
        var y = history.state && history.state.procurementScrollY;
        if (Number.isFinite(y)) window.requestAnimationFrame(function () { window.scrollTo(0, y); });
    }
    function commit(next, scroll) {
        saveScroll(); state = next;
        history.pushState({procurementScrollY: window.scrollY}, '', url());
        if (!ready) { syncForm(); return; }
        render();
        if (scroll) {
            var current = node('procurement-pagination').querySelector('[aria-current="page"]');
            if (current) current.focus({preventScroll: true});
            node('procurement-results').scrollIntoView({block: 'start'});
        }
    }
    function syncForm() {
        ['q', 'min_price', 'max_price', 'store_q', 'sort'].forEach(function (key) { node('filter-' + key).value = state[key]; });
        node('currency-select').value = state.currency;
        node('search-input').value = state.q;
        document.querySelectorAll('[data-price-currency]').forEach(function (item) { item.textContent = state.currency; });
        ['min_price', 'max_price'].forEach(function (key) {
            var label = t(key) + ' (' + state.currency + ')';
            node('filter-' + key).placeholder = label;
            node('filter-' + key).setAttribute('aria-label', label);
        });
    }
    function translate() {
        document.querySelectorAll('[data-procure]').forEach(function (item) { item.textContent = t(item.dataset.procure); });
        node('filter-q').placeholder = t('keyword_hint');
        node('filter-q').setAttribute('aria-label', t('keyword'));
        node('filter-store_q').placeholder = t('store_hint');
        node('filter-store_q').setAttribute('aria-label', t('store_hint'));
        node('filter-sort').setAttribute('aria-label', t('sort'));
        node('procurement-pagination').setAttribute('aria-label', t('pages'));
        node('filter-max_price').setCustomValidity('');
    }
    function renderCategories() {
        var tabs = node('category-tabs'); tabs.replaceChildren();
        [{id: 'all', name: t('all'), rows: model.interleave(categories)}].concat(categories).forEach(function (cat) {
            var tab = button(cat.name + ' (' + cat.rows.length + ')', function () {
                commit(Object.assign({}, state, {catalog_id: cat.id, page: 1}), false);
            });
            tab.setAttribute('aria-pressed', String(cat.id === state.catalog_id));
            tab.classList.toggle('active', cat.id === state.catalog_id); tabs.appendChild(tab);
        });
    }
    function renderCard(row) {
        var title = String(row.spu_name || row.product_name || row.name || '');
        var card = element('div', 'product-card'); card.dataset.skuid = row.skuid;
        card.dataset.cny = row.price; card.dataset.pimg = row.image || ''; card.dataset.pname = title;
        var href = 'product_details.html?skuid=' + encodeURIComponent(row.skuid);
        var picture = element('a', 'product-img-wrap'); picture.href = href; picture.setAttribute('aria-label', title);
        var img = element('img'); img.alt = ''; img.loading = 'lazy';
        img.src = row.image_url || (baseUrl + '/v1/goods/sku/' + row.skuid + '/image');
        img.onerror = function () { this.onerror = null; this.src = '/static/images/cart/product_normal.png'; };
        picture.appendChild(img); card.appendChild(picture);
        var heading = element('h3', 'product-name'), link = element('a', '', title); link.href = href;
        heading.appendChild(link); card.appendChild(heading);
        var skuName = String(row.name || '');
        var spec = [skuName !== title ? skuName : '', row.caption || ''].filter(Boolean).join(' · ');
        card.appendChild(element('p', 'product-spec', spec));
        var price = element('div', 'product-price', TeaMoney.format(row.price, state.currency));
        price.dataset.cny = row.price; card.appendChild(price);
        if (window.Storefront) card.appendChild(Storefront.merchantLink(row.merchant));
        var actions = element('div', 'product-actions-row');
        var add = element('button', 'btn-add-cart', t('add')); add.type = 'button'; actions.appendChild(add); card.appendChild(actions);
        return card;
    }
    function renderPager(result) {
        var pager = node('procurement-pagination'); pager.replaceChildren(); pager.hidden = result.pages <= 1;
        if (pager.hidden) return;
        function pageButton(label, page, disabled) {
            var item = button(label, function () { commit(Object.assign({}, state, {page: page}), true); }, disabled);
            if (page === result.page && !disabled) item.setAttribute('aria-current', 'page');
            pager.appendChild(item);
        }
        pageButton(t('prev'), result.page - 1, result.page === 1);
        var pages = new Set([1, result.pages]);
        for (var i = Math.max(1, result.page - 2); i <= Math.min(result.pages, result.page + 2); i++) pages.add(i);
        var previous = 0;
        Array.from(pages).sort(function (a, b) { return a - b; }).forEach(function (page) {
            if (previous && page > previous + 1) pager.appendChild(element('span', '', '…'));
            pageButton(String(page), page, false); previous = page;
        });
        pageButton(t('next'), result.page + 1, result.page === result.pages);
    }
    function render() {
        translate(); syncForm(); renderCategories();
        var result = model.query(categories, state); state.page = result.page;
        history.replaceState(history.state, '', url());
        var grid = node('product-grid'); grid.replaceChildren();
        result.rows.forEach(function (row) { grid.appendChild(renderCard(row)); });
        node('procurement-empty').hidden = result.total > 0;
        node('procurement-summary').textContent = t('summary').replace('{start}', result.start).replace('{end}', result.end).replace('{total}', result.total);
        renderPager(result);
    }
    async function load() {
        ready = false; node('procurement-fields').disabled = true;
        node('procurement-error').hidden = true; node('procurement-retry').hidden = true;
        node('procurement-empty').hidden = true; node('product-grid').setAttribute('aria-busy', 'true');
        node('product-grid').replaceChildren(element('p', 'product-loading', t('loading')));
        node('procurement-pagination').hidden = true;
        try {
            var response = await fetch(baseUrl + '/v1/goods/index', {cache: 'no-store'});
            if (!response.ok) throw new Error('catalog-request-failed');
            var body = await response.json();
            if (body.code !== 200 || !Array.isArray(body.data)) throw new Error('invalid-catalog-response');
            categories = model.normalize(body.data);
            if (!categories.some(function (cat) { return cat.id === state.catalog_id; })) state.catalog_id = 'all';
            ready = true; node('procurement-fields').disabled = false; render(); restoreScroll();
        } catch (error) {
            node('product-grid').replaceChildren(); node('procurement-summary').textContent = '';
            node('procurement-error').hidden = false; node('procurement-retry').hidden = false;
        } finally { node('product-grid').setAttribute('aria-busy', 'false'); }
    }
    // Set before the shared workbench ready handler reads the sidebar currency.
    node('currency-select').value = state.currency;
    $(function () {
        translate(); syncForm(); load();
        node('procurement-filters').addEventListener('submit', function (event) {
            event.preventDefault();
            var max = node('filter-max_price'), min = node('filter-min_price');
            max.setCustomValidity(max.value !== '' && min.value !== '' && Number(max.value) < Number(min.value) ? t('invalid') : '');
            if (!this.reportValidity()) return;
            var params = new URLSearchParams(model.search(state));
            ['q', 'min_price', 'max_price', 'store_q', 'sort'].forEach(function (key) { params.set(key, node('filter-' + key).value); });
            params.set('page', '1'); commit(model.read(params.toString()), false);
        });
        ['filter-min_price', 'filter-max_price'].forEach(function (id) { node(id).addEventListener('input', function () { node('filter-max_price').setCustomValidity(''); }); });
        node('procurement-reset').addEventListener('click', function () { commit(model.read('?currency=' + state.currency), false); });
        node('procurement-retry').addEventListener('click', load);
        node('currency-select').addEventListener('change', function () {
            commit(Object.assign({}, state, {currency: this.value, min_price: '', max_price: '', page: 1}), false);
        });
        node('lang-switch').addEventListener('click', function (event) {
            if (event.target.closest('.lang-btn')) { if (ready) render(); else translate(); }
        });
        document.addEventListener('buyer:catalog-search', function (event) {
            commit(Object.assign({}, state, {q: event.detail.trim().slice(0, 200), page: 1}), false);
        });
        node('product-grid').addEventListener('click', function (event) { if (event.target.closest('a')) saveScroll(); });
        window.addEventListener('pagehide', saveScroll);
        window.addEventListener('popstate', function () { state = model.read(window.location.search); if (ready) { render(); restoreScroll(); } });
    });
})();
