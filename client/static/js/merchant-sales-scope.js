/* Shared disclosure for the CNY-only merchant statistics, never inferred from amounts. */
(function (global, factory) {
    'use strict';
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    else global.MerchantSalesScope = api;
})(typeof window === 'undefined' ? {} : window, function () {
    'use strict';
    var words = {
        zh: {missing:'人民币统计范围信息暂不可用；当前数值仅代表已纳入统计的人民币（CNY）订单。',
            unknown:'{n}笔历史订单币种未记录，暂未计入人民币统计。',
            other:'{n}笔其他币种订单未计入人民币统计。',
            unavailable:'当前周期暂无可统计的人民币（CNY）订单，金额暂不可统计。',
            amount:'暂无可统计', empty:'暂无纳入统计的人民币（CNY）商品记录'},
        en: {missing:'CNY statistics scope information is temporarily unavailable. Values cover only included CNY orders.',
            unknown:'{n} historical orders have currency not recorded and are excluded from CNY statistics.',
            other:'{n} orders in other currencies are excluded from CNY statistics.',
            unavailable:'No CNY orders can be included for this period; financial amounts are unavailable.',
            amount:'Unavailable', empty:'No included CNY item records in this period'},
        ar: {missing:'معلومات نطاق إحصاءات CNY غير متاحة مؤقتاً. القيم تخص طلبات CNY المدرجة فقط.',
            unknown:'{n} من الطلبات التاريخية بلا عملة مسجلة، ولم تُدرج في إحصاءات اليوان CNY.',
            other:'{n} من الطلبات بعملات أخرى مستبعدة من إحصاءات اليوان CNY.',
            unavailable:'لا تتوفر طلبات باليوان CNY قابلة للإحصاء خلال الفترة؛ المبالغ غير متاحة.',
            amount:'غير متاح', empty:'لا توجد سجلات منتجات CNY مدرجة خلال هذه الفترة'}
    };
    function describe(scope, language, paidCount) {
        var t = words[language] || words.zh, locale = language === 'ar' ? 'ar' : language === 'en' ? 'en' : 'zh-CN';
        var keys = ['status_order_count','cny_order_count','unknown_currency_order_count','other_currency_order_count'];
        var valid = scope && scope.currency === 'CNY' && keys.every(function (key) { return Number.isSafeInteger(scope[key]) && scope[key] >= 0; });
        if (valid) {
            var excluded = scope.unknown_currency_order_count + scope.other_currency_order_count;
            var state = excluded ? (scope.cny_order_count ? 'partial' : 'unavailable') : 'complete';
            valid = Number.isSafeInteger(excluded) && scope.status_order_count === scope.cny_order_count + excluded
                && scope.financial_state === state && scope.cny_order_count === Number(paidCount);
        }
        if (!valid) return {state:'unknown',message:t.missing,unavailable:false,amount:t.amount,empty:t.empty};
        var messages = [];
        ['unknown','other'].forEach(function (key) {
            var value = scope[key === 'unknown' ? 'unknown_currency_order_count' : 'other_currency_order_count'];
            if (value) messages.push(t[key].replace('{n}',value.toLocaleString(locale)));
        });
        if (state === 'unavailable') messages.push(t.unavailable);
        return {state:state,message:messages.join(' '),unavailable:state === 'unavailable',amount:t.amount,empty:t.empty};
    }
    return {describe:describe};
});
