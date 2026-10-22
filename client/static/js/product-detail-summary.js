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
    function mount(doc) {
        var rawPrice = null, select = doc.getElementById('currency-select');
        var value = doc.getElementById('detail-price-value'), host = doc.getElementById('sku');
        function updatePrice() { value.textContent = price(rawPrice, select && select.value); }
        if (select) select.addEventListener('change', updatePrice);
        function node(tag, text, className) {
            var el = doc.createElement(tag); el.textContent = text; el.className = className || ''; return el;
        }
        function render(data) {
            rawPrice = data.price; updatePrice(); host.replaceChildren();
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
        return {render:render, basePrice:function () { return Number(rawPrice); }};
    }
    return {price:price, attributes:attributes, mount:mount};
});
