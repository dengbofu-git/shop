/* Period-based business results. Operational tasks are rendered by the separate feed. */
(function (global, factory) {
    'use strict';
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (global.document) global.MerchantOverview = api.mount(global);
})(typeof window === 'undefined' ? {} : window, function () {
    'use strict';
    var words = {
        zh: {heading: '经营概览', period: '近365天 · 按下单日期统计', sales: '已付销售额', paid: '已付订单数', average: '平均订单金额', completion: '订单完成率',
            sales_note: '本店商品金额，不含运费', paid_note: '当前周期内已全额付款订单', average_note: '已付销售额 ÷ 已付订单数', completion_note: '已完成 {done} / 全部 {total} 笔',
            basis: '经营指标统一使用近365天统计；当前待处理事项见下方，不受该周期限制。', loading: '正在加载经营数据…', failed: '经营数据加载失败，请重试。', retry: '重新加载'},
        en: {heading: 'Business overview', period: 'Past 365 days · by order creation date', sales: 'Paid sales', paid: 'Paid orders', average: 'Average paid order', completion: 'Order completion rate',
            sales_note: 'Your product revenue, excluding freight', paid_note: 'Fully paid orders in this period', average_note: 'Paid sales ÷ paid orders', completion_note: '{done} completed / {total} total orders',
            basis: 'All business metrics cover the past 365 days. Current tasks below include all pending records.', loading: 'Loading business metrics…', failed: 'Could not load business metrics. Please retry.', retry: 'Retry'},
        ar: {heading: 'نظرة عامة على الأعمال', period: 'آخر 365 يوماً · حسب تاريخ إنشاء الطلب', sales: 'المبيعات المدفوعة', paid: 'الطلبات المدفوعة', average: 'متوسط الطلب المدفوع', completion: 'نسبة اكتمال الطلبات',
            sales_note: 'قيمة منتجات متجرك دون الشحن', paid_note: 'طلبات مدفوعة بالكامل خلال الفترة', average_note: 'المبيعات المدفوعة ÷ الطلبات المدفوعة', completion_note: '{done} مكتمل / {total} إجمالي الطلبات',
            basis: 'مؤشرات الأعمال لآخر 365 يوماً. تشمل المهام أدناه جميع السجلات المعلقة.', loading: 'جار تحميل مؤشرات الأعمال…', failed: 'تعذر تحميل مؤشرات الأعمال. أعد المحاولة.', retry: 'إعادة المحاولة'}
    };
    function values(summary, language) {
        var required = ['total_sales', 'paid_order_count', 'avg_order_amount', 'completion_rate', 'completed', 'order_count'];
        if (!summary || required.some(function (key) {
            return summary[key] == null || summary[key] === '' || !Number.isFinite(Number(summary[key]));
        })) throw new Error('invalid-overview-summary');
        var locale = language === 'ar' ? 'ar' : language === 'en' ? 'en' : 'zh-CN';
        var t = words[language] || words.zh;
        function number(value, digits) { return Number(value).toLocaleString(locale, {minimumFractionDigits: digits, maximumFractionDigits: digits}); }
        return {sales: '¥' + number(summary.total_sales, 2), paid: number(summary.paid_order_count, 0),
            average: '¥' + number(summary.avg_order_amount, 2), completion: number(summary.completion_rate, 1) + '%',
            completion_note: t.completion_note.replace('{done}', number(summary.completed, 0)).replace('{total}', number(summary.order_count, 0))};
    }
    function mount(win) {
        var doc = win.document, root = doc.getElementById('merchant-overview');
        if (!root) return null;
        var state = 'loading', summary = null;
        function render() {
            var language = doc.documentElement.lang.split('-')[0], t = words[language] || words.zh, data;
            if (state === 'ready') {
                try { data = values(summary, language); } catch (_) { state = 'error'; }
            }
            root.querySelectorAll('[data-overview-text]').forEach(function (item) { item.textContent = t[item.dataset.overviewText]; });
            ['sales', 'paid', 'average', 'completion'].forEach(function (key) { doc.getElementById('overview-' + key).textContent = data ? data[key] : '—'; });
            doc.getElementById('overview-completion-note').textContent = data ? data.completion_note : t.completion_note.replace('{done}', '—').replace('{total}', '—');
            var status = doc.getElementById('overview-status');
            status.textContent = state === 'ready' ? '' : t[state === 'loading' ? 'loading' : 'failed'];
            status.hidden = state === 'ready';
            doc.getElementById('overview-retry').hidden = state !== 'error';
            root.setAttribute('aria-busy', String(state === 'loading'));
        }
        doc.getElementById('overview-retry').addEventListener('click', function () { doc.dispatchEvent(new win.CustomEvent('supplier:refresh-overview')); });
        new win.MutationObserver(render).observe(doc.documentElement, {attributes: true, attributeFilter: ['lang']});
        render();
        return {render: function (next) { summary = next; state = 'ready'; render(); },
            loading: function () { summary = null; state = 'loading'; render(); },
            error: function () { summary = null; state = 'error'; render(); }};
    }
    return {values: values, mount: mount};
});
