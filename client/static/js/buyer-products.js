/**
 * 买家商品采购页 - 集成在工作台内
 * 分类切换、分页、推荐商品、i18n
 */
(function() {
    'use strict';

    var RATES = { USD: 1, AED: 3.67, SAR: 3.75 };
    var currentCurrency = 'USD';
    var catalogs = [];
    var currentCatalogId = 'all';
    var currentPage = 1;
    var pageMax = 1;
    var PAGE_SIZE = 10;
    var baseUrlMedia = '';

    var i18n = {
        zh: {
            procure_title: '商品采购 - 跨境茶叶saas平台',
            all_products: '全部产品',
            page_summary: '当前显示 {start}–{end} 件，共 {total} 件商品',
            loading: '加载中...',
            no_products: '暂无商品',
            prev_page: '上一页',
            next_page: '下一页',
            recommend_title: '推荐商品',
            recommend_empty: '暂无推荐',
            add_cart: '加入采购车',
            trace_btn: '溯源',
            quick_preview: '快速预览'
        },
        en: {
            procure_title: 'Product Procurement - Cross-border Tea SaaS Platform',
            all_products: 'All Products',
            page_summary: 'Showing {start}–{end} of {total} products',
            loading: 'Loading...',
            no_products: 'No products',
            prev_page: 'Previous',
            next_page: 'Next',
            recommend_title: 'Recommended',
            recommend_empty: 'No recommendations',
            add_cart: 'Add to Cart',
            trace_btn: 'Traceability',
            quick_preview: 'Quick preview'
        },
        ar: {
            procure_title: 'المشتريات - منصة SaaS لتجارة الشاي عبر الحدود',
            all_products: 'جميع المنتجات',
            page_summary: 'عرض {start}–{end} من أصل {total} منتجاً',
            loading: 'جاري التحميل...',
            no_products: 'لا توجد منتجات',
            prev_page: 'السابق',
            next_page: 'التالي',
            recommend_title: 'موصى به',
            recommend_empty: 'لا توجد توصيات',
            add_cart: 'أضف للسلة',
            trace_btn: 'التتبع',
            quick_preview: 'معاينة سريعة'
        }
    };

    function getLang() {
        return localStorage.getItem('buyer_lang') || 'en';
    }

    function t(key) {
        var lang = getLang();
        return (i18n[lang] || i18n.en)[key] || key;
    }

    function getUrlParam(name) {
        var reg = new RegExp('(^|&)' + name + '=([^&]*)(&|$)');
        var r = window.location.search.substr(1).match(reg);
        return r ? r[2] : null;
    }

    function getSymbol() {
        return currentCurrency === 'USD' ? '$' : (currentCurrency === 'AED' ? 'AED ' : 'SAR ');
    }

    function formatPrice(price) {
        var p = parseFloat(price) || 0;
        var rate = RATES[currentCurrency] || 1;
        return getSymbol() + (p * rate).toFixed(2);
    }

    /** 卡片标题用 SPU 商品名，规格放在 product-spec */
    function productTitle(el) {
        var spu = (el.spu_name || el.title || el.product_name || '').trim();
        return spu || String(el.name || '-').trim();
    }

    function productSpec(el) {
        var title = productTitle(el);
        if (el.caption && String(el.caption).trim()) {
            return String(el.caption).trim();
        }
        var sku = String(el.name || '').trim();
        if (sku && sku !== title) {
            return sku;
        }
        return '';
    }

    function renderProductCard(el) {
        var skuid = el.skuid || el.id;
        var title = productTitle(el);
        var spec = productSpec(el);
        var imgUrl = el.image && baseUrlMedia
            ? (baseUrlMedia.replace(/\/$/, '') + (String(el.image).indexOf('/') === 0 ? '' : '/') + el.image)
            : '';
        var imgHtml = imgUrl
            ? '<img src="' + imgUrl + '" alt="' + (el.name || '').replace(/"/g, '&quot;') + '" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">' +
              '<div class="product-img" style="display:none;">' + (el.image_text || el.name || '') + '</div>'
            : '<div class="product-img">' + (el.image_text || el.name || '') + '</div>';
        return '<div class="product-card" data-skuid="' + skuid + '" data-cny="' + (Number(el.price) || 0) + '" data-pimg="' + String(el.image || '').replace(/"/g, '&quot;') + '">' +
            '<a class="product-img-wrap" href="product_details.html?skuid=' + skuid + '" aria-label="' + title.replace(/&/g, '&amp;').replace(/"/g, '&quot;') + '">' + imgHtml + '</a>' +
            '<h3 class="product-name"><a href="product_details.html?skuid=' + skuid + '">' + title.replace(/</g, '&lt;') + '</a></h3>' +
            '<p class="product-spec">' + spec.replace(/</g, '&lt;') + '</p>' +
            '<div class="product-price" data-usd="' + (el.price || 0) + '" data-aed="' + ((el.price || 0) * 3.67).toFixed(0) + '" data-sar="' + ((el.price || 0) * 3.75).toFixed(0) + '">' + formatPrice(el.price) + '</div>' +
            '<div class="product-actions-row"><button type="button" class="btn-add-cart">' + t('add_cart') + '</button></div>' +
            '<div class="product-secondary-actions"><button type="button" class="btn-quick-preview" data-i18n="quick_preview">' + t('quick_preview') + '</button>' +
            '<button type="button" class="btn-trace-link" data-i18n="trace_btn" disabled aria-disabled="true">溯源</button></div>' +
            '</div>';
    }

    function rowsForSelection() {
        var groups = catalogs.filter(function(cat) {
            return currentCatalogId === 'all' || Number(cat.catalog_id) === currentCatalogId;
        }).map(function(cat) {
            return (cat.sku || []).slice().sort(function(a, b) { return Number(b.skuid) - Number(a.skuid); });
        });
        // 全部分类轮流展示各茶类，先保留全部SKU，再按10件分页。
        var rows = [], seen = new Set(), index = 0;
        while (groups.some(function(group) { return index < group.length; })) {
            groups.forEach(function(group) {
                var row = group[index];
                if (row && !seen.has(String(row.skuid))) {
                    seen.add(String(row.skuid));
                    rows.push(row);
                }
            });
            index++;
        }
        return rows;
    }

    function loadCatalogs() {
        $.get(baseUrl + '/v1/goods/index', function(r) {
            if (r.code === 200 && Array.isArray(r.data)) {
                catalogs = r.data;
                baseUrlMedia = (r.base_url || '').replace(/\/$/, '');
                var catalogId = Number(getUrlParam('catalog_id') || getUrlParam('typeid'));
                currentCatalogId = catalogs.some(function(cat) { return Number(cat.catalog_id) === catalogId; }) ? catalogId : 'all';
                renderCategoryTabs();
                loadProducts(1);
            } else {
                $('#category-tabs').html('<p class="cat-loading">' + t('no_products') + '</p>');
                $('#product-grid').html('<div class="product-loading">' + t('no_products') + '</div>');
            }
        }).fail(function() {
            $('#category-tabs').html('<p class="cat-loading">' + t('loading') + '</p>');
            $('#product-grid').html('<div class="product-loading">' + t('no_products') + '</div>');
        });
    }

    function renderCategoryTabs() {
        var total = catalogs.reduce(function(sum, cat) { return sum + (cat.sku || []).length; }, 0);
        var allActive = currentCatalogId === 'all';
        var html = '<button type="button" class="catalog-tab' + (allActive ? ' active' : '') + '" data-catalog-id="all" aria-pressed="' + allActive + '">' + t('all_products') + ' (' + total + ')</button>';
        catalogs.forEach(function(cat) {
            var active = currentCatalogId === Number(cat.catalog_id);
            html += '<button type="button" class="catalog-tab' + (active ? ' active' : '') + '" data-catalog-id="' + cat.catalog_id + '" aria-pressed="' + active + '">' + String(cat.catalog_name || '').replace(/&/g, '&amp;').replace(/</g, '&lt;') + ' (' + (cat.sku || []).length + ')</button>';
        });
        $('#category-tabs').html(html || '<span class="cat-loading">' + t('all_products') + '</span>');

        $('#category-tabs').off('click.catalogTab').on('click.catalogTab', '.catalog-tab', function() {
            var value = $(this).data('catalog-id');
            currentCatalogId = value === 'all' ? 'all' : Number(value);
            history.replaceState(null, '', 'buyer_products.html' + (currentCatalogId === 'all' ? '' : '?catalog_id=' + currentCatalogId));
            renderCategoryTabs();
            loadProducts(1);
        });
    }

    function loadProducts(page) {
        var rows = rowsForSelection();
        pageMax = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
        currentPage = Math.max(1, Math.min(Number(page) || 1, pageMax));
        var offset = (currentPage - 1) * PAGE_SIZE;
        var data = rows.slice(offset, offset + PAGE_SIZE);
        $('#product-grid').html(data.length ? data.map(renderProductCard).join('') : '<div class="product-loading">' + t('no_products') + '</div>');
        $('#procurement-summary').text(t('page_summary')
            .replace('{start}', rows.length ? offset + 1 : 0)
            .replace('{end}', Math.min(offset + PAGE_SIZE, rows.length))
            .replace('{total}', rows.length));
        renderPager();
    }

    function renderPager() {
        if (pageMax <= 1) {
            $('#pager-wrap').hide();
            return;
        }
        $('#pager-wrap').show();
        var html = '';
        for (var i = 1; i <= pageMax; i++) {
            var cls = (i === currentPage) ? ' current' : '';
            html += '<a href="javascript:;" class="pager-num' + cls + '" data-page="' + i + '">' + i + '</a>';
        }
        $('#pager-nums').html(html);

        $('#pager-prev').toggleClass('disabled', currentPage <= 1);
        $('#pager-next').toggleClass('disabled', currentPage >= pageMax);

        $('#pager-nums .pager-num').on('click', function() {
            var p = parseInt($(this).data('page'), 10);
            if (p && p !== currentPage) loadProducts(p);
        });
        $('#pager-prev').off('click').on('click', function() {
            if (currentPage > 1) loadProducts(currentPage - 1);
        });
        $('#pager-next').off('click').on('click', function() {
            if (currentPage < pageMax) loadProducts(currentPage + 1);
        });
    }

    function loadRecommended() {
        $.get(baseUrl + '/v1/goods/recommended-products', function(r) {
            if (r.code === 200 && r.data && r.data.length) {
                var data = r.data.slice(0, 6);
                var IMG = (r.base_url || baseUrlMedia || '').replace(/\/$/, '');
                var html = '';
                data.forEach(function(el) {
                    var title = productTitle(el);
                    var imgUrl = el.image && IMG ? (IMG + (String(el.image).indexOf('/') === 0 ? '' : '/') + el.image) : '';
                    var imgHtml = imgUrl
                        ? '<img src="' + imgUrl + '" alt="' + title.replace(/"/g, '&quot;') + '">'
                        : '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:#2e7d32;">' + (el.image_text || title || '') + '</div>';
                    var price = el.price || 0;
                    html += '<a href="product_details.html?skuid=' + (el.skuid || el.id) + '" class="recommend-item">' +
                        '<div class="rec-img">' + imgHtml + '</div>' +
                        '<div class="rec-name">' + title.replace(/</g, '&lt;') + '</div>' +
                        '<div class="rec-price" data-usd="' + price + '">' + formatPrice(price) + '</div>' +
                        '</a>';
                });
                $('#recommend-grid').html(html);
            } else {
                $('#recommend-grid').html('<span class="recommend-loading">' + t('recommend_empty') + '</span>');
            }
        }).fail(function() {
            $('#recommend-grid').html('<span class="recommend-loading">' + t('recommend_empty') + '</span>');
        });
    }

    function applyI18nProducts() {
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            var key = el.getAttribute('data-i18n');
            if (i18n[getLang()] && i18n[getLang()][key]) {
                el.textContent = i18n[getLang()][key];
            }
        });
        $("#pager-prev").text(i18n[getLang()].prev_page || 'Previous');
        $("#pager-next").text(i18n[getLang()].next_page || 'Next');
        $('.btn-add-cart').each(function() {
            var tAdd = (i18n[getLang()] && i18n[getLang()].add_cart) ? i18n[getLang()].add_cart : 'Add to Cart';
            if ($(this).closest('.product-card').length) $(this).text(tAdd);
        });
        var traceT = (i18n[getLang()] && i18n[getLang()].trace_btn) ? i18n[getLang()].trace_btn : 'Traceability';
        $('.btn-trace-link').text(traceT);
    }

    $(function() {
        applyI18nProducts();
        loadCatalogs();
        loadRecommended();

        $('#currency-select').on('change', function() {
            currentCurrency = this.value;
            $('.product-price').each(function() {
                var usd = $(this).data('usd');
                if (usd != null) $(this).text(formatPrice(usd));
            });
            $('#recommend-grid .rec-price').each(function() {
                var usd = $(this).data('usd');
                if (usd != null) $(this).text(formatPrice(usd));
            });
        });

        $('#lang-switch .lang-btn').on('click', function() {
            var lang = $(this).data('lang');
            localStorage.setItem('buyer_lang', lang);
            applyI18nProducts();
            renderCategoryTabs();
            loadProducts(currentPage);
        });

        $('#btn-search').on('click', function() {
            var q = $('#search-input').val().trim();
            if (q) location.href = 'search_list.html?keyword=' + encodeURIComponent(q);
        });
        $('#search-input').on('keypress', function(e) {
            if (e.key === 'Enter') {
                var q = $(this).val().trim();
                if (q) location.href = 'search_list.html?keyword=' + encodeURIComponent(q);
            }
        });

        var cartCount = 0;
        try {
            if (typeof AuthStorage !== 'undefined' && AuthStorage && AuthStorage.getCount) {
                cartCount = AuthStorage.getCount();
            }
        } catch (e) {}
        $('#cart-count').text(cartCount || 0);
    });
})();
