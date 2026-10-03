/**
 * 中东买家工作台 - 采购+订单追踪（系统：茗越山关跨境电商 9710 报关数字系统）
 * 三语、RTL、多币种、场景+茶类筛选
 */
(function() {
    'use strict';

    var currentCurrency = 'USD';

    var i18n = {
        zh: {
            brand_name: '茗越山关跨境电商 9710 报关数字系统',
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
            section_featured_sub: '先选采购场景，再选茶类；卡片为示例，完整列表见「商品采购」。',
            view_all: '查看全部',
            grid_empty: '该组合下暂无常驻示例商品，请点「查看全部」浏览完整商品库。',
            brand_short: '茗越山关跨境电商 9710 报关数字系统',
            banner1_title: '开斋节礼盒促销',
            banner1_desc: '英德红茶礼盒 · 清真认证',
            banner1_price: '$68 起',
            banner2_title: '2024 明前龙井新茶',
            banner2_desc: '地理标志 · 产地可溯',
            banner2_price: '$45 起',
            banner3_title: '大宗采购阶梯优惠',
            banner3_desc: '100件以上 15% off · 500件以上 25% off',
            banner3_price: '询盘报价',
            cat_bulk: '大宗批发款',
            cat_daily: '家庭日常款',
            cat_portable: '便携年轻款',
            cat_gift: '高端礼盒款',
            tea_all: '全部',
            tea_black: '红茶',
            tea_green: '绿茶',
            tea_oolong: '乌龙茶',
            tea_puer: '普洱茶',
            tea_white: '白茶',
            tea_yellow: '黄茶',
            tea_scented: '花茶',
            add_cart: '加入采购车',
            quick_preview: '快速预览',
            banner_empty: '暂无已上架、有库存的商品作为轮播',
            banner_loading: '正在加载轮播…',
            banner_loading_sub: '从数据库读取可售商品',
            grid_loading: '正在加载精选商品…',
            grid_loading_err: '无法加载推荐商品，请检查网络或稍后再试。',
            btn_view_sku: '查看商品',
            preview_title: '快速预览',
            preview_note: '以下为示例信息，以「商品采购」实价与规格为准。',
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
            adv_3d: '报关与国际运输协同',
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
            ft_intro: '公司介绍',
            ft_news: '新闻动态',
            ft_help: '帮助',
            ft_guide: '采购指南',
            ft_ship: '物流说明',
            ft_contact: '联系',
            ft_follow: '关注我们',
            ft_ig: 'Instagram',
            ft_copy: '© 2026 茗越山关跨境电商 9710 报关数字系统 · 中国地标茶出海中东',
            add_cart_msg: '已加入采购车：',
            inquiry_msg_prefix: '询价：'
        },
        en: {
            brand_name: 'Mingyue Shanguan Cross-border E-commerce 9710 Customs Digital System',
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
            section_featured_sub: 'Pick a scenario, then a tea type. Cards are samples — see Procurement for the full catalog.',
            view_all: 'View all',
            grid_empty: 'No sample cards for this filter. Open View all to browse the full list.',
            brand_short: 'Mingyue Shanguan 9710 Customs Digital System',
            banner1_title: 'Eid Gift Box',
            banner1_desc: 'Yingde black tea gift box · Halal certified',
            banner1_price: 'From $68',
            banner2_title: '2024 Pre-Qingming Longjing',
            banner2_desc: 'Geographic indication · traceable origin',
            banner2_price: 'From $45',
            banner3_title: 'Bulk tier discount',
            banner3_desc: '100+ units: 15% off · 500+ units: 25% off',
            banner3_price: 'Request quote',
            cat_bulk: 'Bulk wholesale',
            cat_daily: 'Daily family',
            cat_portable: 'Portable',
            cat_gift: 'Premium gift',
            tea_all: 'All',
            tea_black: 'Black',
            tea_green: 'Green',
            tea_oolong: 'Oolong',
            tea_puer: 'Pu\'er',
            tea_white: 'White',
            tea_yellow: 'Yellow',
            tea_scented: 'Scented',
            add_cart: 'Add to cart',
            quick_preview: 'Quick view',
            banner_empty: 'No in-stock products for the carousel',
            banner_loading: 'Loading carousel…',
            banner_loading_sub: 'From database',
            grid_loading: 'Loading featured products…',
            grid_loading_err: 'Could not load products. Check your connection.',
            btn_view_sku: 'View product',
            preview_title: 'Quick view',
            preview_note: 'Sample info only. See Procurement for live prices and specs.',
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
            adv_3d: 'Customs & logistics',
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
            ft_intro: 'Company',
            ft_news: 'News',
            ft_help: 'Help',
            ft_guide: 'Buying guide',
            ft_ship: 'Shipping',
            ft_contact: 'Contact',
            ft_follow: 'Follow',
            ft_ig: 'Instagram',
            ft_copy: '© 2026 Mingyue Shanguan Cross-border E-commerce 9710 Customs Digital System — China origin tea to MENA',
            add_cart_msg: 'Added: ',
            inquiry_msg_prefix: 'Inquiry: '
        },
        ar: {
            brand_name: 'نظام مينغ يوي شانغوان الرقمي للتجارة الإلكترونية عبر الحدود والتصريح الجمركي 9710',
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
            section_featured_sub: 'اختر المشهد ثم نوع الشاي. البطاقات للعينة — القائمة الكاملة في المشتريات.',
            view_all: 'عرض الكل',
            grid_empty: 'لا توجد بطاقة عينة لهذا الاختيار. افتح «عرض الكل».',
            brand_short: 'مينغ يوي شانغوان 9710',
            banner1_title: 'صندوق هدايا العيد',
            banner1_desc: 'شاي ينغدي · معتمد حلال',
            banner1_price: 'من 68$',
            banner2_title: 'لونججينغ 2024',
            banner2_desc: 'علامة جغرافية · أصل قابل للتتبع',
            banner2_price: 'من 45$',
            banner3_title: 'خصم بالجملة',
            banner3_desc: '100+ وحدة: 15% · 500+ وحدة: 25%',
            banner3_price: 'طلب عرض سعر',
            cat_bulk: 'جملة',
            cat_daily: 'عائلي',
            cat_portable: 'محمول',
            cat_gift: 'هدايا فاخرة',
            tea_all: 'الكل',
            tea_black: 'أسود',
            tea_green: 'أخضر',
            tea_oolong: 'أولونغ',
            tea_puer: 'بوير',
            tea_white: 'أبيض',
            tea_yellow: 'أصفر',
            tea_scented: 'معطر',
            add_cart: 'أضف للسلة',
            quick_preview: 'معاينة',
            banner_empty: 'لا بيانات عرض',
            banner_loading: 'جاري التحميل…',
            banner_loading_sub: 'من قاعدة البيانات',
            grid_loading: 'جاري تحميل المنتجات…',
            grid_loading_err: 'تعذر التحميل',
            btn_view_sku: 'عرض',
            preview_title: 'معاينة سريعة',
            preview_note: 'معلومات عينة. الأسعار في المشتريات.',
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
            adv_3d: 'الجمرك والشحن',
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
            ft_intro: 'عن الشركة',
            ft_news: 'الأخبار',
            ft_help: 'المساعدة',
            ft_guide: 'دليل الشراء',
            ft_ship: 'الشحن',
            ft_contact: 'اتصال',
            ft_follow: 'تابعنا',
            ft_ig: 'إنستغرام',
            ft_copy: '© 2026 نظام مينغ يوي شانغوان 9710 الرقمي',
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

    var _bannerTimer = null;

    function setPriceDataFromCny(el, cny) {
        var c = parseFloat(cny);
        if (isNaN(c)) c = 0;
        el.setAttribute('data-cny', c.toFixed(2));
        el.setAttribute('data-usd', (c * 0.14).toFixed(0));
        el.setAttribute('data-aed', (c * 0.51).toFixed(0));
        el.setAttribute('data-sar', (c * 0.52).toFixed(0));
        el.setAttribute('data-eur', (c * 0.13).toFixed(0));
    }

    function applyProductFilter() {
        var catEl = document.querySelector('.cat-tab.active');
        var teaEl = document.querySelector('.tea-tab.active');
        var cat = catEl && catEl.getAttribute('data-cat');
        var tea = (teaEl && teaEl.getAttribute('data-tea')) || 'all';
        var cards = document.querySelectorAll('#product-grid .product-card[data-sku-id]');
        var visible = 0;
        for (var i = 0; i < cards.length; i++) {
            var card = cards[i];
            var scenarios = (card.getAttribute('data-scenarios') || '').split(',');
            var teaType = card.getAttribute('data-tea') || '';
            var okCat = cat && scenarios.indexOf(cat) >= 0;
            var okTea = tea === 'all' || teaType === 'all' || !teaType || tea === teaType;
            var show = okCat && okTea;
            card.style.display = show ? '' : 'none';
            if (show) visible++;
        }
        var empty = document.getElementById('product-grid-empty');
        if (empty) empty.style.display = visible ? 'none' : 'block';
    }

    function addToCartFromCard(card) {
        var skuId = card.getAttribute('data-sku-id');
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
            window.localStorage.setItem('dashop_count', String(total));
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

    function normalizeProductRow(it) {
        if (it.title && !it.spu_name) {
            return {
                skuid: it.skuid,
                name: it.name || '',
                spu_name: it.title,
                caption: (it.intro || it.caption || '').slice(0, 200),
                price: it.price,
                image: it.image,
                image_url: it.image_url,
                link: it.link_url || it.link,
                catalog_name: it.catalog_name || ''
            };
        }
        if (!it.link && (it.link_url)) it.link = it.link_url;
        return it;
    }

    function loadBuyerDashboard() {
        var bSlider = document.getElementById('buyer-banner-slider');
        var bMsg = document.getElementById('banner-area-msg');
        var gGrid = document.getElementById('product-grid');
        var gSk = document.getElementById('product-grid-skeleton');
        var gErr = document.getElementById('product-grid-msg');
        if (!bSlider && !gSk && !gErr) return;
        if (gErr) gErr.style.display = 'none';
        if (_bannerTimer) {
            clearInterval(_bannerTimer);
            _bannerTimer = null;
        }
        $.getJSON(getApiBase() + '/v1/goods/carousel?stable=1&limit=6', function(res) {
            if (!bSlider) return;
            var skel = document.getElementById('buyer-banner-skeleton');
            if (skel) skel.remove();
            if (!res || res.code !== 200 || !res.data || !res.data.length) {
                if (bMsg) bMsg.style.display = 'block';
                return;
            }
            if (bMsg) bMsg.style.display = 'none';
            bSlider.innerHTML = '';
            res.data.forEach(function(raw, idx) {
                var it = raw;
                var priceStr = (it.price != null) ? '¥' + it.price : '';
                var item = document.createElement('div');
                item.className = 'banner-item banner-api' + (idx === 0 ? ' active' : '');
                var cover = it.image_url
                    ? "linear-gradient(135deg, rgba(10,20,10,0.82) 0%, rgba(26,93,26,0.55) 100%), url('" + it.image_url.replace(/'/g, "%27") + "')"
                    : 'linear-gradient(135deg, #123d12 0%, #1A5D1A 55%, #0d3d0d 100%)';
                item.style.background = cover;
                item.style.backgroundSize = 'cover';
                item.style.backgroundPosition = 'center';
                var pat = document.createElement('div');
                pat.className = 'banner-pattern';
                var cont = document.createElement('div');
                cont.className = 'banner-content';
                var h2 = document.createElement('h2');
                h2.textContent = it.title || it.name || '';
                var p = document.createElement('p');
                p.textContent = (it.intro || it.caption || '').slice(0, 200);
                cont.appendChild(h2);
                cont.appendChild(p);
                if (priceStr) {
                    var pr = document.createElement('span');
                    pr.className = 'banner-price';
                    pr.textContent = priceStr;
                    cont.appendChild(pr);
                }
                if (it.link_url || it.link) {
                    var a = document.createElement('a');
                    a.className = 'btn-banner-inquiry btn-view-sku';
                    a.href = it.link_url || it.link;
                    a.setAttribute('data-i18n', 'btn_view_sku');
                    var tt0 = getT(localStorage.getItem('buyer_lang') || 'zh');
                    a.textContent = tt0.btn_view_sku || '查看商品';
                    cont.appendChild(a);
                }
                item.appendChild(pat);
                item.appendChild(cont);
                bSlider.appendChild(item);
            });
            var items = bSlider.querySelectorAll('.banner-item');
            if (items.length > 1) {
                var bi = 0;
                _bannerTimer = setInterval(function() {
                    items[bi].classList.remove('active');
                    bi = (bi + 1) % items.length;
                    items[bi].classList.add('active');
                }, 4000);
            }
        }).fail(function() {
            if (bMsg) bMsg.style.display = 'block';
            var sk2 = document.getElementById('buyer-banner-skeleton');
            if (sk2) sk2.remove();
        });

        $.getJSON(getApiBase() + '/v1/goods/recommended-products', function(res) {
            var rows = (res && res.code === 200 && res.data) ? res.data.slice() : [];
            if (!rows.length) {
                return $.getJSON(getApiBase() + '/v1/goods/carousel?stable=1&limit=12', function(r2) {
                    if (r2 && r2.code === 200 && r2.data) {
                        rows = r2.data.map(normalizeProductRow);
                    }
                    buildProductGrid(rows, gGrid, gSk, gErr);
                }).fail(function() { buildProductGrid([], gGrid, gSk, gErr); });
            }
            buildProductGrid(rows.map(normalizeProductRow), gGrid, gSk, gErr);
        }).fail(function() {
            $.getJSON(getApiBase() + '/v1/goods/carousel?stable=1&limit=12', function(r2) {
                var rows2 = (r2 && r2.data) ? r2.data.map(normalizeProductRow) : [];
                buildProductGrid(rows2, gGrid, gSk, gErr);
            }).fail(function() {
                buildProductGrid([], gGrid, gSk, gErr);
            });
        });
    }

    function buildProductGrid(rows, gGrid, gSk, gErr) {
        if (!gGrid) return;
        if (gSk) gSk.remove();
        gGrid.innerHTML = '';
        if (!rows || !rows.length) {
            if (gErr) gErr.style.display = 'block';
            var ge0 = document.getElementById('product-grid-empty');
            if (ge0) ge0.style.display = 'none';
            return;
        }
        if (gErr) gErr.style.display = 'none';
        var lang = localStorage.getItem('buyer_lang') || 'zh';
        var ttx = getT(lang);
        rows.forEach(function(it) {
            var card = document.createElement('div');
            card.className = 'product-card product-card--click product-card--api';
            card.setAttribute('data-sku-id', String(it.skuid));
            card.setAttribute('data-scenarios', 'bulk,daily,portable,gift');
            card.setAttribute('data-tea', 'all');
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
            var wrap = document.createElement('div');
            wrap.className = 'product-img-wrap';
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
            var bPrev = document.createElement('button');
            bPrev.type = 'button';
            bPrev.className = 'btn-quick-preview';
            bPrev.setAttribute('data-i18n', 'quick_preview');
            bPrev.textContent = ttx.quick_preview;
            var aTrace = document.createElement('a');
            aTrace.className = 'btn-trace-link';
            aTrace.href = it.link || 'product_details.html?skuid=' + it.skuid;
            aTrace.setAttribute('data-i18n', 'trace_btn');
            aTrace.textContent = ttx.trace_btn;
            aTrace.target = '_self';
            var h3 = document.createElement('h3');
            h3.className = 'product-name';
            h3.textContent = productTitle(it);
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
            var hover = document.createElement('div');
            hover.className = 'product-hover-info';
            var hp = document.createElement('p');
            hp.textContent = (it.caption && it.caption) ? it.caption : (ttx.preview_note || '');
            hover.appendChild(hp);
            if (it.catalog_name) {
                var hp2 = document.createElement('p');
                hp2.textContent = it.catalog_name;
                hover.appendChild(hp2);
            }
            if (badges) card.appendChild(badges);
            card.appendChild(wrap);
            card.appendChild(bPrev);
            card.appendChild(aTrace);
            card.appendChild(h3);
            card.appendChild(spec);
            card.appendChild(price);
            card.appendChild(act);
            card.appendChild(hover);
            gGrid.appendChild(card);
        });
        var langNow = localStorage.getItem('buyer_lang') || 'zh';
        applyI18n(langNow);
        updatePrices();
        applyProductFilter();
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
        applyProductFilter();
    }

    function updatePrices() {
        document.querySelectorAll('.product-price').forEach(function(el) {
            if (el.getAttribute('data-cny') !== null) {
                var c = parseFloat(el.getAttribute('data-cny') || '0') || 0;
                if (currentCurrency === 'CNY' || !currentCurrency) {
                    el.textContent = '¥' + c.toFixed(2);
                } else if (currentCurrency === 'USD') {
                    el.textContent = '$' + (c * 0.14).toFixed(2);
                } else if (currentCurrency === 'AED') {
                    el.textContent = 'AED ' + (c * 0.51).toFixed(2);
                } else if (currentCurrency === 'SAR') {
                    el.textContent = 'SAR ' + (c * 0.52).toFixed(2);
                } else if (currentCurrency === 'EUR') {
                    el.textContent = '€' + (c * 0.13).toFixed(2);
                } else {
                    el.textContent = '¥' + c.toFixed(2);
                }
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
    }

    function openUserMenu(open) {
        var d = document.getElementById('user-dropdown');
        var tr = document.getElementById('user-trigger');
        if (d) d.style.display = open ? 'block' : 'none';
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

        document.querySelectorAll('.cat-tab').forEach(function(tab) {
            tab.addEventListener('click', function() {
                document.querySelectorAll('.cat-tab').forEach(function(x) { x.classList.remove('active'); });
                tab.classList.add('active');
                applyProductFilter();
            });
        });
        document.querySelectorAll('.tea-tab').forEach(function(tab) {
            tab.addEventListener('click', function() {
                document.querySelectorAll('.tea-tab').forEach(function(x) { x.classList.remove('active'); });
                tab.classList.add('active');
                applyProductFilter();
            });
        });

        var pg = document.getElementById('product-grid');
        var modal = document.getElementById('modal-preview');
        var modalBody = document.getElementById('modal-preview-body');
        if (pg) {
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
                    if (modal) modal.style.display = 'flex';
                    return;
                }
                if (e.target.closest('a.btn-trace-link')) return;
                var c = e.target.closest('.product-card[data-sku-id]');
                if (c) {
                    e.preventDefault();
                    addToCartFromCard(c);
                }
            });
        }
        if (modal) {
            modal.querySelectorAll('[data-close]').forEach(function(b) {
                b.addEventListener('click', function() {
                    modal.style.display = 'none';
                });
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
            userTrigger.addEventListener('click', function(e) {
                e.stopPropagation();
                var hidden = userDropdown.style.display === 'none' ||
                    window.getComputedStyle(userDropdown).display === 'none';
                openUserMenu(hidden);
            });
            document.addEventListener('click', function() {
                openUserMenu(false);
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
