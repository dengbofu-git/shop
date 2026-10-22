/**
 * 中东买家工作台 - 采购+订单追踪（系统：tea_saas）
 * 三语、RTL、多币种、场景+茶类筛选
 */
(function() {
    'use strict';

    var currentCurrency = 'USD';

    var i18n = {
        zh: {
            brand_name: 'tea_saas',
            buyer_title: '买家工作台',
            nav_home: '首页',
            nav_procure: '商品采购',
            nav_orders: '我的订单',
            nav_logistics: '物流追踪',
            nav_settlement: '对账结算',
            nav_halal: '清真资质库',
            nav_help: '帮助中心',
            nav_ai_service: '智能客服',
            currency: '币种',
            whatsapp: 'WhatsApp 客服',
            whatsapp_lbl: 'WhatsApp 客服',
            search_placeholder: '搜索商品',
            favorites: '我的收藏',
            recent: '最近浏览',
            cart: '采购车',
            my_orders: '我的最近订单',
            orders_all: '查看全部',
            section_featured: '精选商品',
            section_featured_sub: '按茶类浏览在售商品，每页10件，可翻页查看全部商品。',
            view_all: '查看全部',
            grid_empty: '该茶类暂无可售商品，请查看其他分类。',
            grid_summary: '当前显示 {start}–{end} 件，共 {total} 件可售商品',
            grid_prev: '上一页',
            grid_next: '下一页',
            grid_pagination: '商品分页',
            grid_retry: '重新加载',
            brand_short: 'tea_saas',
            banner1_title: '开斋节礼盒促销',
            banner1_desc: '英德红茶礼盒 · 清真认证',
            banner1_price: '$68 起',
            banner2_title: '2024 明前龙井新茶',
            banner2_desc: '地理标志 · 产地可溯',
            banner2_price: '$45 起',
            banner3_title: '大宗采购阶梯优惠',
            banner3_desc: '100件以上 15% off · 500件以上 25% off',
            banner3_price: '询盘报价',
            tea_all: '全部',
            tea_black: '红茶',
            tea_green: '绿茶',
            tea_oolong: '乌龙茶',
            tea_puer: '普洱茶',
            tea_white: '白茶',
            tea_yellow: '黄茶',
            tea_scented: '花茶',
            tea_dark: '黑茶',
            add_cart: '加入采购车',
            quick_preview: '快速预览',
            banner_empty: '暂无已上架、有库存的商品作为轮播',
            banner_loading: '正在加载轮播…',
            banner_loading_sub: '从数据库读取可售商品',
            carousel_heading: '发现一款好茶',
            carousel_label: '精选茶品轮播',
            carousel_role: '轮播图',
            carousel_slide: '轮播项',
            carousel_hint: '自动展示精选茶品，悬停或聚焦暂停，可用左右方向键或横滑切换。',
            carousel_error: '轮播加载失败，请重新加载。',
            carousel_price: '参考价格',
            carousel_image_missing: '暂无商品图片',
            grid_loading: '正在加载精选商品…',
            grid_loading_err: '无法加载茶类商品，请检查网络或重新加载。',
            btn_view_sku: '查看商品',
            preview_title: '快速预览',
            preview_note: '商品信息预览，当前价格与规格以商品详情为准。',
            trace_btn: '溯源',
            inquiry_now: '立即询价',
            view_logistics: '查看物流',
            settlement: '对账详情',
            after_sale: '申请售后',
            status_shipped: '已发货',
            status_processing: '处理中',
            from_price: '起',
            adv_title: '平台核心优势',
            adv_1t: '正品溯源',
            adv_1d: '从茶园到餐桌全流程可追溯',
            adv_2t: '清真认证',
            adv_2d: '合作供应商具备合规 Halal 资质',
            adv_3t: '国际履约',
            adv_3d: '采购、订单与国际运输协同',
            adv_4t: '大宗优惠',
            adv_4d: '量大可阶梯议价',
            quick_title: '快速服务',
            q_logistics: '物流追踪',
            q_settlement: '对账结算',
            q_after: '申请售后',
            q_contact: '联系我们',
            origin_title: '热门产地',
            o_anxi: '福建安溪 · 铁观音',
            o_puer: '云南普洱',
            o_hz: '浙江杭州 · 龙井',
            o_yd: '广东英德 · 英德红茶',
            o_wy: '福建武夷山 · 大红袍',
            o_hs: '安徽黄山 · 毛峰',
            menu_personal: '个人信息',
            menu_settings: '账户设置',
            menu_logout: '退出登录',
            hover_p1: '产地：广东英德',
            hover_p2: '冲泡：95℃ · 3–5 分钟',
            hover_p3: '产地：广东潮州',
            hover_p4: '冲泡：100℃ · 可冲 5–8 泡',
            hover_p5: '特点：礼盒包装',
            hover_p6: '场景：节日馈赠',
            hover_p7: '产地：浙江杭州',
            hover_p8: '冲泡：80–85℃',
            ft_about: '关于',
            ft_tagline: '跨境茶叶 SaaS 平台',
            ft_description: '从发现一款好茶，到开启下一次采购，让选茶与经营更从容。',
            ft_bottom_note: '为跨境茶叶采购与经营而设计',
            ft_intro: '公司介绍',
            ft_news: '新闻动态',
            ft_help: '帮助',
            ft_guide: '采购指南',
            ft_ship: '物流说明',
            ft_contact: '联系',
            ft_follow: '关注我们',
            ft_ig: 'Instagram',
            ft_copy: '© 2026 tea_saas · 中国地标茶出海中东',
            add_cart_msg: '已加入采购车：',
            inquiry_msg_prefix: '询价：'
        },
        en: {
            brand_name: 'tea_saas',
            buyer_title: 'Buyer Portal',
            nav_home: 'Home',
            nav_procure: 'Procurement',
            nav_orders: 'My Orders',
            nav_logistics: 'Logistics',
            nav_settlement: 'Settlement',
            nav_halal: 'Halal Cert',
            nav_help: 'Help',
            nav_ai_service: 'AI Support',
            currency: 'Currency',
            whatsapp: 'WhatsApp',
            whatsapp_lbl: 'WhatsApp',
            search_placeholder: 'Search products',
            favorites: 'Favorites',
            recent: 'Recent',
            cart: 'Cart',
            my_orders: 'My Recent Orders',
            orders_all: 'View all',
            section_featured: 'Featured',
            section_featured_sub: 'Browse 10 products per page by tea category. Use pagination to see every product.',
            view_all: 'View all',
            grid_empty: 'No available products in this category. Try another category.',
            grid_summary: 'Showing {start}–{end} of {total} available products',
            grid_prev: 'Previous',
            grid_next: 'Next',
            grid_pagination: 'Product pages',
            grid_retry: 'Retry',
            brand_short: 'tea_saas',
            banner1_title: 'Eid Gift Box',
            banner1_desc: 'Yingde black tea gift box · Halal certified',
            banner1_price: 'From $68',
            banner2_title: '2024 Pre-Qingming Longjing',
            banner2_desc: 'Geographic indication · traceable origin',
            banner2_price: 'From $45',
            banner3_title: 'Bulk tier discount',
            banner3_desc: '100+ units: 15% off · 500+ units: 25% off',
            banner3_price: 'Request quote',
            tea_all: 'All',
            tea_black: 'Black',
            tea_green: 'Green',
            tea_oolong: 'Oolong',
            tea_puer: 'Pu\'er',
            tea_white: 'White',
            tea_yellow: 'Yellow',
            tea_scented: 'Scented',
            tea_dark: 'Dark tea',
            add_cart: 'Add to cart',
            quick_preview: 'Quick view',
            banner_empty: 'No in-stock products for the carousel',
            banner_loading: 'Loading carousel…',
            banner_loading_sub: 'From database',
            carousel_heading: 'Discover your next tea',
            carousel_label: 'Featured tea carousel',
            carousel_role: 'carousel',
            carousel_slide: 'slide',
            carousel_hint: 'Tea rotates automatically. Hover or focus to pause; use arrow keys or swipe to browse.',
            carousel_error: 'Could not load the carousel. Please retry.',
            carousel_price: 'Reference price',
            carousel_image_missing: 'Product image unavailable',
            grid_loading: 'Loading featured products…',
            grid_loading_err: 'Could not load products. Check your connection.',
            btn_view_sku: 'View product',
            preview_title: 'Quick view',
            preview_note: 'Product preview. Check the product details for current prices and specifications.',
            trace_btn: 'Traceability',
            inquiry_now: 'Inquire now',
            view_logistics: 'View logistics',
            settlement: 'Settlement',
            after_sale: 'After-sales',
            status_shipped: 'Shipped',
            status_processing: 'Processing',
            from_price: 'from',
            adv_title: 'Why us',
            adv_1t: 'Traceability',
            adv_1d: 'Full chain from garden to table',
            adv_2t: 'Halal',
            adv_2d: 'Compliant suppliers',
            adv_3t: 'Global delivery',
            adv_3d: 'Procurement, orders & logistics',
            adv_4t: 'Volume pricing',
            adv_4d: 'Tiered negotiation for bulk',
            quick_title: 'Quick links',
            q_logistics: 'Tracking',
            q_settlement: 'Settlement',
            q_after: 'After-sales',
            q_contact: 'Contact',
            origin_title: 'Popular origins',
            o_anxi: 'Anxi, Fujian · Tieguanyin',
            o_puer: 'Yunnan Pu\'er',
            o_hz: 'Hangzhou, Zhejiang · Longjing',
            o_yd: 'Yingde, Guangdong',
            o_wy: 'Wuyishan, Fujian',
            o_hs: 'Huangshan, Anhui',
            menu_personal: 'Personal info',
            menu_settings: 'Account security',
            menu_logout: 'Sign out',
            hover_p1: 'Origin: Yingde, Guangdong',
            hover_p2: 'Brew: 95°C · 3–5 min',
            hover_p3: 'Origin: Chaozhou, Guangdong',
            hover_p4: 'Brew: 100°C · 5–8 steeps',
            hover_p5: 'Feature: gift box',
            hover_p6: 'Occasion: festivals',
            hover_p7: 'Origin: Hangzhou, Zhejiang',
            hover_p8: 'Brew: 80–85°C',
            ft_about: 'About',
            ft_tagline: 'A SaaS platform for cross-border tea trade',
            ft_description: 'From finding your next tea to placing your next order, make sourcing and business feel simpler.',
            ft_bottom_note: 'Built for tea sourcing and cross-border business',
            ft_intro: 'Company',
            ft_news: 'News',
            ft_help: 'Help',
            ft_guide: 'Buying guide',
            ft_ship: 'Shipping',
            ft_contact: 'Contact',
            ft_follow: 'Follow',
            ft_ig: 'Instagram',
            ft_copy: '© 2026 tea_saas — China origin tea to MENA',
            add_cart_msg: 'Added: ',
            inquiry_msg_prefix: 'Inquiry: '
        },
        ar: {
            brand_name: 'tea_saas',
            buyer_title: 'بوابة المشتري',
            nav_home: 'الرئيسية',
            nav_procure: 'المشتريات',
            nav_orders: 'طلباتي',
            nav_logistics: 'الشحن',
            nav_settlement: 'التسوية',
            nav_halal: 'شهادة الحلال',
            nav_help: 'المساعدة',
            nav_ai_service: 'المساعد الذكي',
            currency: 'العملة',
            whatsapp: 'واتساب',
            whatsapp_lbl: 'واتساب',
            search_placeholder: 'البحث عن المنتجات',
            favorites: 'المفضلة',
            recent: 'المشاهدة الأخيرة',
            cart: 'السلة',
            my_orders: 'طلباتي الأخيرة',
            orders_all: 'عرض الكل',
            section_featured: 'مميز',
            section_featured_sub: 'تصفح 10 منتجات في كل صفحة حسب فئة الشاي. تنقل بين الصفحات لعرض جميع المنتجات.',
            view_all: 'عرض الكل',
            grid_empty: 'لا توجد منتجات متاحة في هذه الفئة. اختر فئة أخرى.',
            grid_summary: 'عرض {start}–{end} من أصل {total} منتجاً متاحاً',
            grid_prev: 'السابق',
            grid_next: 'التالي',
            grid_pagination: 'صفحات المنتجات',
            grid_retry: 'إعادة المحاولة',
            brand_short: 'tea_saas',
            banner1_title: 'صندوق هدايا العيد',
            banner1_desc: 'شاي ينغدي · معتمد حلال',
            banner1_price: 'من 68$',
            banner2_title: 'لونججينغ 2024',
            banner2_desc: 'علامة جغرافية · أصل قابل للتتبع',
            banner2_price: 'من 45$',
            banner3_title: 'خصم بالجملة',
            banner3_desc: '100+ وحدة: 15% · 500+ وحدة: 25%',
            banner3_price: 'طلب عرض سعر',
            tea_all: 'الكل',
            tea_black: 'أسود',
            tea_green: 'أخضر',
            tea_oolong: 'أولونغ',
            tea_puer: 'بوير',
            tea_white: 'أبيض',
            tea_yellow: 'أصفر',
            tea_scented: 'معطر',
            tea_dark: 'شاي داكن',
            add_cart: 'أضف للسلة',
            quick_preview: 'معاينة',
            banner_empty: 'لا بيانات عرض',
            banner_loading: 'جاري التحميل…',
            banner_loading_sub: 'من قاعدة البيانات',
            carousel_heading: 'اكتشف شايك القادم',
            carousel_label: 'عارض منتجات الشاي',
            carousel_role: 'عارض شرائح',
            carousel_slide: 'شريحة',
            carousel_hint: 'يتبدل الشاي تلقائياً. مرّر المؤشر أو ركّز للإيقاف المؤقت، واستخدم الأسهم أو السحب للتصفح.',
            carousel_error: 'تعذر تحميل العرض. حاول مجدداً.',
            carousel_price: 'سعر مرجعي',
            carousel_image_missing: 'صورة المنتج غير متاحة',
            grid_loading: 'جاري تحميل المنتجات…',
            grid_loading_err: 'تعذر التحميل',
            btn_view_sku: 'عرض',
            preview_title: 'معاينة سريعة',
            preview_note: 'معاينة المنتج. راجع تفاصيل المنتج للأسعار والمواصفات الحالية.',
            trace_btn: 'التتبع',
            inquiry_now: 'استفسر الآن',
            view_logistics: 'عرض الشحن',
            settlement: 'التسوية',
            after_sale: 'ما بعد البيع',
            status_shipped: 'تم الشحن',
            status_processing: 'قيد المعالجة',
            from_price: 'من',
            adv_title: 'مميزات المنصة',
            adv_1t: 'التتبع',
            adv_1d: 'من المزرعة للمائدة',
            adv_2t: 'الحلال',
            adv_2d: 'موردون معتمدون',
            adv_3t: 'لوجستيات',
            adv_3d: 'المشتريات والطلبات والشحن',
            adv_4t: 'سعر الجملة',
            adv_4d: 'تدرجات للكميات',
            quick_title: 'خدمات سريعة',
            q_logistics: 'التتبع',
            q_settlement: 'التسوية',
            q_after: 'ما بعد البيع',
            q_contact: 'اتصل',
            origin_title: 'أصول شهيرة',
            o_anxi: 'آنشي · تيغوانيين',
            o_puer: 'يونان بوير',
            o_hz: 'هانغتشو · لونججينغ',
            o_yd: 'ينغدي، قوانغدونغ',
            o_wy: 'وويي شان',
            o_hs: 'هوانغشان',
            menu_personal: 'المعلومات الشخصية',
            menu_settings: 'إعدادات الحساب',
            menu_logout: 'تسجيل الخروج',
            hover_p1: 'الأصل: ينغدي',
            hover_p2: 'التخمير: 95°م',
            hover_p3: 'الأصل: تشاوتشو',
            hover_p4: 'التخمير: 100°م',
            hover_p5: 'علبة هدايا',
            hover_p6: 'للمناسبات',
            hover_p7: 'الأصل: هانغتشو',
            hover_p8: '80–85°م',
            ft_about: 'عن',
            ft_tagline: 'منصة SaaS لتجارة الشاي عبر الحدود',
            ft_description: 'من اكتشاف شاي جديد إلى طلبك التالي، نجعل التوريد وإدارة الأعمال أكثر سهولة.',
            ft_bottom_note: 'مصممة لتوريد الشاي والتجارة عبر الحدود',
            ft_intro: 'عن الشركة',
            ft_news: 'الأخبار',
            ft_help: 'المساعدة',
            ft_guide: 'دليل الشراء',
            ft_ship: 'الشحن',
            ft_contact: 'اتصال',
            ft_follow: 'تابعنا',
            ft_ig: 'إنستغرام',
            ft_copy: '© 2026 tea_saas',
            add_cart_msg: 'تمت الإضافة: ',
            inquiry_msg_prefix: 'استفسار: '
        }
    };

    function getT(lang) {
        return i18n[lang] || i18n.en;
    }

    function getApiBase() {
        if (typeof baseUrl !== 'undefined' && baseUrl) return String(baseUrl).replace(/\/$/, '');
        return 'http://127.0.0.1:8000';
    }

    var buyerCarousel = null;
    var catalogPreview = null;

    function setPriceDataFromCny(el, cny) {
        var c = parseFloat(cny);
        if (isNaN(c)) c = 0;
        el.setAttribute('data-cny', c.toFixed(2));
        el.setAttribute('data-usd', (c * 0.14).toFixed(0));
        el.setAttribute('data-aed', (c * 0.51).toFixed(0));
        el.setAttribute('data-sar', (c * 0.52).toFixed(0));
        el.setAttribute('data-eur', (c * 0.13).toFixed(0));
    }

    function addToCartFromCard(card) {
        var skuId = card.getAttribute('data-sku-id') || card.getAttribute('data-skuid');
        if (!skuId) return;
        var nameEl = card.querySelector('.product-name');
        var name = nameEl ? nameEl.textContent : '';
        var username = typeof AuthStorage !== 'undefined' && AuthStorage.getUser && AuthStorage.getUser();
        var token = typeof AuthStorage !== 'undefined' && AuthStorage.getToken && AuthStorage.getToken();
        var lang = localStorage.getItem('buyer_lang') || 'zh';
        var tt = getT(lang);
        if (username && token) {
            $.ajax({
                type: 'POST',
                url: getApiBase() + '/v1/carts/' + encodeURIComponent(username),
                contentType: 'application/json',
                dataType: 'json',
                beforeSend: function(xhr) {
                    xhr.setRequestHeader('authorization', token);
                },
                data: JSON.stringify({ sku_id: parseInt(skuId, 10), count: 1 }),
                success: function(res) {
                    if (res.code === 403) {
                        alert('登录已过期，请重新登录');
                        if (AuthStorage.clear) AuthStorage.clear();
                        location.href = 'login.html';
                        return;
                    }
                    if (res.code === 200) {
                        var cnt = res.data && res.data.carts_count;
                        if (cnt != null && AuthStorage.setCount) AuthStorage.setCount(String(cnt));
                        if ($('#cart-count').length) $('#cart-count').text(cnt || 0);
                        alert((tt.add_cart_msg || '') + name);
                    } else {
                        alert((res && res.error) || '操作失败');
                    }
                },
                error: function() {
                    alert('网络异常');
                }
            });
        } else {
            var price = card.getAttribute('data-cny') || (card.querySelector('.product-price') && card.querySelector('.product-price').getAttribute('data-cny')) || '0';
            var pimg = card.getAttribute('data-pimg') || '';
            var row = {
                id: String(skuId),
                count: 1,
                name: name,
                price: parseFloat(price) || 0,
                default_image_url: pimg,
                selected: true,
                sku_sale_attr_name: [],
                sku_sale_attr_val: []
            };
            var oldData = null;
            try {
                oldData = JSON.parse(window.localStorage.getItem('cart') || 'null');
            } catch (e) {
                oldData = null;
            }
            var list = (oldData && oldData.length) ? oldData.slice() : [];
            var found = false;
            for (var j = 0; j < list.length; j++) {
                if (String(list[j].id) === String(skuId)) {
                    list[j].count = parseInt(list[j].count, 10) + 1;
                    found = true;
                    break;
                }
            }
            if (!found) list.push(row);
            window.localStorage.setItem('cart', JSON.stringify(list));
            var total = 0;
            for (var k = 0; k < list.length; k++) total += parseInt(list[k].count, 10) || 0;
            window.localStorage.setItem('tea_saas_count', String(total));
            if (AuthStorage && AuthStorage.setCount) AuthStorage.setCount(String(total));
            if ($('#cart-count').length) $('#cart-count').text(total);
            alert((tt.add_cart_msg || '') + name);
        }
    }

    function productTitle(it) {
        var spu = (it.spu_name || it.title || it.product_name || '').trim();
        return spu || String(it.name || '').trim();
    }

    function productSpec(it) {
        var title = productTitle(it);
        if (it.caption && String(it.caption).trim()) {
            return String(it.caption).trim();
        }
        var intro = (it.intro && String(it.intro).trim()) ? String(it.intro).trim() : '';
        if (intro && intro !== title) {
            return intro.slice(0, 200);
        }
        var sku = String(it.name || '').trim();
        if (sku && sku !== title) {
            return sku;
        }
        return '';
    }

    function loadBuyerDashboard() {
        var carouselRoot = document.getElementById('buyer-carousel');
        var gGrid = document.getElementById('product-grid');
        var gSk = document.getElementById('product-grid-skeleton');
        var gErr = document.getElementById('product-grid-msg');
        if (!carouselRoot && !gSk && !gErr) return;
        if (gErr) gErr.style.display = 'none';
        if (carouselRoot && window.BuyerCarousel) {
            if (buyerCarousel) buyerCarousel.destroy();
            buyerCarousel = BuyerCarousel.start({
                root: carouselRoot, url: getApiBase() + '/v1/goods/carousel?stable=1&limit=6',
                labels: function() { return getT(localStorage.getItem('buyer_lang') || 'zh'); },
                formatPrice: formatDisplayPrice
            });
        }

        if (gGrid && window.BuyerCatalogPreview) {
            catalogPreview = BuyerCatalogPreview.start({
                url: getApiBase() + '/v1/goods/index',
                tabs: document.getElementById('featured-tea-tabs'), grid: gGrid,
                summary: document.getElementById('featured-summary'), error: gErr,
                retry: document.getElementById('featured-retry'),
                empty: document.getElementById('product-grid-empty'),
                pager: document.getElementById('featured-pagination'), section: document.getElementById('buyer-featured'),
                labels: function() { return getT(localStorage.getItem('buyer_lang') || 'zh'); },
                render: function(rows) { buildProductGrid(rows, gGrid, gSk, gErr); }
            });
        }
    }

    function buildProductGrid(rows, gGrid, gSk, gErr) {
        if (!gGrid) return;
        if (gSk) gSk.remove();
        gGrid.innerHTML = '';
        if (!rows || !rows.length) {
            if (gErr) gErr.style.display = 'none';
            var ge0 = document.getElementById('product-grid-empty');
            if (ge0) ge0.style.display = 'block';
            return;
        }
        if (gErr) gErr.style.display = 'none';
        var empty = document.getElementById('product-grid-empty');
        if (empty) empty.style.display = 'none';
        var lang = localStorage.getItem('buyer_lang') || 'zh';
        var ttx = getT(lang);
        rows.forEach(function(it) {
            var card = document.createElement('div');
            card.className = 'product-card product-card--api';
            card.setAttribute('data-sku-id', String(it.skuid));
            card.setAttribute('data-catalog-id', String(it.catalog_id));
            card.setAttribute('data-pname', productTitle(it));
            card.setAttribute('data-cny', String(it.price != null ? it.price : '0'));
            if (it.image) {
                card.setAttribute('data-pimg', String(it.image).replace(/^\//, ''));
            } else {
                card.setAttribute('data-pimg', '');
            }
            var badges = null;
            if (it.catalog_name) {
                badges = document.createElement('div');
                badges.className = 'product-badges';
                var b1 = document.createElement('span');
                b1.className = 'badge-gi';
                b1.textContent = '\uD83D\uDCCD ' + it.catalog_name;
                badges.appendChild(b1);
            }
            var detailsUrl = 'product_details.html?skuid=' + it.skuid;
            var wrap = document.createElement('a');
            wrap.className = 'product-img-wrap';
            wrap.href = detailsUrl;
            wrap.setAttribute('aria-label', productTitle(it));
            var img = document.createElement('img');
            img.alt = '';
            img.src = it.image_url || (getApiBase() + '/v1/goods/sku/' + it.skuid + '/image');
            img.onerror = function() {
                var fb = '/static/images/cart/product_normal.png';
                if (this.src.indexOf(fb) === -1) {
                    this.onerror = null;
                    this.src = fb;
                    this.style.display = '';
                } else {
                    this.style.display = 'none';
                }
            };
            wrap.appendChild(img);
            var h3 = document.createElement('h3');
            h3.className = 'product-name';
            var titleLink = document.createElement('a');
            titleLink.href = detailsUrl;
            titleLink.textContent = productTitle(it);
            h3.appendChild(titleLink);
            var spec = document.createElement('p');
            spec.className = 'product-spec';
            spec.textContent = productSpec(it);
            var price = document.createElement('div');
            price.className = 'product-price';
            setPriceDataFromCny(price, it.price);
            var act = document.createElement('div');
            act.className = 'product-actions-row';
            var bAdd = document.createElement('button');
            bAdd.type = 'button';
            bAdd.className = 'btn-add-cart';
            bAdd.setAttribute('data-i18n', 'add_cart');
            bAdd.textContent = ttx.add_cart;
            act.appendChild(bAdd);
            if (badges) card.appendChild(badges);
            card.appendChild(wrap);
            card.appendChild(h3);
            card.appendChild(spec);
            card.appendChild(price);
            if (typeof Storefront !== 'undefined') card.appendChild(Storefront.merchantLink(it.merchant));
            card.appendChild(act);
            gGrid.appendChild(card);
        });
        var langNow = localStorage.getItem('buyer_lang') || 'zh';
        applyI18n(langNow);
        updatePrices();
    }

    function syncLangButtons(lang) {
        var langSwitch = document.getElementById('lang-switch');
        if (!langSwitch) return;
        langSwitch.querySelectorAll('.lang-btn').forEach(function(b) {
            b.classList.toggle('active', b.getAttribute('data-lang') === lang);
        });
    }

    function setLang(lang) {
        document.documentElement.lang = lang === 'ar' ? 'ar' : (lang === 'en' ? 'en' : 'zh');
        document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
        if (document.body) document.body.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
        localStorage.setItem('buyer_lang', lang);
        applyI18n(lang);
        syncLangButtons(lang);
    }

    function applyI18n(lang) {
        var t = getT(lang);
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            var key = el.getAttribute('data-i18n');
            if (key && t[key] !== undefined) el.textContent = t[key];
        });
        var ph = document.getElementById('search-input');
        if (ph) ph.placeholder = t.search_placeholder;
        var wa = document.querySelector('.whatsapp-btn');
        if (wa) wa.textContent = '\uD83D\uDCAC ' + (t.whatsapp_lbl || t.whatsapp);
        document.querySelectorAll('.btn-add-cart').forEach(function(btn) {
            btn.textContent = t.add_cart;
        });
        document.querySelectorAll('.btn-quick-preview').forEach(function(btn) {
            btn.textContent = t.quick_preview;
        });
        document.querySelectorAll('.btn-view-sku').forEach(function(el) {
            if (t.btn_view_sku) el.textContent = t.btn_view_sku;
        });
        var orderBtnTexts = [t.view_logistics, t.settlement, t.after_sale];
        document.querySelectorAll('.order-actions .btn-order').forEach(function(btn, i) {
            if (orderBtnTexts[i % 3]) btn.textContent = orderBtnTexts[i % 3];
        });
        document.querySelectorAll('.order-status.shipped').forEach(function(el) {
            el.textContent = t.status_shipped;
        });
        document.querySelectorAll('.order-status.processing').forEach(function(el) {
            el.textContent = t.status_processing;
        });
        document.querySelectorAll('.btn-trace-link').forEach(function(el) {
            if (t.trace_btn) el.textContent = t.trace_btn;
        });
        document.querySelectorAll('a.btn-banner-inquiry.btn-view-sku').forEach(function(el) {
            if (t.btn_view_sku) el.textContent = t.btn_view_sku;
        });
        if (document.getElementById('buyer-banner-slider')) {
            document.title = (t.brand_name || t.brand_short || '') + ' · ' + (t.buyer_title || '');
        }
        updatePrices();
        if (catalogPreview) catalogPreview.setLanguage();
        if (buyerCarousel) buyerCarousel.setLanguage();
    }

    function formatDisplayPrice(value) {
        var amount = parseFloat(value) || 0;
        var rates = {CNY: 1, USD: 0.14, AED: 0.51, SAR: 0.52, EUR: 0.13};
        var symbols = {CNY: '¥', USD: '$', AED: 'AED ', SAR: 'SAR ', EUR: '€'};
        var currency = Object.prototype.hasOwnProperty.call(rates, currentCurrency) ? currentCurrency : 'CNY';
        return symbols[currency] + (amount * rates[currency]).toFixed(2);
    }

    function updatePrices() {
        document.querySelectorAll('.product-price').forEach(function(el) {
            if (el.getAttribute('data-cny') !== null) {
                el.textContent = formatDisplayPrice(el.getAttribute('data-cny'));
                return;
            }
            var lower = currentCurrency.toLowerCase();
            var val = el.getAttribute('data-' + lower);
            if (val == null) return;
            var out;
            if (currentCurrency === 'USD') out = '$' + val;
            else if (currentCurrency === 'AED') out = 'AED ' + val;
            else if (currentCurrency === 'SAR') out = 'SAR ' + val;
            else if (currentCurrency === 'EUR') out = '€' + val;
            else out = val + ' ' + currentCurrency;
            el.textContent = out;
        });
        if (buyerCarousel) buyerCarousel.refreshPrices();
    }

    function openUserMenu(open) {
        var d = document.getElementById('user-dropdown');
        var tr = document.getElementById('user-trigger');
        if (d) {
            d.classList.toggle('is-open', open);
            d.setAttribute('aria-hidden', open ? 'false' : 'true');
            d.inert = !open;
        }
        if (tr) tr.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    $(function() {
        var savedLang = localStorage.getItem('buyer_lang') || 'zh';
        var curSel = document.getElementById('currency-select');
        if (curSel && curSel.value) currentCurrency = curSel.value;
        setLang(savedLang);
        loadBuyerDashboard();

        var cartCount = 0;
        try {
            if (typeof AuthStorage !== 'undefined' && AuthStorage && AuthStorage.getCount) {
                cartCount = AuthStorage.getCount();
            }
        } catch (e) {}
        if ($('#cart-count').length) $('#cart-count').text(cartCount || 0);

        $('#currency-select').on('change', function() {
            currentCurrency = this.value;
            updatePrices();
        });

        var pg = document.getElementById('product-grid');
        var modal = document.getElementById('modal-preview');
        var modalBody = document.getElementById('modal-preview-body');
        var previewTrigger = null;
        function closePreview() {
            modal.style.display = 'none';
            if (previewTrigger) previewTrigger.focus();
        }
        document.querySelectorAll('#product-grid, [data-product-grid]').forEach(function(pg) {
            pg.addEventListener('click', function(e) {
                if (e.target.closest('.btn-quick-preview')) {
                    e.stopPropagation();
                    e.preventDefault();
                    var cardp = e.target.closest('.product-card');
                    if (!cardp) return;
                    var lang = localStorage.getItem('buyer_lang') || 'zh';
                    var tt = getT(lang);
                    var t1 = cardp.querySelector('.product-name') && cardp.querySelector('.product-name').textContent;
                    var s1 = cardp.querySelector('.product-spec') && cardp.querySelector('.product-spec').textContent;
                    if (modalBody) {
                        modalBody.textContent = (t1 || '') + (s1 ? '\n' + s1 : '') + '\n\n' + (tt.preview_note || '');
                    }
                    if (modal) {
                        previewTrigger = e.target.closest('.btn-quick-preview');
                        modal.style.display = 'flex';
                        modal.querySelector('.modal-close').focus();
                    }
                    return;
                }
                // Only the explicit purchase button opens the cart flow.
                if (!e.target.closest('.btn-add-cart')) return;
                var c = e.target.closest('.product-card[data-sku-id], .product-card[data-skuid]');
                if (c) {
                    e.preventDefault();
                    addToCartFromCard(c);
                }
            });
        });
        if (modal) {
            modal.querySelectorAll('[data-close]').forEach(function(b) {
                b.addEventListener('click', function() {
                    closePreview();
                });
            });
            modal.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') { e.preventDefault(); closePreview(); }
                if (e.key === 'Tab') { e.preventDefault(); modal.querySelector('.modal-close').focus(); }
            });
        }

        var btnSearch = document.getElementById('btn-search') || document.querySelector('.btn-search');
        if (btnSearch) {
            btnSearch.addEventListener('click', function() {
                var q = (document.getElementById('search-input') && document.getElementById('search-input').value) || '';
                q = q.trim();
                if (q) location.href = 'search_list.html?keyword=' + encodeURIComponent(q);
            });
        }

        var searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter') {
                    var q = this.value.trim();
                    if (q) location.href = 'search_list.html?keyword=' + encodeURIComponent(q);
                }
            });
        }

        var langSwitch = document.getElementById('lang-switch');
        if (langSwitch) {
            langSwitch.querySelectorAll('.lang-btn').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    setLang(btn.getAttribute('data-lang') || 'en');
                });
            });
        }

        var userTrigger = document.getElementById('user-trigger');
        var userDropdown = document.getElementById('user-dropdown');
        if (userTrigger && userDropdown) {
            var userItems = Array.from(userDropdown.querySelectorAll('[role="menuitem"]'));
            userItems.forEach(function(item) {
                if (new URL(item.href, location.href).pathname === location.pathname && item.id !== 'buyer-btn-logout') item.setAttribute('aria-current', 'page');
                else item.removeAttribute('aria-current');
            });
            openUserMenu(false);
            userTrigger.addEventListener('click', function(e) {
                e.stopPropagation();
                openUserMenu(userTrigger.getAttribute('aria-expanded') !== 'true');
            });
            userTrigger.addEventListener('keydown', function(e) {
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    e.preventDefault(); openUserMenu(true);
                    userItems[e.key === 'ArrowDown' ? 0 : userItems.length - 1].focus();
                }
            });
            document.addEventListener('click', function(e) { if (!e.target.closest('#user-menu')) openUserMenu(false); });
            document.addEventListener('focusin', function(e) { if (!e.target.closest('#user-menu')) openUserMenu(false); });
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape' && userTrigger.getAttribute('aria-expanded') === 'true') {
                    e.preventDefault(); openUserMenu(false); userTrigger.focus();
                }
            });
            userDropdown.addEventListener('keydown', function(e) {
                var index = userItems.indexOf(document.activeElement), next;
                if (e.key === 'ArrowDown') next = (index + 1) % userItems.length;
                else if (e.key === 'ArrowUp') next = (index - 1 + userItems.length) % userItems.length;
                else if (e.key === 'Home') next = 0;
                else if (e.key === 'End') next = userItems.length - 1;
                else return;
                e.preventDefault(); userItems[next].focus();
            });
            userDropdown.addEventListener('click', function(e) {
                e.stopPropagation();
            });
        }

        var logout = document.getElementById('buyer-btn-logout');
        if (logout) {
            logout.addEventListener('click', function(e) {
                e.preventDefault();
                try {
                    if (typeof AuthStorage !== 'undefined' && AuthStorage && AuthStorage.clear) {
                        AuthStorage.clear();
                    }
                } catch (err) {}
                location.href = 'login.html';
            });
        }
    });
})();
