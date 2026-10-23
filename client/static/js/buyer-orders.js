(function () {
    'use strict';

    var apiBase = typeof baseUrl === 'string' ? baseUrl.replace(/\/$/, '') : '';
    var username = AuthStorage.getUser();
    var orders = [];
    var mediaBase = apiBase + '/media/';
    var currentStatus = 'all';
    var currentCurrency = 'CNY';
    var statusNames = { 0: '已关闭', 1: '待付款', 2: '待发货', 3: '待收货', 4: '已完成' };

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
        });
    }

    function money(value) {
        var amount = Number(value);
        return TeaMoney.format(isFinite(amount) && amount >= 0 ? amount : 0, currentCurrency);
    }

    function imageUrl(path) {
        path = String(path || '').trim();
        if (!path) return '/static/images/cart/product_normal.png';
        if (/^(https?:|data:)/i.test(path)) return path;
        if (path.indexOf('/media/') === 0) return apiBase + path;
        return mediaBase.replace(/\/$/, '') + '/' + path.replace(/^\//, '');
    }

    function actionButtons(order) {
        var status = order.status == null ? -1 : Number(order.status);
        var id = escapeHtml(order.order_id);
        var actions = [];
        if (status === 1 && !order.payment_exception) actions.push('<a class="bo-action bo-action-primary" href="gopay.html?order_id=' + encodeURIComponent(order.order_id) + '">去付款</a>');
        if (status === 1 && order.order_type === 'standard' && !order.payment_exception) actions.push('<button type="button" class="bo-action" data-action="cancel" data-order-id="' + id + '">' + (order.reservation_managed ? '取消并释放库存' : '取消订单') + '</button>');
        if (status === 3) actions.push('<button type="button" class="bo-action bo-action-primary" data-action="receive" data-order-id="' + id + '">确认收货</button>');
        if (status === 3) actions.push('<a class="bo-action" href="logistics_track.html?order=' + encodeURIComponent(order.order_id) + '">查看物流</a>');
        if ((order.order_type === 'standard' && (status === 0 || status === 1)) || order.is_completed) actions.push('<button type="button" class="bo-action bo-action-danger" data-action="delete" data-order-id="' + id + '">隐藏订单</button>');
        if (order.payment_exception) actions.push('<span class="bo-good-meta">支付需人工核验，请联系商家或平台；请勿重复付款。</span>');
        if (order.status === 1 && order.expires_at) actions.push('<span class="bo-good-meta">付款截止：' + escapeHtml(new Date(order.expires_at).toLocaleString()) + '</span>');
        return actions.join('');
    }

    function goodsMarkup(order) {
        var goods = Array.isArray(order.order_sku) ? order.order_sku : [];
        if (!goods.length) return '<div class="bo-good"><span class="bo-good-meta">暂无商品明细</span></div>';
        return goods.map(function (good) {
            var skuId = encodeURIComponent(good.sku || '');
            var productName = good.product_name || good.spu_name || '商品';
            var specification = good.sku_name || good.name || '';
            var price = Number(good.price) || 0;
            var count = Number(good.count) || 0;
            return '<div class="bo-good">'
                + '<img src="' + escapeHtml(imageUrl(good.default_image_url)) + '" alt="' + escapeHtml(productName) + '">'
                + '<div class="bo-good-info"><a class="bo-good-name" href="product_details.html?skuid=' + skuId + '">' + escapeHtml(productName) + '</a>'
                + (specification && specification !== productName ? '<p class="bo-good-meta">规格：' + escapeHtml(specification) + '</p>' : '')
                + '<p class="bo-good-meta">单价 ' + money(price) + ' × ' + count + '</p></div>'
                + '<div class="bo-actions">'
                + (good.can_review ? '<a class="bo-action" href="buyer_reviews.html?order_item_id=' + encodeURIComponent(good.id) + '" data-eng-text="review">评价商品</a>' : '')
                + (good.review_id ? '<a class="bo-action" href="buyer_reviews.html?order_item_id=' + encodeURIComponent(good.id) + '" data-eng-text="viewReview">查看评价</a>' : '')
                + '</div>'
                + '<div class="bo-good-price">' + money(price * count) + '<small>' + currentCurrency + '</small></div>'
                + '</div>';
        }).join('');
    }

    function addressMarkup(order) {
        var address = order.address || {};
        if (!address.address && !address.receiver) return '';
        return '<details class="bo-address"><summary>查看收货信息</summary><p>'
            + escapeHtml(address.receiver || '') + '　' + escapeHtml(address.mobile || '')
            + '<br>' + escapeHtml(address.address || '') + '</p></details>';
    }

    function render() {
        var query = ($('#bo-search').val() || '').trim().toLowerCase();
        var filtered = orders.filter(function (order) {
            if (currentStatus === 'review') {
                if (!(order.order_sku || []).some(function (good) { return good.can_review; })) return false;
            } else if (currentStatus === '4') {
                if (!order.is_completed) return false;
            } else if (currentStatus !== 'all' && String(order.status) !== currentStatus) return false;
            if (!query) return true;
            var names = (order.order_sku || []).map(function (good) {
                return [good.product_name, good.spu_name, good.sku_name, good.name].filter(Boolean).join(' ');
            }).join(' ');
            return (String(order.order_id) + ' ' + names).toLowerCase().indexOf(query) >= 0;
        });
        $('#bo-count').text('共 ' + filtered.length + ' 笔订单');
        if (!filtered.length) {
            $('#bo-list').html('<div class="bo-empty">' + (orders.length ? '没有符合条件的订单。' : '暂无订单，<a href="buyer_products.html">去选购茶品</a>。') + '</div>');
            return;
        }
        var markup = filtered.map(function (order) {
            var status = order.status == null ? -1 : Number(order.status);
            return '<article class="bo-order">'
                + '<div class="bo-order-head"><div><span class="bo-order-id">订单号 ' + escapeHtml(order.order_id) + '</span>'
                + '<span class="bo-order-time">' + escapeHtml(order.order_time || '') + '</span></div>'
                + '<span class="bo-status" data-status="' + status + '">' + escapeHtml(order.status_text || statusNames[status] || '处理中') + '</span></div>'
                + '<div class="bo-goods">' + goodsMarkup(order) + '</div>'
                + '<div class="bo-order-foot"><div class="bo-order-total">共 ' + escapeHtml(order.order_total_count || 0)
                + ' 件商品　运费 ' + money(order.order_freight) + '　订单金额 <strong>' + money(order.order_total_amount) + '</strong></div>'
                + '<div class="bo-actions">' + actionButtons(order) + '</div></div>'
                + addressMarkup(order)
                + '</article>';
        }).join('');
        $('#bo-list').html(markup);
        if (window.Engagement) window.Engagement.translate(document.getElementById('bo-list'));
    }

    function showError(message) {
        $('#bo-count').text('订单加载失败');
        $('#bo-list').html('<div class="bo-empty">' + escapeHtml(message) + ' <button type="button" class="bo-action" id="bo-retry">重试</button></div>');
    }

    function loadOrders() {
        if (!username) {
            showError('请先登录后查看订单。');
            $('#bo-list').append('<div class="bo-empty"><a href="login.html">前往登录</a></div>');
            return;
        }
        $('#bo-count').text('正在加载订单…');
        $('#bo-list').html('<div class="bo-empty">正在读取订单…</div>');
        $.ajax({
            url: apiBase + '/v1/orders/' + encodeURIComponent(username),
            type: 'GET',
            dataType: 'json',
            data: { type: '0' },
            headers: { Authorization: AuthStorage.getToken() }
        }).done(function (response) {
            if (!response || response.code !== 200) { showError((response && (response.error || response.errmsg)) || '无法读取订单。'); return; }
            mediaBase = response.base_url || mediaBase;
            orders = (response.data && response.data.orders_list) || [];
            orders.sort(function (a, b) { return String(b.order_time || '').localeCompare(String(a.order_time || '')); });
            render();
        }).fail(function (xhr) {
            showError(xhr.status === 401 || xhr.status === 403 ? '登录已过期，请重新登录。' : '网络异常，请稍后重试。');
        });
    }

    function changeOrder(action, id) {
        var deleting = action === 'delete', cancelling = action === 'cancel';
        if (!confirm(deleting ? '确定隐藏订单吗？未付款订单将同时取消并释放库存，记录仍保留。' : cancelling ? '取消订单并释放库存？取消记录仍计入预留限制。' : '确认已经收到这个订单的商品吗？')) return;
        $.ajax({
            url: apiBase + '/v1/orders/' + encodeURIComponent(username) + (deleting ? '/delete' : cancelling ? '/cancel' : '/confirm-receipt'),
            type: 'POST',
            contentType: 'application/json',
            dataType: 'json',
            data: JSON.stringify({ order_id: id }),
            headers: { Authorization: AuthStorage.getToken() }
        }).done(function (response) {
            if (response && response.code === 200) { loadOrders(); return; }
            alert((response && response.error) || '操作失败，请稍后重试');
        }).fail(function (xhr) {
            alert((xhr.responseJSON && xhr.responseJSON.error) || '网络异常，请稍后重试');
        });
    }

    $(function () {
        $('#currency-select').on('change', function () {
            currentCurrency = TeaMoney.currency(this.value);
            render();
        });
        $('#bo-refresh').on('click', loadOrders);
        $('#bo-list').on('click', '#bo-retry', loadOrders);
        $('.bo-tab').on('click', function () {
            $('.bo-tab').removeClass('active');
            $(this).addClass('active');
            currentStatus = String($(this).data('status'));
            render();
        });
        $('#bo-search').on('input', render);
        $('#bo-list').on('click', 'button[data-action]', function () {
            changeOrder($(this).data('action'), $(this).attr('data-order-id'));
        });
        loadOrders();
    });
})();
