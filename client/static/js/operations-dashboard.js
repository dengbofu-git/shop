/**
 * 运营管理驾驶舱 - ECharts 图表
 * 答辩核心亮点，数据可视化
 */

(function() {
    'use strict';

    var theme = getComputedStyle(document.documentElement);
    var colorPrimary = theme.getPropertyValue('--color-primary').trim() || '#185c3b';
    var colorTea = '#50886a';
    var colorGold = '#91b19b';
    var colorMuted = '#6a7d73';

    var _charts = [];
    var _resizeTimer = null;
    var _analytics = null;
    var _currentPeriod = 'year';
    var _loadToken = 0;

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
        set('m-order-count', '已付 ' + s.paid_order_count + ' / 全部 ' + s.order_count + ' 笔');
        var periodNames = { month: '近30天', quarter: '近92天', year: '近365天' };
        set('sales-basis', (periodNames[_currentPeriod] || '近365天') + ' · ' + data.sales_basis);
        set('m-completion-rate', (s.completion_rate || 0) + '%');
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

    function initSalesTrendChart(data) {
        var dom = document.getElementById('chart-sales-trend');
        if (!dom) return;
        var chart = echarts.init(dom);
        var monthly = (data && data.monthly) || [];
        var months = monthly.map(function(m) { return m.label; });
        var sales = monthly.map(function(m) { return m.sales; });
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'axis', backgroundColor: '#ffffff', borderColor: '#e1e9e3', textStyle: { color: '#17352b' } },
            legend: {
                data: ['已付款销售额'],
                textStyle: { color: colorMuted, fontSize: 12 },
                bottom: 0
            },
            grid: { left: '3%', right: '4%', bottom: '15%', top: '10%', containLabel: true },
            xAxis: {
                type: 'category',
                data: months,
                axisLine: { lineStyle: { color: '#cfdbd1' } },
                axisLabel: { color: colorMuted }
            },
            yAxis: {
                type: 'value',
                name: '金额（元）',
                axisLine: { show: false },
                splitLine: { lineStyle: { color: '#edf0eb' } },
                axisLabel: { color: colorMuted }
            },
            series: [
                { name: '已付款销售额', type: 'line', data: sales, smooth: true, lineStyle: { color: colorPrimary }, itemStyle: { color: colorPrimary } }
            ]
        });
        registerChart(chart);
    }

    function initOrderStatusChart(data) {
        var dom = document.getElementById('chart-order-status');
        if (!dom) return;
        var chart = echarts.init(dom);
        var summary = (data && data.summary) || {};
        chart.setOption({
            backgroundColor: 'transparent',
            tooltip: { trigger: 'item', backgroundColor: '#ffffff', borderColor: '#e1e9e3', textStyle: { color: '#17352b' } },
            series: [{
                type: 'pie',
                radius: ['50%', '75%'],
                center: ['50%', '50%'],
                avoidLabelOverlap: false,
                itemStyle: {
                    borderColor: '#ffffff',
                    borderWidth: 2
                },
                label: { show: true, color: colorMuted, fontSize: 12 },
                data: [
                    { value: summary.unpaid || 0, name: '待付款', itemStyle: { color: colorMuted } },
                    { value: summary.pending_ship || 0, name: '待发货', itemStyle: { color: colorGold } },
                    { value: summary.in_transit || 0, name: '待收货', itemStyle: { color: colorTea } },
                    { value: summary.completed || 0, name: '已完成', itemStyle: { color: colorPrimary } }
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
            tooltip: { trigger: 'axis', formatter: '{b}: ¥{c}万', backgroundColor: '#ffffff', borderColor: '#e1e9e3', textStyle: { color: '#17352b' } },
            grid: { left: '15%', right: '5%', bottom: '15%', top: '15%' },
            xAxis: {
                type: 'category',
                data: xData,
                axisLine: { lineStyle: { color: '#cfdbd1' } },
                axisLabel: { color: colorMuted }
            },
            yAxis: {
                type: 'value',
                name: '销售额(万)',
                axisLine: { show: false },
                splitLine: { lineStyle: { color: '#edf0eb' } },
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
            tooltip: { trigger: 'axis', backgroundColor: '#ffffff', borderColor: '#e1e9e3', textStyle: { color: '#17352b' } },
            grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
            xAxis: {
                type: 'category',
                data: xCat,
                axisLine: { lineStyle: { color: '#cfdbd1' } },
                axisLabel: { color: colorMuted }
            },
            yAxis: {
                type: 'value',
                axisLine: { show: false },
                splitLine: { lineStyle: { color: '#edf0eb' } },
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
            tooltip: { trigger: 'item', backgroundColor: '#ffffff', borderColor: '#e1e9e3', textStyle: { color: '#17352b' } },
            series: [{
                type: 'funnel',
                left: '10%', width: '80%',
                minSize: '20%',
                maxSize: '100%',
                sort: 'descending',
                gap: 4,
                label: { show: true, position: 'inside', color: '#fff', fontSize: 12 },
                labelLine: { show: false },
                itemStyle: { borderColor: '#ffffff', borderWidth: 2 },
                data: funnel.map(function(item, idx) {
                    var colors = [colorPrimary, colorTea, colorGold];
                    return { value: item.value, name: item.name, itemStyle: { color: colors[idx % colors.length] } };
                })
            }]
        });
        registerChart(chart);
    }

    var chartIds = ['chart-sales-trend', 'chart-order-status', 'chart-map', 'chart-category', 'chart-funnel'];
    var _libraryPromise = null;
    var _libraryCancel = null;
    var _request = null;
    var _destroyed = false;
    var _chartLoading = false;

    function notify(message, canRetry) {
        document.getElementById('dashboard-load-status').textContent = message;
        var button = document.getElementById('retry-dashboard');
        button.hidden = !canRetry;
        button.disabled = false;
    }

    function disposeCharts() {
        _charts.forEach(function(chart) { try { chart.dispose(); } catch (_) {} });
        _charts = [];
    }

    function chartPlaceholder(id, message, busy) {
        var el = document.getElementById(id);
        if (!el) return;
        el.replaceChildren();
        var text = document.createElement('p');
        text.className = 'chart-placeholder';
        text.textContent = message;
        el.appendChild(text);
        el.setAttribute('aria-busy', String(busy));
    }

    function metricsBusy(busy) {
        document.querySelectorAll('.core-metrics, .aux-metrics').forEach(function(el) {
            el.setAttribute('aria-busy', String(busy));
        });
    }

    function resetMetrics() {
        document.querySelectorAll('.metric-value, .metric-tag[id], .aux-value, #m-turnover-display').forEach(function(el) {
            el.textContent = '—';
        });
    }

    // Prefer the pinned same-origin bundle. Statistics never wait for library loading.
    function loadEcharts() {
        if (window.echarts) return Promise.resolve();
        if (_libraryPromise) return _libraryPromise;
        var sources = ['/static/vendor/echarts/5.4.3/echarts.min.js',
            'https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js',
            'https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js'];
        function attempt(index) {
            if (_destroyed || index >= sources.length) return Promise.reject(new Error('图表库加载失败'));
            return new Promise(function(resolve, reject) {
                var script = document.createElement('script'), done = false;
                script.async = true;
                script.src = sources[index];
                function finish(error) {
                    if (done) return;
                    done = true;
                    window.clearTimeout(timer);
                    script.onload = script.onerror = null;
                    script.remove();
                    _libraryCancel = null;
                    if (error) reject(error); else resolve();
                }
                var timer = window.setTimeout(function() { finish(new Error('图表库加载超时')); }, 5000);
                _libraryCancel = function() { finish(new Error('页面已关闭')); };
                script.onload = function() { finish(window.echarts ? null : new Error('图表库不可用')); };
                script.onerror = function() { finish(new Error('图表库加载失败')); };
                document.head.appendChild(script);
            }).catch(function() { return attempt(index + 1); });
        }
        _libraryPromise = attempt(0).catch(function(error) {
            _libraryPromise = null;
            throw error;
        });
        return _libraryPromise;
    }

    function fetchAnalytics(period) {
        var token = typeof AuthStorage !== 'undefined' ? AuthStorage.getToken() : '';
        if (!token) return Promise.reject(new Error('请先登录后查看统计数据'));
        var url = baseUrl.replace(/\/$/, '') + '/v1/supplier/analytics?period=' + encodeURIComponent(period);
        return new Promise(function(resolve, reject) {
            var abort = new AbortController(), done = false;
            var request = {abort: function() { abort.abort(); finish(new Error('请求已取消')); }};
            _request = request;
            function finish(error, data) {
                if (done) return;
                done = true;
                window.clearTimeout(timer);
                if (_request === request) _request = null;
                if (error) reject(error); else resolve(data);
            }
            var timer = window.setTimeout(function() {
                abort.abort(); finish(new Error('统计请求超时，请重试'));
            }, 12000);
            fetch(url, {headers: {Authorization: token}, signal: abort.signal})
                .then(function(response) {
                    if (!response.ok) throw new Error(response.status === 401 ? '登录已过期，请重新登录' : '统计数据加载失败，请重试');
                    return response.json();
                }).then(function(json) {
                    if (!json || json.code !== 200 || !json.data || !json.data.summary) throw new Error('统计数据加载失败，请重试');
                    finish(null, json.data);
                }).catch(function(error) { finish(error); });
        });
    }

    async function renderCharts(data, token, libraryReady) {
        _chartLoading = true;
        notify('统计数据已更新，图表正在加载…', false);
        var available = await libraryReady;
        if (token !== _loadToken || _destroyed) return;
        if (!available) {
            _chartLoading = false;
            chartIds.forEach(function(id) { chartPlaceholder(id, '图表库加载失败，可点击重试', false); });
            notify('统计数据已显示，图表库加载失败，请重试。', true);
            return;
        }
        setupResizeOnce();
        var jobs = [initSalesTrendChart, initOrderStatusChart, initMapChart, initCategoryChart, initFunnelChart];
        var pending = jobs.length, failures = 0;
        jobs.forEach(function(job, index) {
            scheduleIdle(function() {
                if (token !== _loadToken || _destroyed) return;
                var el = document.getElementById(chartIds[index]);
                try {
                    if (el) { el.replaceChildren(); job(data); el.setAttribute('aria-busy', 'false'); }
                } catch (_) {
                    failures += 1;
                    // A partially initialized instance must not survive a failed setOption.
                    var instance = el && window.echarts.getInstanceByDom && window.echarts.getInstanceByDom(el);
                    if (instance) instance.dispose();
                    chartPlaceholder(chartIds[index], '此图表加载失败，可点击重试', false);
                }
                pending -= 1;
                if (!pending) {
                    _chartLoading = false;
                    notify(failures ? '统计数据已显示，部分图表加载失败，请重试。' : '统计数据与图表已更新', !!failures);
                }
            }, 200 + index * 100);
        });
    }

    async function init() {
        var token = ++_loadToken;
        if (_request) _request.abort();
        _analytics = null;
        _chartLoading = false;
        disposeCharts();
        resetMetrics();
        document.getElementById('sales-basis').textContent = '正在加载所选周期的统计数据…';
        metricsBusy(true);
        document.getElementById('refresh-data').disabled = true;
        chartIds.forEach(function(id) { chartPlaceholder(id, '图表加载中…', true); });
        notify('正在加载统计数据，图表将陆续显示…', false);
        // Consume failures immediately, even when statistics are slower than library fallback.
        var libraryReady = loadEcharts().then(function() { return true; }, function() { return false; });
        try {
            var data = await fetchAnalytics(_currentPeriod);
            if (token !== _loadToken || _destroyed) return;
            _analytics = data;
            applySummary(data);
            metricsBusy(false);
            renderCharts(data, token, libraryReady);
        } catch (error) {
            if (token !== _loadToken || _destroyed) return;
            metricsBusy(false);
            chartIds.forEach(function(id) { chartPlaceholder(id, '统计数据暂不可用', false); });
            notify(error.message || '统计数据加载失败，请重试', true);
        } finally {
            if (token === _loadToken && !_destroyed) document.getElementById('refresh-data').disabled = false;
        }
    }

    document.getElementById('refresh-data').addEventListener('click', function() { init(); });
    document.getElementById('retry-dashboard').addEventListener('click', function() {
        if (!_analytics) { init(); return; }
        if (_chartLoading) return;
        disposeCharts();
        chartIds.forEach(function(id) { chartPlaceholder(id, '图表重新加载中…', true); });
        renderCharts(_analytics, _loadToken, loadEcharts().then(function() { return true; }, function() { return false; }));
    });
    window.addEventListener('pagehide', function() {
        _destroyed = true;
        _loadToken += 1;
        if (_request) _request.abort();
        if (_libraryCancel) _libraryCancel();
        if (_resizeTimer) window.clearTimeout(_resizeTimer);
        disposeCharts();
    });
    window.addEventListener('pageshow', function(event) {
        if (event.persisted) { _destroyed = false; init(); }
    });

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
