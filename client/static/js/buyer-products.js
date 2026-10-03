/**
 * 买家商品采购页 - 集成在工作台内
 * 分类切换、分页、推荐商品、i18n
 */
(function() {
    'use strict';

    var RATES = { USD: 1, AED: 3.67, SAR: 3.75 };
    var currentCurrency = 'USD';
    var catalogs = [];
    var currentCatalogId = null;
    var currentPage = 1;
    var pageMax = 1;
    var pageSize = 12;
    var baseUrlMedia = '';

    var i18n = {
        zh: {
            procure_title: '商品采购 - 茗越山关跨境电商 9710 报关数字系统',
            all_products: '全部产品',
            loading: '加载中...',
            no_products: '暂无商品',
            prev_page: '上一页',
            next_page: '下一页',
            recommend_title: '推荐商品',
            recommend_empty: '暂无推荐',
            add_cart: '加入采购车',
            trace_btn: '溯源'
        },
        en: {
            procure_title: 'Product Procurement - Mingyue Shanguan 9710 Customs Digital System',
            all_products: 'All Products',
            loading: 'Loading...',
            no_products: 'No products',
            prev_page: 'Previous',
            next_page: 'Next',
            recommend_title: 'Recommended',
            recommend_empty: 'No recommendations',
            add_cart: 'Add to Cart',
            trace_btn: 'Traceability'
        },
        ar: {
            procure_title: 'المشتريات - مينغ يوي شانغوان 9710',
            all_products: 'جميع المنتجات',
            loading: 'جاري التحميل...',
            no_products: 'لا توجد منتجات',
            prev_page: 'السابق',
            next_page: 'التالي',
            recommend_title: 'موصى به',
            recommend_empty: 'لا توجد توصيات',
            add_cart: 'أضف للسلة',
            trace_btn: 'التتبع'
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
        var traceCode = 'TR-' + skuid;
        return '<div class="product-card" data-skuid="' + skuid + '">' +
            '<div class="product-badges"><span class="badge-gi">📍 GI</span></div>' +
            '<div class="product-img-wrap">' + imgHtml + '</div>' +
            '<a href="trace.html?code=' + traceCode + '" class="btn-trace-link" target="_blank" data-i18n="trace_btn">溯源</a>' +
            '<h3 class="product-name"><a href="product_details.html?skuid=' + skuid + '">' + title.replace(/</g, '&lt;') + '</a></h3>' +
            '<p class="product-spec">' + spec.replace(/</g, '&lt;') + '</p>' +
            '<div class="product-price" data-usd="' + (el.price || 0) + '" data-aed="' + ((el.price || 0) * 3.67).toFixed(0) + '" data-sar="' + ((el.price || 0) * 3.75).toFixed(0) + '">' + formatPrice(el.price) + '</div>' +
            '<button type="button" class="btn-add-cart">加入采购车</button>' +
            '</div>';
    }

    function loadCatalogs() {
        $.get(baseUrl + '/v1/goods/index', function(r) {
            if (r.code === 200 && r.data && r.data.length) {
                catalogs = r.data;
                baseUrlMedia = (r.base_url || '').replace(/\/$/, '');
                renderCategoryTabs();
                var catalogId = getUrlParam('catalog_id') || getUrlParam('typeid') || (catalogs[0] && catalogs[0].catalog_id);
                if (catalogId) {
                    currentCatalogId = parseInt(catalogId, 10);
                    loadProducts(1);
                } else {
                    $('#product-grid').html('<div class="product-loading">' + t('no_products') + '</div>');
                }
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
        var html = '';
        catalogs.forEach(function(cat) {
            var active = (currentCatalogId === cat.catalog_id) ? ' active' : '';
            html += '<button type="button" class="catalog-tab' + active + '" data-catalog-id="' + cat.catalog_id + '">' + (cat.catalog_name || '') + '</button>';
        });
        $('#category-tabs').html(html || '<span class="cat-loading">' + t('all_products') + '</span>');

        $('#category-tabs').off('click.catalogTab').on('click.catalogTab', '.catalog-tab', function() {
            currentCatalogId = parseInt($(this).data('catalog-id'), 10);
            if (!currentCatalogId) return;
            history.replaceState(null, '', 'buyer_products.html?catalog_id=' + currentCatalogId);
            $('#category-tabs .catalog-tab').removeClass('active');
            $(this).addClass('active');
            loadProducts(1);
        });
    }

    function loadProducts(page) {
        currentPage = page || 1;
        $('#product-grid').html('<div class="product-loading">' + t('loading') + '</div>');
        $('#pager-wrap').hide();

        $.get(baseUrl + '/v1/goods/catalogs/' + currentCatalogId + '?launched=true&page=' + currentPage, function(r) {
            if (r.code === 200) {
                baseUrlMedia = (r.base_url || baseUrlMedia || '').replace(/\/$/, '');
                var data = r.data || [];
                var total = (r.paginator && r.paginator.total) || 0;
                pageSize = (r.paginator && r.paginator.pagesize) || 12;
                pageMax = Math.ceil(total / pageSize) || 1;

                if (data.length === 0) {
                    $('#product-grid').html('<div class="product-loading">' + t('no_products') + '</div>');
                } else {
                    var html = '';
                    data.forEach(function(el) {
                        html += renderProductCard(el);
                    });
                    $('#product-grid').html(html);

                    renderPager();
                    bindProductEvents();
                }
            } else {
                $('#product-grid').html('<div class="product-loading">' + t('no_products') + '</div>');
            }
        }).fail(function() {
            $('#product-grid').html('<div class="product-loading">' + t('no_products') + '</div>');
        });
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

    function bindProductEvents() {
        $('.product-card .btn-add-cart').on('click', function() {
            var card = $(this).closest('.product-card');
            var name = card.find('.product-name').text().trim();
            var lang = getLang();
            var msg = (lang === 'zh' ? '已加入采购车：' : (lang === 'ar' ? 'تمت الإضافة: ' : 'Added to cart: ')) + name;
            alert(msg);
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
