/* Product presentation only. API price and SKU identity remain unchanged. */
(function (root, factory) {
    var api = factory(typeof module === 'object' && module.exports ? require('./currency.js') : root.TeaMoney);
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.ProductDetailSummary = api.mount(root.document);
})(typeof window === 'undefined' ? globalThis : window, function (money) {
    'use strict';
    function price(value, currency) {
        if (value == null || String(value).trim() === '' || !Number.isFinite(Number(value)) || Number(value) < 0) return '—';
        currency = money.currency(currency);
        return currency + ' ' + money.amount(value, currency).toFixed(2);
    }
    function attributes(data) {
        return (data.sku_sale_attr_names || []).map(function (name, index) {
            var id = data.sku_sale_attr_id[index];
            var ids = (data.sku_all_sale_attr_vals_id || {})[id] || [];
            var names = (data.sku_all_sale_attr_vals_name || {})[id] || [];
            var selected = (data.sku_sale_attr_val_id || [])[index];
            return {id:id, name:String(name), index:index,
                readonly:/^(净含量|净重|net\s*(weight|content)|الوزن الصافي)$/i.test(String(name).trim().replace(/[:：]$/, '')),
                values:ids.map(function (value, i) { return {id:value, name:String(names[i] == null ? '—' : names[i]), selected:String(value) === String(selected)}; })};
        });
    }
    function quantityControl(doc) {
        var input = doc.getElementById('buy-num'), minus = doc.getElementById('detail-quantity-minus');
        var plus = doc.getElementById('detail-quantity-plus'), stock = 0, last = 1;
        if (!input || !minus || !plus) return null;
        function refresh() {
            var text = input.value.trim(), count = /^\d+$/.test(text) ? Number(text) : NaN;
            var valid = Number.isSafeInteger(count) && count >= (stock ? 1 : 0) && count <= stock;
            input.disabled = stock === 0;
            input.setAttribute('aria-valuemin', stock ? '1' : '0');
            input.setAttribute('aria-valuemax', String(stock));
            input.setAttribute('aria-invalid', String(text !== '' && !valid));
            if (valid) input.setAttribute('aria-valuenow', String(count));
            else input.removeAttribute('aria-valuenow');
            minus.disabled = stock === 0 || (valid && count <= 1);
            plus.disabled = stock === 0 || (valid && count >= stock);
        }
        function commit() {
            var text = input.value.trim(), count = /^-?\d+$/.test(text) ? Number(text) : NaN;
            if (!Number.isSafeInteger(count)) count = last;
            last = stock ? Math.max(1, Math.min(stock, count)) : 0;
            input.value = String(last); refresh(); return last;
        }
        function step(amount) {
            var current = commit();
            if (!stock) return;
            input.value = String(Math.max(1, Math.min(stock, current + amount))); commit();
        }
        input.addEventListener('input', refresh);
        input.addEventListener('change', commit);
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', function (event) {
            if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
                event.preventDefault(); step(event.key === 'ArrowUp' ? 1 : -1);
            } else if (event.key === 'Enter') { event.preventDefault(); commit(); }
        });
        minus.addEventListener('click', function () { step(-1); });
        plus.addEventListener('click', function () { step(1); });
        function setStock(value) {
            stock = Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : 0;
            commit();
        }
        setStock(0);
        return {setStock:setStock, commit:commit};
    }
    function mount(doc) {
        var rawPrice = null, select = doc.getElementById('currency-select');
        var value = doc.getElementById('detail-price-value'), host = doc.getElementById('sku');
        var quantity = quantityControl(doc);
        function updatePrice() { value.textContent = price(rawPrice, select && select.value); }
        if (select) select.addEventListener('change', updatePrice);
        function node(tag, text, className) {
            var el = doc.createElement(tag); el.textContent = text; el.className = className || ''; return el;
        }
        function render(data) {
            rawPrice = data.price; updatePrice(); host.replaceChildren();
            if (quantity) quantity.setStock(data.stock);
            attributes(data).forEach(function (attr) {
                var row = node('div', '', 'detail-attribute');
                var label = node('span', attr.name + '：', 'spu_name'); label.setAttribute('data-id', attr.id);
                var values = node('div', '', 'detail-attribute-values'); row.append(label, values);
                if (attr.readonly) {
                    var selected = attr.values.find(function (entry) { return entry.selected; });
                    var fixed = node('span', selected ? selected.name : '—', 'detail-readonly-value');
                    if (selected) {
                        // Legacy SKU resolution still needs the current fixed attribute ID.
                        fixed.className += ' spu_value spu_check';
                        fixed.setAttribute('data-id', selected.id); fixed.setAttribute('data-value', selected.name);
                    }
                    values.append(fixed);
                } else attr.values.forEach(function (entry) {
                    var button = node('button', entry.name, 'spu_value l' + attr.index + (entry.selected ? ' spu_check' : ''));
                    button.type = 'button'; button.value = entry.name;
                    button.setAttribute('data-id', entry.id); button.setAttribute('aria-pressed', String(entry.selected));
                    values.append(button);
                });
                host.append(row);
            });
        }
        return {render:render, basePrice:function () { return Number(rawPrice); },
            quantity:function () { return quantity ? quantity.commit() : 0; }};
    }
    return {price:price, attributes:attributes, mount:mount, quantityControl:quantityControl};
});
