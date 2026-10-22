/* All raw prices are CNY; rates are shared with the backend via currency.json. */
(function (root, factory) {
    var config;
    if (typeof module === 'object' && module.exports) {
        config = require('../../../tea_saas/currency.json');
        module.exports = factory(config);
    } else {
        var node = root.document.getElementById('tea-currency-config');
        config = (node ? JSON.parse(node.textContent) : null) || {base_currency:'CNY', rates:{CNY:'1.00'}, symbols:{CNY:'¥'}};
        root.TeaMoney = factory(config);
    }
})(typeof window === 'undefined' ? globalThis : window, function (config) {
    'use strict';
    var rates = {}, symbols = config.symbols;
    Object.keys(config.rates).forEach(function (code) { rates[code] = Number(config.rates[code]); });
    function currency(code) { return Object.prototype.hasOwnProperty.call(rates, code) ? code : config.base_currency; }
    function cents(value) {
        var match = /^(\d+)(?:\.(\d+))?$/.exec(String(value));
        if (!match) throw new Error('商品价格无效');
        var fraction = (match[2] || '') + '000';
        var result = Number(match[1]) * 100 + Number(fraction.slice(0, 2)) + (Number(fraction[2]) >= 5 ? 1 : 0);
        if (!Number.isSafeInteger(result)) throw new Error('商品金额超出范围');
        return result;
    }
    function convertCents(amount, code) {
        var multiplier = Math.round(rates[currency(code)] * 10000), scaled = amount * multiplier;
        if (!Number.isSafeInteger(amount) || !Number.isSafeInteger(scaled)) throw new Error('商品金额超出范围');
        return Math.round(scaled / 10000);
    }
    function amount(value, code) { return convertCents(cents(value), code) / 100; }
    function formatCents(value, code) { return symbols[currency(code)] + (value / 100).toFixed(2); }
    function format(value, code) { return formatCents(convertCents(cents(value), code), code); }
    return Object.freeze({base:config.base_currency, rates:Object.freeze(rates), currency:currency,
        cents:cents, convertCents:convertCents, amount:amount, format:format, formatCents:formatCents});
});
