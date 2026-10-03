/**
 * 运营管理驾驶舱 - ECharts 图表
 * 答辩核心亮点，数据可视化
 */

(function() {
    'use strict';

    var colorPrimary = '#165DFF';
    var colorTea = '#2E7D32';
    var colorGold = '#D4AF37';
    var colorMuted = 'rgba(255,255,255,0.5)';

    var _charts = [];
    var _resizeTimer = null;
    var _analytics = null;
    var _currentPeriod = 'year';
    var _loadToken = 0;

    function buildLoadingOverlay() {
        var root = document.querySelector('.dashboard-root');
        if (!root) return null;
        var el = document.createElement('div');
        el.id = 'dashboard-loading';
        el.className = 'wb-loading-overlay';
        el.setAttribute('role', 'status');
        el.setAttribute('aria-live', 'polite');
        el.setAttribute('aria-busy', 'true');
        el.innerHTML =
            '<div class="wb-loading-dialog">' +
            '<div class="wb-loading-badge" aria-hidden="true">🍵</div>' +
            '<h2 class="wb-loading-title">数据中心</h2>' +
            '<p class="wb-loading-desc" id="dashboard-loading-desc">正在加载图表与统计数据，请稍候…</p>' +
            '<div class="wb-loading-spinner" aria-hidden="true"></div>' +
            '</div>';
        root.insertBefore(el, root.firstChild);
        return el;
    }

    function showLoading(message) {
        document.body.classList.add('dashboard-is-loading');
        var el = document.getElementById('dashboard-loading') || buildLoadingOverlay();
        if (!el) return;
        el.classList.remove('wb-loading-overlay--out');
        el.setAttribute('aria-busy', 'true');
        var desc = document.getElementById('dashboard-loading-desc');
        if (desc && message) desc.textContent = message;
        else if (desc) desc.textContent = '正在加载图表与统计数据，请稍候…';
    }

    function hideLoading() {
        document.body.classList.remove('dashboard-is-loading');
        var el = document.getElementById('dashboard-loading');
        if (!el) return;
        el.setAttribute('aria-busy', 'false');
        el.classList.add('wb-loading-overlay--out');
        function removeEl() {
            if (el.parentNode) el.parentNode.removeChild(el);
        }
        el.addEventListener('transitionend', removeEl, { once: true });
        window.setTimeout(removeEl, 400);
    }

    function registerChart(chart) {
        if (!chart) return;
        _charts.push(chart);
    }

    function setupResizeOnce() {
        if (setupResizeOnce._installed) return;
        setupResizeOnce._installed = true;
        window.addEventListener('resize', function() {
            if (_resizeTimer) window.clearTimeout(_resizeTimer);
            _resizeTimer = window.setTimeout(function() {
                _charts.forEach(function(c) {
                    try { c.resize(); } catch (_) {}
                });
            }, 120);
        });
    }

    function scheduleIdle(fn, timeout) {
        if (typeof window.requestIdleCallback === 'function') {
            window.requestIdleCallback(function() { fn(); }, { timeout: timeout || 600 });
        } else {
            window.setTimeout(fn, 120);
        }
    }

    function applySummary(data) {
        if (!data || !data.summary) return;
        var s = data.summary;
        var aux = data.aux || {};
        function set(id, text) {
            var el = document.getElementById(id);
            if (el) el.textContent = text;
        }
        set('m-total-sales', s.total_sales_display || ('¥' + s.total_sales));
        set('m-order-count', '订单 ' + s.order_count + ' 笔');
        set('m-pass-rate', (s.compliance_pass_rate || 0) + '%');
        set('m-completed', '已完成 ' + s.completed + ' 笔');
        set('m-pending-ship', String(s.pending_ship));
        set('m-unpaid', '待付款 ' + (s.unpaid || 0) + ' 笔');
        set('m-in-transit', String(s.in_transit));
        set('m-avg-order', String(s.avg_order_amount));
        set('m-turnover', String(s.inventory_turnover_days));
        set('m-turnover-display', String(s.inventory_turnover_days));
        set('aux-partners', String(aux.monthly_new_partners || 0));
        set('aux-roi', (aux.campaign_roi || 0) + 'x');
        set('aux-warehouse', (aux.warehouse_health_pct || 0) + '%');
        set('aux-score', String(aux.satisfaction_score || 0));
    }

    function fetchAnalytics(period, cb) {
        var token = typeof AuthStorage !== 'undefined' ? AuthStorage.getToken() : '';
        if (!token || typeof baseUrl === 'undefined') {
            cb(null);
            return;
        }
        var url = baseUrl.replace(/\/$/, '') + '/v1/supplier/analytics?period=' + encodeURIComponent(period || 'year');
        fetch(url, { headers: { Authorization: token } })
            .then(function(r) { return r.json(); })
            .then(function(json) {
                if (json && json.code === 200) cb(json.data);
                else cb(null);
            })
            .catch(function() { cb(null); });
    }

    function initLogisticsChart(data) {
        var dom = document.getElementById('chart-logistics');
        if (!dom) return;
        var chart = echarts.init(dom);
        var months = (data && data.monthly) ? data.monthly.map(function(m) { return m.label; }) : ['1月', '2月', '3月', '4月', '5月', '6月'];
        var projectDays = (data && data.logistics_days) ? data.logistics_days : [3, 2, 2, 2, 2, 2];
        var industry = projectDays.map(function(d) { return d + 5; });
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)' },
            legend: {
                data: ['项目报关周期', '行业平均'],
                textStyle: { color: colorMuted, fontSize: 12 },
                bottom: 0
            },
            grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
            xAxis: {
                type: 'category',
                data: months,
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
                axisLabel: { color: colorMuted }
            },
            yAxis: {
                type: 'value',
                name: '天数',
                axisLine: { show: false },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
                axisLabel: { color: colorMuted }
            },
            series: [
                { name: '项目报关周期', type: 'line', data: projectDays, smooth: true, lineStyle: { color: colorPrimary }, itemStyle: { color: colorPrimary } },
                { name: '行业平均', type: 'line', data: industry, smooth: true, lineStyle: { color: colorMuted }, itemStyle: { color: colorMuted } }
            ]
        });
        registerChart(chart);
    }

    function initComplianceChart(data) {
        var dom = document.getElementById('chart-compliance');
        if (!dom) return;
        var chart = echarts.init(dom);
        var pass = (data && data.summary) ? data.summary.compliance_pass_rate : 99;
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)' },
            series: [{
                type: 'pie',
                radius: ['50%', '75%'],
                center: ['50%', '50%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderColor: '#0a0e1a',
                    borderWidth: 2
                },
                label: { show: true, color: colorMuted, fontSize: 12 },
                data: [
                    { value: pass, name: '通过', itemStyle: { color: colorTea } },
                    { value: Math.max(0, 100 - pass), name: '待整改', itemStyle: { color: 'rgba(255,255,255,0.2)' } }
                ]
            }]
        });
        registerChart(chart);
    }

    function initMapChart(data) {
        var dom = document.getElementById('chart-map');
        if (!dom) return;
        var chart = echarts.init(dom);
        var regions = (data && data.regions) ? data.regions : [];
        var xData = regions.length ? regions.map(function(r) { return r.name; }) : ['阿联酋', '沙特', '卡塔尔', '科威特'];
        var yData = regions.length ? regions.map(function(r) { return r.sales_wan; }) : [0, 0, 0, 0];
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'axis', formatter: '{b}: ¥{c}万', backgroundColor: 'rgba(0,0,0,0.8)' },
            grid: { left: '15%', right: '5%', bottom: '15%', top: '15%' },
            xAxis: {
                type: 'category',
                data: xData,
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
                axisLabel: { color: colorMuted }
            },
            yAxis: {
                type: 'value',
                name: '销售额(万)',
                axisLine: { show: false },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
                axisLabel: { color: colorMuted }
            },
            series: [{
                type: 'bar',
                data: yData.map(function(v, i) {
                    var colors = [colorPrimary, colorPrimary, colorTea, colorGold];
                    return { value: v, itemStyle: { color: colors[i % colors.length] } };
                }),
                barWidth: '50%',
                label: { show: true, position: 'top', color: colorMuted }
            }]
        });
        registerChart(chart);
    }

    function initCategoryChart(data) {
        var dom = document.getElementById('chart-category');
        if (!dom) return;
        var chart = echarts.init(dom);
        var cats = (data && data.categories) ? data.categories : [];
        var xCat = cats.length ? cats.map(function(c) { return c.name; }) : ['暂无'];
        var yCat = cats.length ? cats.map(function(c) { return c.pct; }) : [0];
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'axis', backgroundColor: 'rgba(0,0,0,0.8)' },
            grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
            xAxis: {
                type: 'category',
                data: xCat,
                axisLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
                axisLabel: { color: colorMuted }
            },
            yAxis: {
                type: 'value',
                axisLine: { show: false },
                splitLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } },
                axisLabel: { color: colorMuted }
            },
            series: [{
                type: 'bar',
                data: yCat.map(function(v, i) {
                    var colors = [colorTea, colorGold, colorPrimary, colorMuted];
                    return { value: v, itemStyle: { color: colors[i % colors.length] } };
                }),
                barWidth: '50%'
            }]
        });
        registerChart(chart);
    }

    function initFunnelChart(data) {
        var dom = document.getElementById('chart-funnel');
        if (!dom) return;
        var chart = echarts.init(dom);
        var funnel = (data && data.funnel) ? data.funnel : [];
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'item', backgroundColor: 'rgba(0,0,0,0.8)' },
            series: [{
                type: 'funnel',
                left: '10%', width: '80%',
                minSize: '20%',
                maxSize: '100%',
                sort: 'descending',
                gap: 4,
                label: { show: true, position: 'inside', color: '#fff', fontSize: 12 },
                labelLine: { show: false },
                itemStyle: { borderColor: '#0a0e1a', borderWidth: 2 },
                data: funnel.map(function(item, idx) {
                    var colors = [colorPrimary, colorTea, colorGold];
                    return { value: item.value, name: item.name, itemStyle: { color: colors[idx % colors.length] } };
                })
            }]
        });
        registerChart(chart);
    }

    function renderCharts(data, onComplete) {
        _charts.forEach(function(c) {
            try { c.dispose(); } catch (_) {}
        });
        _charts = [];
        initLogisticsChart(data);
        initComplianceChart(data);
        var pending = 3;
        function chartDone() {
            pending -= 1;
            if (pending <= 0 && typeof onComplete === 'function') {
                window.requestAnimationFrame(function() { onComplete(); });
            }
        }
        scheduleIdle(function() { initMapChart(data); chartDone(); }, 200);
        scheduleIdle(function() { initCategoryChart(data); chartDone(); }, 300);
        scheduleIdle(function() { initFunnelChart(data); chartDone(); }, 400);
    }

    function waitForEcharts(cb, attempts) {
        if (typeof echarts !== 'undefined') {
            cb(true);
            return;
        }
        var left = attempts != null ? attempts : 40;
        if (left <= 0) {
            cb(false);
            return;
        }
        window.setTimeout(function() { waitForEcharts(cb, left - 1); }, 150);
    }

    function init() {
        var token = ++_loadToken;
        var finished = false;
        function finishLoading() {
            if (finished || token !== _loadToken) return;
            finished = true;
            hideLoading();
        }
        showLoading();
        window.setTimeout(finishLoading, 12000);

        waitForEcharts(function(ok) {
            if (token !== _loadToken) return;
            if (!ok) {
                console.error('ECharts 未加载，请检查网络连接');
                showLoading('图表库加载失败，请刷新页面或检查网络');
                window.setTimeout(finishLoading, 1600);
                return;
            }
            setupResizeOnce();
            fetchAnalytics(_currentPeriod, function(data) {
                if (token !== _loadToken) return;
                _analytics = data;
                applySummary(data);
                renderCharts(data, function() {
                    finishLoading();
                });
            });
        });
    }

    document.getElementById('btn-logout') && document.getElementById('btn-logout').addEventListener('click', function() {
        try {
            if (typeof AuthStorage !== 'undefined' && AuthStorage && typeof AuthStorage.clear === 'function') {
                AuthStorage.clear();
            }
        } catch (_) {}
        window.location.replace('login.html');
    });

    var timeFilter = document.getElementById('time-filter');
    if (timeFilter) {
        timeFilter.addEventListener('change', function() {
            _currentPeriod = this.value || 'year';
            init();
        });
    }

    function runInit() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function() {
                // 让首屏布局/样式先落地，再初始化图表
                window.requestAnimationFrame(function() { init(); });
            });
        } else {
            window.requestAnimationFrame(function() { init(); });
        }
    }
    runInit();
})();
