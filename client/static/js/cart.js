(function () {
    'use strict';

    var apiBase = typeof baseUrl === 'string' ? baseUrl.replace(/\/$/, '') : '';
    var username = AuthStorage.getUser();
    var items = [];
    var mediaBase = typeof imgUrl === 'string' ? imgUrl : apiBase + '/media/';
    var pendingDeleteId = null;
    // 与商品采购页保持相同的展示比例，不改变服务端价格或结算数据。
    var rates = { USD: 1, AED: 3.67, SAR: 3.75 };
    var currentCurrency = 'USD';

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
        });
    }

    function money(value) {
        var amount = Number(value);
        var symbol = currentCurrency === 'USD' ? '$' : currentCurrency + ' ';
        return symbol + ((isFinite(amount) ? amount : 0) * rates[currentCurrency]).toFixed(2);
    }

    function unitPrice(item) {
        var unit = Number(item.unit_price);
        if (item.unit_price != null && item.unit_price !== '' && isFinite(unit)) return unit;
        var price = Number(item.price);
        return isFinite(price) ? price : 0;
    }

    function imageUrl(item) {
        var path = String(item.default_image_url || '').trim();
        if (!path) return '/static/images/cart/product_normal.png';
        if (/^(https?:|data:)/i.test(path)) return path;
        if (path.indexOf('/media/') === 0) return apiBase + path;
        return mediaBase.replace(/\/$/, '') + '/' + path.replace(/^\//, '');
    }

    function selected(item) { return item.selected !== false && item.selected !== 'false'; }

    function updateSummary() {
        var chosen = items.filter(selected);
        var total = chosen.reduce(function (sum, item) {
            return sum + unitPrice(item) * (Number(item.count) || 1);
        }, 0);
        $('.total,.totalOne').text(chosen.length);
        $('.susum,.susumOne').text(money(total));
        $('#allcheck').prop('checked', items.length > 0 && chosen.length === items.length);
        $('#go-buy').prop('disabled', chosen.length === 0);
        $('.my_cart_count').text(items.length);
        if (AuthStorage.setCount) AuthStorage.setCount(items.length);
    }

    function render() {
        $('[data-cart-currency]').text(currentCurrency);
        var list = $('#cart_imfor').empty();
        $('.imfor_top').toggle(items.length > 0);
        if (!items.length) {
            list.html('<div class="empty-tip">采购车暂无商品，<a href="buyer_products.html">去选购茶品</a></div>');
            updateSummary();
            return;
        }
        items.forEach(function (item) {
            var id = escapeHtml(item.id);
            var count = Math.max(1, Number(item.count) || 1);
            var attrs = item.sku_sale_attr_name || [];
            var vals = item.sku_sale_attr_val || [];
            var attrHtml = attrs.map(function (name, index) {
                return '<p class="col"><span>' + escapeHtml(name) + '：</span><span>' + escapeHtml(vals[index] || '') + '</span></p>';
            }).join('');
            var row = ''
                + '<div class="imfor" data-id="' + id + '">'
                + '  <div class="check"><label class="Each"><input type="checkbox" value="' + id + '"' + (selected(item) ? ' checked' : '') + ' aria-label="选择商品"></label></div>'
                + '  <div class="pudc"><div class="pudc_information">'
                + '    <img src="' + escapeHtml(imageUrl(item)) + '" alt="商品图片">'
                + '    <div class="product-copy"><span class="des">' + escapeHtml(item.name) + '</span>' + attrHtml + '</div>'
                + '  </div></div>'
                + '  <div class="pices"><p class="pices_information">' + money(unitPrice(item)) + '</p></div>'
                + '  <div class="num"><button type="button" class="reduc" aria-label="减少数量">−</button><input class="num1207" type="text" value="' + count + '" readonly aria-label="数量"><button type="button" class="add" aria-label="增加数量">+</button></div>'
                + '  <div class="totle"><span class="totle_information">' + money(unitPrice(item) * count) + '</span></div>'
                + '  <div class="del"><a href="#" class="del_d">删除</a></div>'
                + '</div>';
            list.append(row);
        });
        updateSummary();
    }

    function saveGuest() {
        localStorage.setItem('cart', JSON.stringify(items));
        render();
    }

    function authExpired() {
        alert('登录已过期，请重新登录');
        AuthStorage.clear();
        location.href = 'login.html';
    }

    function request(method, payload) {
        return $.ajax({
            url: apiBase + '/v1/carts/' + encodeURIComponent(username),
            type: method,
            contentType: 'application/json',
            dataType: 'json',
            headers: { authorization: AuthStorage.getToken() },
            data: method === 'GET' ? undefined : JSON.stringify(payload)
        });
    }

    function handleFailure(response) {
        if (response && response.code === 403) { authExpired(); return; }
        alert((response && response.error) || '操作失败，请稍后重试');
    }

    function loadCart() {
        if (!username) {
            try {
                var stored = JSON.parse(localStorage.getItem('cart') || '[]');
                items = Array.isArray(stored) ? stored : [];
            } catch (_) { items = []; }
            render();
            return;
        }
        request('GET').done(function (response) {
            if (response.code !== 200) { handleFailure(response); return; }
            items = Array.isArray(response.data) ? response.data : [];
            mediaBase = response.base_url || mediaBase;
            render();
        }).fail(function (xhr) {
            if (xhr.status === 403 || (xhr.responseJSON && xhr.responseJSON.code === 403)) { authExpired(); return; }
            $('#cart_imfor').html('<div class="empty-tip">采购车加载失败，请刷新页面重试。</div>');
            $('#go-buy').prop('disabled', true);
        });
    }

    function mutate(method, payload, onSuccess) {
        request(method, payload).done(function (response) {
            if (response.code !== 200) { handleFailure(response); render(); return; }
            if (onSuccess) onSuccess();
            loadCart();
        }).fail(function (xhr) {
            if (xhr.status === 403 || (xhr.responseJSON && xhr.responseJSON.code === 403)) { authExpired(); return; }
            alert('网络异常，请稍后重试');
            render();
        });
    }

    $(function () {
        try {
            var savedCurrency = localStorage.getItem('buyer_cart_currency');
            if (Object.prototype.hasOwnProperty.call(rates, savedCurrency)) currentCurrency = savedCurrency;
        } catch (_) {}
        $('#currency-select').val(currentCurrency).on('change', function () {
            currentCurrency = Object.prototype.hasOwnProperty.call(rates, this.value) ? this.value : 'USD';
            $(this).val(currentCurrency);
            try { localStorage.setItem('buyer_cart_currency', currentCurrency); } catch (_) {}
            render();
        });
        loadCart();

        $('#cart_imfor').on('click', '.reduc,.add', function () {
            var row = $(this).closest('.imfor');
            var item = items.find(function (entry) { return String(entry.id) === String(row.data('id')); });
            if (!item) return;
            var current = Math.max(1, Number(item.count) || 1);
            var increase = $(this).hasClass('add');
            var limit = Number(item.available_stock);
            if (!increase && current <= 1) return;
            if (increase && current >= 9) { alert('单件商品最多购买 9 件'); return; }
            if (increase && item.available_stock != null && isFinite(limit) && current >= limit) { alert('购买数量超过库存'); return; }
            if (username) {
                mutate('PUT', { sku_id: item.id, state: increase ? 'add' : 'del' });
            } else {
                item.count = current + (increase ? 1 : -1);
                saveGuest();
            }
        });

        $('#cart_imfor').on('change', '.Each input', function () {
            var id = $(this).val();
            var item = items.find(function (entry) { return String(entry.id) === String(id); });
            if (!item) return;
            var next = $(this).prop('checked');
            if (username) {
                mutate('PUT', { sku_id: item.id, state: next ? 'select' : 'unselect' });
            } else {
                item.selected = next;
                saveGuest();
            }
        });

        $('#allcheck').on('change', function () {
            var next = $(this).prop('checked');
            if (username) {
                mutate('PUT', { state: next ? 'selectall' : 'unselectall' });
            } else {
                items.forEach(function (item) { item.selected = next; });
                saveGuest();
            }
        });

        $('#cart_imfor').on('click', '.del_d', function (event) {
            event.preventDefault();
            pendingDeleteId = String($(this).closest('.imfor').data('id'));
            $('.modal').show();
        });
        $('.modal .no').on('click', function () { pendingDeleteId = null; $('.modal').hide(); });
        $('.modal .yes').on('click', function () {
            if (pendingDeleteId == null) return;
            var id = pendingDeleteId;
            pendingDeleteId = null;
            $('.modal').hide();
            if (username) {
                mutate('DELETE', { sku_id: id });
            } else {
                items = items.filter(function (item) { return String(item.id) !== id; });
                saveGuest();
            }
        });

        $('#go-buy').on('click', function () {
            if (!username) { alert('请登录后结算'); location.href = 'login.html'; return; }
            if (!items.some(selected)) { alert('请选择要结算的商品'); return; }
            location.href = 'orderConfirm.html';
        });
    });
})();
