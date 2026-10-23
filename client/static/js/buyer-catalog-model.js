/* Shared catalog selection, display-price and URL state rules. No account data. */
(function (root) {
    'use strict';
    var money = typeof module === 'object' && module.exports ? require('./currency.js') : root.TeaMoney;
    function amount(value) {
        if (value === null || value === undefined || String(value).trim() === '') return '';
        var number = Number(value);
        return Number.isFinite(number) && number >= 0 ? number : '';
    }
    function normalize(data) {
        var seen = new Set();
        return (Array.isArray(data) ? data : []).filter(function (cat) {
            return Number.isInteger(Number(cat.catalog_id)) && Number(cat.catalog_id) > 0 && Array.isArray(cat.sku);
        }).map(function (cat) {
            return {id: String(cat.catalog_id), name: String(cat.catalog_name || ''), rows: cat.sku.filter(function (row) {
                var id = Number(row.skuid);
                if (!Number.isInteger(id) || id <= 0 || seen.has(id)) return false;
                seen.add(id); return true;
            }).map(function (row) {
                return Object.assign({}, row, {catalog_id: String(cat.catalog_id), catalog_name: String(cat.catalog_name || '')});
            }).sort(function (a, b) { return Number(b.skuid) - Number(a.skuid); })};
        });
    }
    function interleave(categories) {
        var rows = [], index = 0;
        while (categories.some(function (cat) { return index < cat.rows.length; })) {
            categories.forEach(function (cat) { if (cat.rows[index]) rows.push(cat.rows[index]); });
            index++;
        }
        return rows;
    }
    function read(search) {
        var params = new URLSearchParams(search);
        var currency = params.get('currency');
        return {catalog_id: params.get('catalog_id') || params.get('typeid') || 'all',
            q: (params.get('q') || '').trim().slice(0, 200), min_price: amount(params.get('min_price')),
            max_price: amount(params.get('max_price')),
            store_q: (params.get('store_q') || '').trim().slice(0, 200),
            sort: ['price_asc', 'price_desc'].includes(params.get('sort')) ? params.get('sort') : 'default',
            currency: money.currency(currency),
            page: Math.max(1, Math.floor(Number(params.get('page')) || 1))};
    }
    function search(state) {
        var params = new URLSearchParams();
        ['catalog_id', 'q', 'min_price', 'max_price', 'store_q', 'sort', 'currency', 'page'].forEach(function (key) {
            var value = state[key];
            if (value === '' || value == null || (key === 'catalog_id' && value === 'all') ||
                (key === 'sort' && value === 'default') || (key === 'page' && value === 1)) return;
            params.set(key, value);
        });
        return params.toString();
    }
    function price(row, currency) { return money.amount(row.price, currency); }
    function query(categories, state) {
        var needle = state.q.toLocaleLowerCase();
        var storeNeedle = (state.store_q || '').toLocaleLowerCase();
        var rows = interleave(categories.filter(function (cat) { return state.catalog_id === 'all' || cat.id === state.catalog_id; }))
            .filter(function (row) {
                var value = price(row, state.currency);
                var haystack = [row.spu_name, row.product_name, row.name, row.caption, row.merchant && row.merchant.name].join(' ').toLocaleLowerCase();
                return (!needle || haystack.includes(needle)) &&
                    (state.min_price === '' || value >= state.min_price) && (state.max_price === '' || value <= state.max_price) &&
                    (!storeNeedle || (row.merchant && String(row.merchant.name || '').toLocaleLowerCase().includes(storeNeedle)));
            });
        if (state.sort !== 'default') rows.sort(function (a, b) {
            return (state.sort === 'price_desc' ? -1 : 1) * (Number(a.price) - Number(b.price)) || Number(b.skuid) - Number(a.skuid);
        });
        var pages = Math.max(1, Math.ceil(rows.length / 10));
        var page = Math.min(Number.isFinite(state.page) ? state.page : 1, pages), start = (page - 1) * 10;
        return {rows: rows.slice(start, start + 10), total: rows.length, pages: pages, page: page,
            start: rows.length ? start + 1 : 0, end: Math.min(start + 10, rows.length)};
    }
    var api = {normalize: normalize, interleave: interleave, read: read, search: search, price: price, query: query};
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.BuyerCatalogModel = api;
})(typeof window === 'undefined' ? globalThis : window);
