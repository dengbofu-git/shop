(function (root, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.CheckoutUtils = api;
})(typeof window === 'undefined' ? this : window, function () {
    'use strict';
    var rates = { USD: 100, AED: 367, SAR: 375 };
    function currency(value) { return Object.prototype.hasOwnProperty.call(rates, value) ? value : 'USD'; }
    function cents(value) {
        var match = /^(\d+)(?:\.(\d+))?$/.exec(String(value));
        if (!match) throw new Error('商品价格无效');
        var fraction = (match[2] || '') + '000';
        var result = Number(match[1]) * 100 + Number(fraction.slice(0, 2)) + (Number(fraction[2]) >= 5 ? 1 : 0);
        if (!Number.isSafeInteger(result)) throw new Error('商品价格超出范围');
        return result;
    }
    function quantity(value) {
        var count = Number(value);
        if (!Number.isSafeInteger(count) || count < 1) throw new Error('商品数量无效');
        return count;
    }
    function line(item, code) {
        var amount = cents(item.price) * quantity(item.count);
        var converted = amount * rates[currency(code)];
        if (!Number.isSafeInteger(converted)) throw new Error('商品金额超出范围');
        return Math.round(converted / 100);
    }
    function format(amount, code) {
        return (currency(code) === 'USD' ? '$' : currency(code) + ' ') + (amount / 100).toFixed(2);
    }
    function summary(items, code) {
        return items.reduce(function (total, item) {
            total.count += quantity(item.count);
            total.cents += line(item, code);
            return total;
        }, { count: 0, cents: 0 });
    }
    function request(search) {
        var params = new URLSearchParams(search || '');
        var sku = params.get('sku_id');
        var count = params.get('buy_num');
        var result = new URLSearchParams();
        if (sku && count) {
            if (!/^\d+$/.test(sku) || Number(sku) < 1) throw new Error('商品编号无效');
            quantity(count);
            result.set('sku_id', sku);
            result.set('buy_num', count);
            result.set('settlement_type', '1');
        } else if (sku || count) throw new Error('立即购买参数不完整，请重新选择商品');
        else result.set('settlement_type', '0');
        return result;
    }
    function payment(state, addressId) {
        var params = new URLSearchParams({ address_id: addressId, settlement_type: state.type });
        if (String(state.type) === '1') {
            params.set('buy_count', state.count);
            params.set('sku_id', state.sku);
        }
        return 'payment.html?' + params.toString();
    }
    return { currency: currency, cents: cents, quantity: quantity, line: line, format: format,
        summary: summary, request: request, payment: payment };
});
