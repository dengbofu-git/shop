/**
 * 区块链溯源扫码页 - 移动端H5
 * 三语切换、时间轴展开
 */
(function() {
    'use strict';

    var i18n = {
        zh: {
            product_name: '英德红茶·特级浓香型',
            brand_sub: '中国地理标志茶·中东官方溯源',
            batch: '批次号',
            harvest: '采摘时间',
            factory: '加工工厂',
            trace_title: '全链路溯源',
            node1: '茶园种植',
            node1_desc: '英德茶园实景、土壤检测报告、种植户信息。百千万工程帮扶茶农。',
            node2: '鲜叶采摘',
            node2_desc: '一芽二叶标准采摘，当日送达加工厂。',
            node3: '加工发酵',
            node3_desc: '非遗制茶工艺，二次发酵+低温慢烘，贴合中东浓香型偏好。',
            node4: '品控检测',
            node4_desc: '农残检测报告、清真认证文件，可查看高清扫描件。',
            node5: '报关出口',
            node5_desc: '9710报关单，通关时间2.5小时，供应链效率领先。',
            node6: '海运物流',
            node6_desc: '船名航次、物流轨迹地图，全流程透明可查。',
            node7: '海外仓入库',
            node7_desc: '迪拜仓入库，质检合格。',
            node8: '终端销售',
            node8_desc: '中东电商平台/线下门店销售。',
            culture_title: '中国工夫茶文化',
            brewing_title: '冲泡指南',
            brewing_desc: '水温95°C，茶水比1:50，冲泡3-5分钟。适配中东浓香偏好。',
            recommend_title: '开斋节限定礼盒',
            recommend_name: '英德红茶·开斋节礼盒 500g×2',
            buy_now: '立即购买'
        },
        en: {
            product_name: 'Yingde Black Tea · Premium Strong Aroma',
            brand_sub: 'China GI Tea · Middle East Official Traceability',
            batch: 'Batch',
            harvest: 'Harvest',
            factory: 'Factory',
            trace_title: 'Full-Chain Traceability',
            node1: 'Tea Garden',
            node1_desc: 'Yingde tea garden, soil test report, grower info. Rural revitalization program.',
            node2: 'Fresh Leaf Picking',
            node2_desc: 'One bud two leaves standard, same-day delivery to factory.',
            node3: 'Processing & Fermentation',
            node3_desc: 'Intangible heritage craft, double fermentation + low-temp slow roast.',
            node4: 'Quality Control',
            node4_desc: 'Pesticide residue report, Halal certification, viewable in HD.',
            node5: 'Customs Export',
            node5_desc: '9710 declaration, 2.5h clearance, leading supply chain efficiency.',
            node6: 'Sea Freight',
            node6_desc: 'Vessel name, voyage, logistics map, full transparency.',
            node7: 'Overseas Warehouse',
            node7_desc: 'Dubai warehouse inbound, QC passed.',
            node8: 'Retail',
            node8_desc: 'Middle East e-commerce / offline stores.',
            culture_title: 'Chinese Gongfu Tea Culture',
            brewing_title: 'Brewing Guide',
            brewing_desc: '95°C water, 1:50 ratio, 3-5 min. Suits Middle East strong flavor preference.',
            recommend_title: 'Eid Limited Gift Box',
            recommend_name: 'Yingde Black Tea Eid Gift Box 500g×2',
            buy_now: 'Buy Now'
        },
        ar: {
            product_name: 'شاي يينغدي الأسود · عطري ممتاز',
            brand_sub: 'شاي الصين الجغرافي · التتبع الرسمي للشرق الأوسط',
            batch: 'الدفعة',
            harvest: 'الحصاد',
            factory: 'المصنع',
            trace_title: 'التتبع الكامل',
            node1: 'مزرعة الشاي',
            node1_desc: 'حديقة شاي يينغدي، تقرير التربة، معلومات المزارع.',
            node2: 'قطف الأوراق',
            node2_desc: 'معيار برعم وورقتين، توصيل نفس اليوم.',
            node3: 'المعالجة والتخمير',
            node3_desc: 'حرفة التراث، تخمير مزدوج + تحميص بطيء.',
            node4: 'مراقبة الجودة',
            node4_desc: 'تقرير المبيدات، شهادة الحلال.',
            node5: 'التصدير الجمركي',
            node5_desc: 'إعلان 9710، تصفية 2.5 ساعة.',
            node6: 'الشحن البحري',
            node6_desc: 'اسم السفينة، خريطة الشحن.',
            node7: 'المستودع الخارجي',
            node7_desc: 'مستودع دبي، فحص الجودة.',
            node8: 'البيع بالتجزئة',
            node8_desc: 'منصات التجارة الإلكترونية / المتاجر.',
            culture_title: 'ثقافة الشاي الصينية',
            brewing_title: 'دليل التحضير',
            brewing_desc: 'ماء 95°م، نسبة 1:50، 3-5 دقائق.',
            recommend_title: 'علبة هدايا العيد',
            recommend_name: 'شاي يينغدي علبة العيد 500g×2',
            buy_now: 'اشتري الآن'
        }
    };

    function setLang(lang) {
        document.documentElement.lang = lang === 'ar' ? 'ar' : (lang === 'en' ? 'en' : 'zh');
        document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
        document.body.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
        localStorage.setItem('trace_lang', lang);
        applyI18n(lang);
    }

    function applyI18n(lang) {
        var t = i18n[lang] || i18n.zh;
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            var key = el.getAttribute('data-i18n');
            if (t[key]) el.textContent = t[key];
        });
        document.querySelectorAll('.tag-gi').forEach(function(el) {
            el.textContent = lang === 'zh' ? '📍 国家地理标志产品' : (lang === 'en' ? '📍 GI Product' : '📍 منتج جغرافي');
        });
        document.querySelectorAll('.tag-halal').forEach(function(el) {
            el.textContent = lang === 'zh' ? '☪️ JAKIM清真认证' : (lang === 'en' ? '☪️ JAKIM Halal' : '☪️ حلال JAKIM');
        });
        document.querySelectorAll('.tag-eu').forEach(function(el) {
            el.textContent = lang === 'zh' ? '✓ 欧盟农残检测合格' : (lang === 'en' ? '✓ EU Pesticide Pass' : '✓ معتمد EU');
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        var savedLang = localStorage.getItem('trace_lang') || 'zh';
        setLang(savedLang);

        document.querySelectorAll('.lang-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var lang = btn.dataset.lang;
                setLang(lang);
                document.querySelectorAll('.lang-btn').forEach(function(b) { b.classList.remove('active'); });
                btn.classList.add('active');
            });
        });

        var activeBtn = document.querySelector('.lang-btn[data-lang="' + savedLang + '"]');
        if (activeBtn) {
            document.querySelectorAll('.lang-btn').forEach(function(b) { b.classList.remove('active'); });
            activeBtn.classList.add('active');
        }

        document.querySelectorAll('.trace-node').forEach(function(node) {
            node.querySelector('.node-header').addEventListener('click', function() {
                node.classList.toggle('expanded');
            });
        });
    });
})();
