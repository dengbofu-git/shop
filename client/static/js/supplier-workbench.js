/**
 * 供应商工作台（茶企端）- 品控溯源管理 · tea_saas
 * 三语切换、编辑品控弹窗
 */
(function() {
    'use strict';

    var i18n = {
        zh: {
            supplier_title: '茶企工作台',
            nav_dashboard: '工作台首页',
            nav_products: '商品管理',
            nav_orders: '订单管理',
            nav_store: '店铺页面管理',
            nav_assistant: '智能助手',
            nav_qc: '品控溯源',
            nav_settlement: '结算管理',
            nav_data: '数据中心',
            welcome: '欢迎',
            joined: '入驻',
            stat_sales: '近一年已付销售额',
            stat_pending_ship: '待发货订单数',
            stat_in_transit: '待收货订单数',
            stat_trace: '溯源码生成数量',
            todo_title: '待办事项',
            todo_unshipped: '待发货订单',
            todo_qc: '待补充品控资料',
            todo_settlement: '待结算账单',
            insight_title: '中东市场需求洞察',
            insight_hot: '近期热销茶品',
            insight_taste: '口感偏好',
            insight_price: '价格区间',
            qc_title: '品控溯源管理',
            qc_col_product: '商品名称',
            qc_col_batch: '批次',
            qc_col_status: '品控状态',
            status_ok: '已完善',
            status_pending: '待补充',
        },
        en: {
            supplier_title: 'Supplier Portal',
            nav_dashboard: 'Dashboard',
            nav_products: 'Products',
            nav_orders: 'Orders',
            nav_store: 'Store Page',
            nav_assistant: 'AI Assistant',
            nav_qc: 'QC & Trace',
            nav_settlement: 'Settlement',
            nav_data: 'Analytics',
            welcome: 'Welcome',
            joined: 'joined',
            stat_sales: 'Paid Sales (Past Year)',
            stat_pending_ship: 'Pending Shipments',
            stat_in_transit: 'Orders in Transit',
            stat_trace: 'Trace Codes Generated',
            todo_title: 'To-Do',
            todo_unshipped: 'Pending Shipments',
            todo_qc: 'QC Data to Complete',
            todo_settlement: 'Pending Bills',
            insight_title: 'Middle East Market Insights',
            insight_hot: 'Hot Products',
            insight_taste: 'Taste Preference',
            insight_price: 'Price Range',
            qc_title: 'QC & Traceability',
            qc_col_product: 'Product',
            qc_col_batch: 'Batch',
            qc_col_status: 'QC Status',
            status_ok: 'Complete',
            status_pending: 'Pending',
        },
        ar: {
            supplier_title: 'بوابة المورد',
            nav_dashboard: 'لوحة التحكم',
            nav_products: 'المنتجات',
            nav_orders: 'الطلبات',
            nav_store: 'إدارة صفحة المتجر',
            nav_assistant: 'المساعد الذكي',
            nav_qc: 'المراقبة والتتبع',
            nav_settlement: 'التسوية',
            nav_data: 'التحليلات',
            welcome: 'مرحباً',
            joined: 'انضم',
            stat_sales: 'المبيعات المدفوعة خلال آخر سنة',
            stat_pending_ship: 'الشحنات المعلقة',
            stat_in_transit: 'الطلبات قيد النقل',
            stat_trace: 'أكواد التتبع',
            todo_title: 'المهام',
            todo_unshipped: 'الشحنات المعلقة',
            todo_qc: 'إكمال بيانات المراقبة',
            todo_settlement: 'الفواتير المعلقة',
            insight_title: 'رؤى سوق الشرق الأوسط',
            insight_hot: 'المنتجات الرائجة',
            insight_taste: 'تفضيلات الطعم',
            insight_price: 'نطاق السعر',
            qc_title: 'المراقبة والتتبع',
            qc_col_product: 'المنتج',
            qc_col_batch: 'الدفعة',
            qc_col_status: 'حالة المراقبة',
            status_ok: 'مكتمل',
            status_pending: 'معلق',
        }
    };

    function getLang() {
        return localStorage.getItem('supplier_lang') || 'zh';
    }

    function setLang(lang) {
        document.documentElement.lang = lang === 'ar' ? 'ar' : (lang === 'en' ? 'en' : 'zh');
        document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
        document.body.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');
        localStorage.setItem('supplier_lang', lang);
        applyI18n(lang);
    }

    function applyI18n(lang) {
        var t = i18n[lang] || i18n.zh;
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            var key = el.getAttribute('data-i18n');
            if (t[key]) el.textContent = t[key];
        });
        document.title = (lang === 'zh' ? '供应商工作台' : (lang === 'ar' ? 'بوابة المورد' : 'Supplier Portal')) + ' - tea_saas';
    }

    $(function() {
        var token = AuthStorage.getToken();
        var user = AuthStorage.getUser();
        var shop = AuthStorage.getShop();

        if (!token || !user) {
            alert('请先登录');
            location.href = 'login.html';
            return;
        }

        $('#supplier-shop-name').text(shop || user || '茶企');
        $('#shop-name-2').text(shop || user || '茶企');
        $('#supplier-user-name').text(user || '账号');
        if (shop) document.title = shop + ' - 供应商工作台';

        var savedLang = getLang();
        setLang(savedLang);
        document.querySelectorAll('.lang-btn').forEach(function(btn) {
            if (btn.getAttribute('data-lang') === savedLang) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        document.querySelectorAll('.lang-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var lang = this.getAttribute('data-lang');
                setLang(lang);
                document.querySelectorAll('.lang-btn').forEach(function(b) { b.classList.remove('active'); });
                this.classList.add('active');
            });
        });

        function bindLogout($el) {
            $el.attr('href', '#').on('click', function (e) {
                e.preventDefault();
                AuthStorage.clear();
                location.href = 'login.html';
            });
        }
        bindLogout($('#btn-logout'));

        // 用户菜单
        var $dropdown = $('#user-dropdown');
        $('#btn-user-menu').on('click', function (e) {
            e.stopPropagation();
            $dropdown.toggle();
        });
        $(document).on('click', function (e) {
            var t = e.target;
            if (!t) return;
            var inMenu = $(t).closest('.user-menu').length > 0;
            if (!inMenu) $dropdown.hide();
        });

        $('#menu-profile').on('click', function (e) {
            e.preventDefault();
            $dropdown.hide();
            if (typeof showPanel === 'function') showPanel('supplier_profile.html');
        });
        $('#menu-security').on('click', function (e) {
            e.preventDefault();
            $dropdown.hide();
            if (typeof showPanel === 'function') showPanel('supplier_password.html');
        });

        // 侧边栏折叠
        $('#btn-sidebar-toggle').on('click', function() {
            $('#sidebar').toggleClass('collapsed');
        });

        function renderDashboard(data) {
            if (!data || !data.summary) return;
            var s = data.summary;
            $('#stat-sales').text(s.total_sales_display || ('¥' + s.total_sales));
            $('#stat-sales-sub').text('近365天已付订单 ' + s.paid_order_count + ' 笔 · 不含运费');
            $('#stat-pending-ship').text(s.pending_ship);
            $('#stat-pending-sub').text('待付款 ' + (s.unpaid || 0) + ' 笔');
            $('#stat-in-transit').text(s.in_transit);
            $('#stat-in-transit-sub').text('已完成 ' + s.completed + ' 笔');
            $('#stat-orders-total').text(s.order_count);
            $('#todo-unshipped').text(s.pending_ship);
            $('#todo-settlement').text((data.todos && data.todos.settlement) || 0);
            $('#todo-total-count').text('（共 ' + ((data.todos && data.todos.total) || 0) + ' 项）');

            var top = data.top_products || [];
            var maxPct = top.length ? top[0].amount : 1;
            $('#insight-top-products').html(top.slice(0, 5).map(function(p) {
                var w = Math.round((p.amount / maxPct) * 100);
                return '<div class="bar-row"><span>' + p.name + '</span><span class="bar"><i style="width:' + w + '%"></i></span><em>' + p.qty + '件</em></div>';
            }).join('') || '<div class="bar-row"><span>暂无销量</span></div>');

            $('#sales-monthly-list').html((data.monthly || []).map(function(m) {
                return '<li>' + m.label + '：' + m.order_count + ' 单 / ¥' + Math.round(m.sales) + '</li>';
            }).join(''));
            $('#sales-top-list').html(top.map(function(p) {
                return '<li>' + p.name + ' — ' + p.qty + ' 件 / ¥' + Math.round(p.amount) + '</li>';
            }).join('') || '<li>暂无</li>');
            $('#sales-region-list').html((data.regions || []).map(function(r) {
                return '<li>' + r.name + '：¥' + r.sales_wan + ' 万</li>';
            }).join(''));
        }

        if (typeof baseUrl !== 'undefined') {
            $.ajax({
                url: baseUrl + '/v1/supplier/analytics?period=year',
                headers: { 'Authorization': token },
                success: function(r) {
                    if (r.code === 200) renderDashboard(r.data);
                },
                error: function() { /* 首页指标仍可在控制台查看接口错误 */ }
            });
        }

        var showPanel;

        // 面板切换：侧栏导航 + 待办链接
        showPanel = function(panel) {
            var dashboard = document.getElementById('panel-dashboard');
            var iframe = document.getElementById('panel-iframe');
            if (!dashboard || !iframe) return;
            if (panel === 'dashboard') {
                dashboard.style.display = 'block';
                iframe.style.display = 'none';
                iframe.src = 'about:blank';
            } else {
                dashboard.style.display = 'none';
                iframe.style.display = 'block';
                iframe.src = panel.indexOf('?') >= 0 ? (panel + '&embed=1') : (panel + '?embed=1');
            }
            var isAccountPanel = panel.indexOf('supplier_profile') === 0 || panel.indexOf('supplier_password') === 0;
            document.querySelectorAll('.sidebar-nav .nav-item').forEach(function(item) {
                var itemPanel = item.getAttribute('data-panel');
                var isActive = !isAccountPanel && (
                    (panel === 'dashboard' && itemPanel === 'dashboard') ||
                    (panel !== 'dashboard' && itemPanel !== 'dashboard' && panel.indexOf(itemPanel) === 0)
                );
                item.classList.toggle('active', !!isActive);
            });
        };

        document.querySelectorAll('.sidebar-nav .nav-item').forEach(function(item) {
            item.addEventListener('click', function(e) {
                e.preventDefault();
                if (this.getAttribute('aria-disabled') === 'true' || this.classList.contains('nav-item-disabled')) return;
                var panel = this.getAttribute('data-panel');
                if (panel) showPanel(panel);
            });
        });

        document.querySelectorAll('.nav-panel-link').forEach(function(el) {
            el.addEventListener('click', function(e) {
                e.preventDefault();
                if (this.getAttribute('aria-disabled') === 'true' || this.classList.contains('nav-item-disabled')) return;
                var panel = this.getAttribute('data-panel');
                if (panel) showPanel(panel);
            });
        });

        // Tabs
        document.querySelectorAll('.tab').forEach(function(tab) {
            tab.addEventListener('click', function() {
                var id = this.getAttribute('data-tab');
                if (!id) return;
                document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
                this.classList.add('active');
                document.querySelectorAll('.tab-panel').forEach(function(p) {
                    p.classList.toggle('active', p.id === id);
                });
            });
        });

        // 按钮和回车统一提交，沿用现有订单页入口。
        $('#global-search-form').on('submit', function(e) {
            e.preventDefault();
            showPanel('merchant_orders.html');
        });
    });
})();
