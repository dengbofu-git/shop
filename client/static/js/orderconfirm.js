(function () {
    'use strict';
    var utils = CheckoutUtils;
    var apiBase = typeof baseUrl === 'string' ? baseUrl.replace(/\/$/, '') : '';
    var state = { items: [], addresses: [], addressId: null, type: '0', count: null, sku: null, media: '', currency: 'CNY', ready: false };
    var token = AuthStorage.getToken(), user = AuthStorage.getUser();
    function byId(id) { return document.getElementById(id); }
    function node(tag, text, cls) {
        var el = document.createElement(tag);
        if (text !== undefined) el.textContent = text;
        if (cls) el.className = cls;
        return el;
    }
    function address() { return state.addresses.find(function (item) { return String(item.id) === String(state.addressId); }); }
    function updateDelivery() {
        var selected = address();
        byId('checkout-delivery').textContent = selected ? selected.name + '  ' + selected.mobile + '\n' + selected.address : '请选择收货地址';
        byId('go_pay').disabled = !state.ready || !selected || !state.items.length;
    }
    function renderAddresses() {
        var root = byId('checkout-addresses');
        root.replaceChildren();
        byId('address-empty').hidden = state.addresses.length > 0;
        state.addresses.forEach(function (item) {
            var label = node('label', undefined, 'checkout-address');
            var radio = node('input');
            radio.type = 'radio'; radio.name = 'checkout-address'; radio.value = item.id;
            radio.checked = String(state.addressId) === String(item.id);
            radio.addEventListener('change', function () { state.addressId = item.id; updateDelivery(); });
            var copy = node('div', undefined, 'checkout-address-copy');
            copy.append(node('strong', item.name), node('small', item.mobile));
            if (item.title) copy.appendChild(node('span', item.title, 'checkout-tag'));
            copy.appendChild(node('p', item.address));
            label.append(radio, copy); root.appendChild(label);
        });
        updateDelivery();
    }
    function imageUrl(item) {
        var value = String(item.default_image_url || '').trim();
        if (!value) return '/static/images/cart/product_normal.png';
        if (/^https?:\/\//i.test(value)) return value;
        if (value.charAt(0) === '/') return apiBase + value;
        return state.media.replace(/\/$/, '') + '/' + value;
    }
    function renderItems() {
        var root = byId('checkout-items');
        root.replaceChildren();
        document.querySelectorAll('[data-checkout-currency]').forEach(function (el) { el.textContent = state.currency; });
        state.items.forEach(function (item) {
            var row = node('tr'), product = node('div', undefined, 'checkout-product');
            var image = node('img'); image.src = imageUrl(item); image.alt = item.product_name || item.name || '商品图片';
            image.addEventListener('error', function () { image.onerror = null; image.src = '/static/images/cart/product_normal.png'; }, { once: true });
            var copy = node('div');
            copy.appendChild(node('strong', item.product_name || item.name || '商品'));
            if (item.product_name && item.name && item.product_name !== item.name) copy.appendChild(node('p', item.name));
            var names = item.sku_sale_attr_name || [], values = item.sku_sale_attr_val || [];
            if (names.length) copy.appendChild(node('p', names.map(function (name, i) { return name + '：' + (values[i] || ''); }).join(' · ')));
            product.append(image, copy);
            var cell = node('td'); cell.appendChild(product);
            row.append(cell, node('td', utils.format(utils.line({ price: item.price, count: 1 }, state.currency), state.currency)),
                node('td', String(item.count)), node('td', utils.format(utils.line(item, state.currency), state.currency)));
            root.appendChild(row);
        });
        var total = utils.summary(state.items, state.currency);
        byId('count').textContent = total.count;
        byId('checkout-total').textContent = utils.format(total.cents, state.currency);
        byId('checkout-lines-count').textContent = state.items.length + ' 款商品';
        byId('products-empty').hidden = state.items.length > 0;
        byId('currency-note').textContent = (state.currency === 'CNY' ? '商品按人民币（CNY）基础价展示。' : '外币仅按人民币基础价参考换算，非实时汇率。') + '商品合计不含尚未确认的费用，订单金额以人民币记录，实际扣款以支付页为准。';
    }
    async function api(path, options) {
        var response = await fetch(apiBase + path, Object.assign({ headers: { Authorization: token, 'Content-Type': 'application/json' }, cache: 'no-store' }, options));
        var data = await response.json();
        if (response.status === 401 || response.status === 403 || data.code === 403) {
            AuthStorage.clear(); location.href = 'login.html'; throw new Error('登录已过期，请重新登录');
        }
        if (!response.ok || data.code !== 200) throw new Error(data.error || data.errmsg || '请求失败，请稍后重试');
        return data;
    }
    async function load(preferredAddress) {
        state.ready = false; updateDelivery();
        byId('checkout-status').textContent = '正在加载订单信息…';
        try {
            var query = utils.request(location.search);
            state.type = query.get('settlement_type');
            state.sku = query.get('sku_id'); state.count = query.get('buy_num');
            var result = await api('/v1/orders/' + encodeURIComponent(user) + '/advance?' + query.toString());
            var data = result.data;
            if (!data || !Array.isArray(data.sku_list) || !Array.isArray(data.addresses)) throw new Error('订单信息不完整，请返回采购车重新选择');
            utils.summary(data.sku_list, state.currency);
            state.items = data.sku_list; state.addresses = data.addresses;
            state.media = result.base_url || apiBase + '/media/';
            var preferred = preferredAddress || state.addressId;
            var chosen = state.addresses.find(function (item) { return String(item.id) === String(preferred); });
            state.addressId = chosen ? chosen.id : (state.addresses.length ? state.addresses[0].id : null);
            state.ready = true; renderItems(); renderAddresses();
            byId('checkout-status').textContent = '';
        } catch (error) {
            byId('checkout-status').textContent = error.message;
            state.ready = false; updateDelivery();
        }
    }
    document.addEventListener('DOMContentLoaded', function () {
        if (!token || !user) { location.href = 'login.html'; return; }
        var select = byId('currency-select');
        try { state.currency = utils.currency(localStorage.getItem('buyer_checkout_currency') || localStorage.getItem('buyer_cart_currency')); } catch (_) {}
        select.value = state.currency;
        select.addEventListener('change', function () {
            state.currency = utils.currency(select.value); select.value = state.currency;
            try { localStorage.setItem('buyer_checkout_currency', state.currency); } catch (_) {}
            renderItems();
        });
        byId('choose').addEventListener('click', function () { byId('address-error').textContent = ''; byId('address-dialog').showModal(); });
        byId('close-address').addEventListener('click', function () { byId('address-dialog').close(); });
        byId('go_pay').addEventListener('click', function () {
            if (!state.ready || !address() || !state.items.length) return;
            location.href = utils.payment(state, state.addressId);
        });
        byId('address-form').addEventListener('submit', async function (event) {
            event.preventDefault();
            var save = byId('save-address'); if (save.disabled) return;
            var addressText = ['receiverState', 'receiverCity', 'receiverDistrict', 'receiverAddress'].map(function (id) { return byId(id).value.trim(); }).join('');
            if (addressText.length > 100) { byId('address-error').textContent = '收货地址总长度不能超过100字'; return; }
            save.disabled = true; byId('address-error').textContent = '';
            try {
                var before = state.addresses.map(function (item) { return String(item.id); });
                await api('/v1/users/' + encodeURIComponent(user) + '/address', { method: 'POST', body: JSON.stringify({
                    receiver: byId('receiverName').value.trim(), receiver_phone: byId('receiverMobile').value.trim(),
                    address: addressText, postcode: byId('receiverZip').value.trim(), tag: byId('addressName').value.trim()
                }) });
                await load();
                var added = state.addresses.find(function (item) { return before.indexOf(String(item.id)) === -1; });
                if (added) { state.addressId = added.id; renderAddresses(); }
                byId('address-dialog').close();
            } catch (error) { byId('address-error').textContent = error.message; }
            finally { save.disabled = false; }
        });
        load();
    });
})();
