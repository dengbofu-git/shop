(function (root, factory) {
    'use strict';
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else api.mount(root);
}(typeof window !== 'undefined' ? window : null, function () {
    'use strict';
    var standard = ['待付款', '待发货', '待收货', '已完成'];
    function statusOf(order) {
        var text = String(order.status_text || '').trim();
        if (text === '订单完成') return '已完成';
        if (order.status != null && Number(order.status) === 0 && order.order_type === 'standard') return '已关闭';
        return text || standard[Number(order.status) - 1] || '未知状态';
    }
    function escape(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
            return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
        });
    }
    function allowed(order, action) {
        var flag = order['can_' + action];
        if (typeof flag === 'boolean') return flag;
        return false; // Missing authenticated capability flags cannot enable a mutation.
    }
    function categories(orders) {
        var counts = new Map(standard.map(function (name) { return [name, 0]; }));
        orders.forEach(function (order) {
            var name = statusOf(order);
            counts.set(name, (counts.get(name) || 0) + 1);
        });
        return [{name: '全部', count: orders.length}].concat(Array.from(counts, function (entry) {
            return {name: entry[0], count: entry[1]};
        }));
    }
    function initialFilter(search) {
        var value = new URLSearchParams(search).get('filter') || '全部';
        return ({all: '全部', unpaid: '待付款', unshipped: '待发货', shipped: '待收货',
            completed: '已完成', '1': '待付款', '2': '待发货', '3': '待收货', '4': '已完成',
            '订单完成': '已完成'})[value] || value;
    }
    function rowsHtml(orders) {
        var headings = ['订单号', '状态', '金额（CNY）', '数量', '收货人', '电话', '地址', '下单时间', '操作'];
        return '<table class="merchant-orders-table"><caption class="order-sr-only">当前分类订单</caption><thead><tr>' +
            headings.map(function (title) { return '<th scope="col">' + title + '</th>'; }).join('') +
            '</tr></thead><tbody>' + orders.map(function (o) {
                var id = escape(o.order_id || '-'), state = statusOf(o), status = Number(o.status);
                var actions = '';
                if (allowed(o, 'ship')) actions += '<button type="button" class="btn-ship" data-action="ship" data-order-id="' + id + '">发货</button>';
                if (allowed(o, 'delete')) actions += '<button type="button" class="btn-delete-order" data-action="delete" data-order-id="' + id + '">取消订单</button>';
                if (o.requires_merchant_split) actions = '<span>需平台处理商家拆分</span>';
                var tone = standard.indexOf(state);
                var amount = Number(o.total_amount);
                return '<tr><td>' + id + '</td><td><span class="order-status-badge order-status-' + tone + '">' + escape(state) + '</span></td>' +
                    '<td>￥' + (Number.isFinite(amount) ? amount.toFixed(2) : '—') + '</td><td>' + escape(o.total_count || 0) + '</td>' +
                    '<td class="order-receiver">' + escape(o.receiver || '-') + '</td><td>' + escape(o.receiver_mobile || '-') + '</td>' +
                    '<td class="order-address">' + escape(o.address || '-') + '</td><td>' + escape(o.created_time || '-') + '</td>' +
                    '<td><div class="order-actions">' + (actions || '—') + '</div></td></tr>';
            }).join('') + '</tbody></table>';
    }
    function createController(deps) {
        var orders = [], active = deps.initial || '全部', loading = false, busy = false, error = '', loaded = false;
        function render() {
            var tabs = categories(orders);
            // Retain a selected subtype even after its last order is removed.
            if (!tabs.some(function (tab) { return tab.name === active; })) tabs.push({name: active, count: 0});
            var visible = orders.filter(function (order) { return active === '全部' || statusOf(order) === active; });
            deps.render({tabs: tabs, active: active, orders: visible, total: orders.length,
                loading: loading, busy: busy, error: error, loaded: loaded});
        }
        async function load() {
            if (loading || busy) return;
            loading = true; error = ''; render();
            try {
                var result = await deps.request('list');
                if (result.code !== 200 || !Array.isArray(result.data)) throw new Error(result.error || '订单加载失败');
                orders = result.data; loaded = true;
            } catch (e) { error = e.message || '订单加载失败，请重试'; }
            finally { loading = false; render(); }
        }
        async function act(action, id) {
            if (busy || loading || (action !== 'ship' && action !== 'delete')) return;
            var order = orders.find(function (o) { return String(o.order_id) === id; });
            if (!order) return;
            if (!allowed(order, action)) return;
            if (action === 'delete' && !deps.confirm('确定要取消未付款订单 ' + id + ' 吗？订单记录将保留。')) return;
            busy = true; error = ''; render();
            try {
                var result = await deps.request(action, id);
                if (result.code !== 200) throw new Error(result.error || '操作失败');
                deps.notify(action === 'ship' ? '发货成功' : '订单已取消，记录保留');
                // Re-read actual status_text: trial/presale labels have their own lifecycle.
                busy = false;
                await load();
            } catch (e) { error = e.message || '操作失败，请重试'; }
            finally { busy = false; render(); }
        }
        return {load: load, act: act, select: function (name) {
            active = name; render();
            if (deps.onSelect) deps.onSelect(name);
        }};
    }
    function mount(win) {
        var doc = win.document, list = doc.getElementById('order-list');
        if (!list) return;
        var token = win.AuthStorage.getToken();
        if (!token) { win.alert('请先登录'); win.location.href = 'login.html'; return; }
        var filters = doc.getElementById('order-status-filters'), summary = doc.getElementById('order-summary');
        var retry = doc.createElement('button');
        retry.type = 'button'; retry.className = 'order-retry'; retry.textContent = '重新加载'; retry.hidden = true;
        summary.after(retry);
        var controller = createController({
            initial: initialFilter(win.location.search),
            confirm: function (message) { return win.confirm(message); },
            notify: function (message) { win.alert(message); },
            request: function (action, id) {
                return new Promise(function (resolve, reject) {
                    var suffix = action === 'list' ? '' : action === 'ship' ? '/' + encodeURIComponent(id) + '/ship' : '/delete';
                    win.jQuery.ajax({url: win.baseUrl + '/v1/supplier/orders' + suffix,
                        type: action === 'list' ? 'GET' : 'POST', headers: {Authorization: token},
                        contentType: action === 'delete' ? 'application/json' : undefined,
                        data: action === 'delete' ? JSON.stringify({order_id: id}) : undefined,
                        success: resolve, error: function (xhr) {
                            reject(new Error(xhr.status === 401 ? '登录已过期，请重新登录' :
                                (xhr.responseJSON && xhr.responseJSON.error) || '请求失败，请重试'));
                        }});
                });
            },
            onSelect: function (name) {
                var url = new URL(win.location.href);
                if (name === '全部') url.searchParams.delete('filter');
                else url.searchParams.set('filter', name);
                win.history.replaceState(null, '', url);
            },
            render: function (state) {
                filters.innerHTML = state.tabs.map(function (tab) {
                    return '<button type="button" data-status="' + escape(tab.name) + '" aria-controls="order-list" aria-pressed="' +
                        (tab.name === state.active) + '">' + escape(tab.name) + ' <span>' + (state.loaded ? tab.count : '—') + '</span></button>';
                }).join('');
                list.setAttribute('aria-busy', String(state.loading || state.busy));
                summary.textContent = state.error || (state.loading ? '正在加载订单…' : state.busy ? '正在处理订单…' :
                    '共 ' + state.total + ' 笔订单，当前显示' + state.active + ' ' + state.orders.length + ' 笔');
                retry.hidden = !state.error;
                list.innerHTML = state.orders.length ? rowsHtml(state.orders) : '<div class="order-empty">' +
                    (state.loading ? '正在加载订单…' : state.error ? '未能更新订单，请重新加载。' :
                        state.active === '全部' ? '暂无订单' : '暂无“' + escape(state.active) + '”订单') + '</div>';
                list.querySelectorAll('[data-action]').forEach(function (button) { button.disabled = state.loading || state.busy || !!state.error; });
            }
        });
        filters.addEventListener('click', function (event) {
            var button = event.target.closest('[data-status]');
            if (button && filters.contains(button)) {
                controller.select(button.dataset.status);
                // Rendering replaces buttons; preserve keyboard focus on the chosen category.
                Array.from(filters.querySelectorAll('[data-status]')).find(function (item) {
                    return item.dataset.status === button.dataset.status;
                }).focus();
            }
        });
        list.addEventListener('click', function (event) {
            var button = event.target.closest('[data-action]');
            if (button && list.contains(button) && !button.disabled) controller.act(button.dataset.action, button.dataset.orderId);
        });
        retry.addEventListener('click', controller.load);
        doc.getElementById('btn-logout').addEventListener('click', function (event) {
            event.preventDefault(); win.AuthStorage.clear(); win.location.href = 'login.html';
        });
        controller.load();
        return controller;
    }
    return {statusOf: statusOf, categories: categories, rowsHtml: rowsHtml,
        initialFilter: initialFilter, createController: createController, mount: mount};
}));
