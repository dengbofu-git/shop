/* Merchant-only sales facts. Unavailable market data stays in template TODOs. */
(function (global, factory) {
    var api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    if (global.document) {
        if (global.document.readyState === 'loading') global.document.addEventListener('DOMContentLoaded', function () { api.mount(global); });
        else api.mount(global);
    }
})(typeof window === 'undefined' ? {} : window, function () {
    'use strict';
    var words = {
        zh: {heading:'销售洞察与数据分析', insight:'本店销售洞察', sales:'我的销售数据', industry:'行业趋势', refresh:'刷新',
            basis:'近365天 · 本店已全额付款商品 · 按下单日期统计 · 人民币，不含运费',
            top:'热销商品 TOP5（按件数）', price:'成交单价分布（按件数）', monthly:'近6个自然月已付订单', salesTop:'商品销售额 TOP5',
            priceNote:'按购买件数统计，非茶叶重量。区间含起始价、不含结束价，最后一档无上限。', priceCurrency:'人民币 CNY', priceUnit:'元 / 件', below:'低于 {n}', above:'{n} 及以上', monthlyNote:'当前月截至本次查询时间；各月只统计本店已全额付款订单。',
            industryMissing:'暂无已接入、可核验的行业数据。', unavailable:'口感偏好、地区销售、行业出口、竞品和政策数据尚未接入。',
            loading:'正在加载销售数据…', failed:'销售数据加载失败，请刷新重试。', login:'登录已过期，请重新登录。', forbidden:'需要商家账号。', empty:'暂无已付商品记录',
            quantity:'{n}件', month:'月份', orders:'已付订单数', amount:'销售额（CNY）', summary:'本期 {orders} 笔已付订单，共 {quantity} 件商品',
            updated:'更新于 {time}', excluded:'有 {n} 条非正数量或负单价明细未计入价格分布。'},
        en: {heading:'Sales insights and analysis', insight:'My store insights', sales:'My sales', industry:'Industry trends', refresh:'Refresh',
            basis:'Past 365 days · Fully paid store items · By order creation date · CNY, excluding freight',
            top:'Top 5 products by units', price:'Paid unit price distribution', monthly:'Paid orders over 6 calendar months', salesTop:'Top 5 products by revenue',
            priceNote:'Weighted by purchased units, not tea weight. Ranges include the lower bound and exclude the upper; the final range has no ceiling.', priceCurrency:'Chinese yuan · CNY', priceUnit:'CNY / unit', below:'Below {n}', above:'{n} and above', monthlyNote:'The current month ends at this query. Fully paid store orders only.',
            industryMissing:'No verified industry source is connected yet.', unavailable:'Taste preferences, regional sales, exports, competitors and policy data are not connected.',
            loading:'Loading sales data…', failed:'Could not load sales data. Please retry.', login:'Please sign in again.', forbidden:'Merchant account required.', empty:'No paid items in this period',
            quantity:'{n} units', month:'Month', orders:'Paid orders', amount:'Sales (CNY)', summary:'{orders} paid orders and {quantity} purchased units in this period',
            updated:'Updated {time}', excluded:'{n} lines with non-positive quantities or negative prices are excluded from price distribution.'},
        ar: {heading:'رؤى المبيعات وتحليل البيانات', insight:'رؤى متجري', sales:'مبيعاتي', industry:'اتجاهات القطاع', refresh:'تحديث',
            basis:'آخر 365 يوماً · منتجات متجرك المدفوعة بالكامل · حسب تاريخ إنشاء الطلب · باليوان دون الشحن',
            top:'أفضل 5 منتجات حسب الكمية', price:'توزيع سعر الوحدة المدفوع', monthly:'الطلبات المدفوعة خلال 6 أشهر تقويمية', salesTop:'أفضل 5 منتجات حسب المبيعات',
            priceNote:'حسب عدد الوحدات وليس وزن الشاي. يشمل النطاق الحد الأدنى ويستثني الأعلى؛ الفئة الأخيرة بلا حد أعلى.', priceCurrency:'اليوان الصيني · CNY', priceUnit:'CNY / وحدة', below:'أقل من {n}', above:'{n} فأكثر', monthlyNote:'الشهر الحالي حتى وقت الاستعلام. طلبات متجرك المدفوعة بالكامل فقط.',
            industryMissing:'لم يتم ربط مصدر موثق لبيانات القطاع بعد.', unavailable:'لم يتم ربط تفضيلات المذاق أو المبيعات الإقليمية أو التصدير أو المنافسين أو السياسات.',
            loading:'جارٍ تحميل بيانات المبيعات…', failed:'تعذر تحميل بيانات المبيعات. يرجى المحاولة مجدداً.', login:'يرجى تسجيل الدخول مجدداً.', forbidden:'يلزم حساب تاجر.', empty:'لا توجد منتجات مدفوعة في هذه الفترة',
            quantity:'{n} وحدة', month:'الشهر', orders:'الطلبات المدفوعة', amount:'المبيعات (CNY)', summary:'{orders} طلبات مدفوعة و{quantity} وحدة مشتراة خلال الفترة',
            updated:'تم التحديث {time}', excluded:'تم استبعاد {n} سجلات بكميات غير موجبة أو أسعار سالبة من توزيع الأسعار.'}
    };
    var ranges = {'under_80':[null,80], '80_to_120':[80,120], '120_to_280':[120,280], '280_plus':[280,null]};
    function locale(language) { return language === 'ar' ? 'ar' : language === 'en' ? 'en' : 'zh-CN'; }
    function number(value, language) { return Number(value).toLocaleString(locale(language), {maximumFractionDigits:1}); }
    function currency(value, language) { return Number(value).toLocaleString(locale(language), {style:'currency',currency:'CNY'}); }
    function width(value, maximum) { return maximum > 0 ? Math.min(100, Math.max(0, value / maximum * 100)) : 0; }
    function count(value) { return Number.isInteger(value) && value >= 0; }
    function money(value) { return typeof value === 'string' && /^-?\d+\.\d{2}$/.test(value) && Number.isFinite(Number(value)); }
    function productsValid(rows) {
        return Array.isArray(rows) && rows.length <= 5 && rows.every(function (row) {
            return row && count(row.product_id) && typeof row.name === 'string' && count(row.quantity) && money(row.amount);
        });
    }
    function valid(data) {
        return !!(data && data.scope === 'merchant_only' && data.currency === 'CNY' && data.totals && data.period
            && count(data.totals.paid_orders) && count(data.totals.quantity) && money(data.totals.amount)
            && Number.isFinite(Date.parse(data.generated_at))
            && productsValid(data.top_products) && productsValid(data.sales_top_products)
            && Array.isArray(data.monthly) && data.monthly.length === 6 && data.monthly.every(function (row) {
                return row && /^\d{4}-(0[1-9]|1[0-2])$/.test(row.month) && count(row.order_count) && money(row.amount);
            }) && data.price_distribution && count(data.price_distribution.quantity) && count(data.price_distribution.excluded_lines)
            && Array.isArray(data.price_distribution.buckets) && data.price_distribution.buckets.length === 4
            && data.price_distribution.buckets.every(function (row, index) {
                return row && row.code === Object.keys(ranges)[index] && count(row.quantity)
                    && (data.price_distribution.quantity ? typeof row.percent === 'number' && Number.isFinite(row.percent) && row.percent >= 0 && row.percent <= 100 : row.percent === null);
            }));
    }
    function createController(options) {
        var generation = 0;
        return {
            refresh: async function () {
                var current = ++generation, token = options.token();
                options.onState({status:'loading',token:token});
                if (!token) { options.onState({status:'error',reason:'login'}); return; }
                try {
                    var data = await options.request(token);
                    if (current !== generation) return;
                    if (options.token() !== token) { options.onState({status:'error',reason:'login'}); return; }
                    if (!valid(data)) throw new Error('invalid');
                    options.onState({status:'ready',data:data,token:token});
                } catch (error) {
                    if (current === generation) options.onState({status:'error',reason:error.status === 401 ? 'login' : error.status === 403 ? 'forbidden' : 'failed'});
                }
            },
            cancel: function () { generation++; }
        };
    }
    function element(doc, tag, text, className) {
        var node = doc.createElement(tag); if (text !== undefined) node.textContent = text;
        if (className) node.className = className; return node;
    }
    function bar(doc, name, value, percent) {
        var row = element(doc,'li',undefined,'insight-row');
        var label = element(doc,'span',name,'insight-name');
        var track = element(doc,'span',undefined,'insight-bar'), fill = element(doc,'i');
        track.setAttribute('aria-hidden','true'); fill.style.width = Math.max(0,Math.min(100,percent || 0)) + '%';
        track.append(fill); row.append(label,track,element(doc,'span',value,'insight-value')); return row;
    }
    function renderProducts(doc, target, products, language, byAmount) {
        target.replaceChildren(); var t = words[language] || words.zh;
        if (!products.length) { target.append(element(doc,'li',t.empty,'insight-empty')); return; }
        var key = byAmount ? 'amount' : 'quantity';
        var maximum = Math.max.apply(null, products.map(function (row) {return Number(row[key]);}));
        products.forEach(function (row) {
            target.append(bar(doc,row.name,byAmount ? currency(row.amount,language) : t.quantity.replace('{n}',number(row.quantity,language)),width(Number(row[key]),maximum)));
        });
    }
    function renderPrices(doc, target, distribution, language) {
        target.replaceChildren(); var t = words[language] || words.zh;
        if (!distribution.quantity) { target.append(element(doc,'li',t.empty,'insight-empty')); return; }
        distribution.buckets.forEach(function (row) {
            var bounds = ranges[row.code];
            var label = bounds[0] === null ? t.below.replace('{n}',number(bounds[1],language))
                : bounds[1] === null ? t.above.replace('{n}',number(bounds[0],language))
                : number(bounds[0],language) + ' – ' + number(bounds[1],language);
            var item = bar(doc,'','',row.percent); item.className = 'insight-row insight-price-row';
            var rangeLabel = element(doc,'bdi',label,'insight-price-range');
            if (bounds[0] !== null && bounds[1] !== null) rangeLabel.setAttribute('dir','ltr');
            item.children[0].append(rangeLabel,element(doc,'small',t.priceUnit,'insight-price-unit'));
            item.children[2].append(element(doc,'strong',Number(row.percent / 100).toLocaleString(locale(language),{style:'percent',maximumFractionDigits:1})),
                element(doc,'small',t.quantity.replace('{n}',number(row.quantity,language))));
            target.append(item);
        });
    }
    function renderMonths(doc, target, monthly, language) {
        target.replaceChildren();
        monthly.forEach(function (row) {
            var tr = element(doc,'tr');
            var month = new Date(row.month + '-01T00:00:00+08:00').toLocaleDateString(locale(language), {year:'numeric',month:'short',timeZone:'Asia/Shanghai'});
            tr.append(element(doc,'th',month),element(doc,'td',number(row.order_count,language)),element(doc,'td',currency(row.amount,language)));
            tr.children[0].setAttribute('scope','row'); target.append(tr);
        });
    }
    function mount(win) {
        var doc = win.document, root = doc.getElementById('merchant-insights'); if (!root) return;
        var state = {status:'loading'}, active = 0, abort, timeout;
        var button = doc.getElementById('insights-refresh'), tabs = Array.from(root.querySelectorAll('[role=tab]'));
        var token = function () { return win.AuthStorage && win.AuthStorage.getToken(); };
        function setTab(index, focus) {
            active = index;
            tabs.forEach(function (tab, position) {
                var selected = position === index; tab.classList.toggle('active',selected); tab.setAttribute('aria-selected',String(selected)); tab.tabIndex = selected ? 0 : -1;
                var panel = doc.getElementById(tab.getAttribute('aria-controls')); panel.hidden = !selected; panel.classList.toggle('active',selected);
            });
            if (focus) tabs[active].focus();
        }
        tabs.forEach(function (tab, index) {
            tab.addEventListener('click',function () {setTab(index);});
            tab.addEventListener('keydown',function (event) {
                var next = index, rtl = doc.documentElement.dir === 'rtl';
                if (event.key === 'Home') next = 0; else if (event.key === 'End') next = tabs.length - 1;
                else if (event.key === 'ArrowRight') next += rtl ? -1 : 1;
                else if (event.key === 'ArrowLeft') next += rtl ? 1 : -1; else return;
                event.preventDefault();setTab((next + tabs.length) % tabs.length,true);
            });
        });
        function render(next) {
            state = next; var language = doc.documentElement.lang.split('-')[0], t = words[language] || words.zh;
            root.querySelectorAll('[data-insight-text]').forEach(function (node) {node.textContent = t[node.dataset.insightText];});
            var ready = state.status === 'ready' && state.token === token(), data = ready ? state.data : null;
            root.setAttribute('aria-busy',String(state.status === 'loading')); button.disabled = state.status === 'loading';
            ['insights-top-products','insights-price-list','insights-sales-top'].forEach(function (id) {doc.getElementById(id).replaceChildren();});
            doc.getElementById('insights-months').replaceChildren();
            var status = doc.getElementById('insights-status');
            status.textContent = data ? t.updated.replace('{time}',new Date(data.generated_at).toLocaleString(locale(language))) : t[state.status === 'loading' ? 'loading' : state.reason || 'failed'];
            var summary = doc.getElementById('insights-summary'); summary.textContent = data ? t.summary.replace('{orders}',number(data.totals.paid_orders,language)).replace('{quantity}',number(data.totals.quantity,language)) : '';
            var excluded = doc.getElementById('insights-excluded'); excluded.hidden = !(data && data.price_distribution.excluded_lines);
            excluded.textContent = data ? t.excluded.replace('{n}',data.price_distribution.excluded_lines) : '';
            root.querySelectorAll('[data-insight-data]').forEach(function (node) {node.hidden = !data;});
            if (!data) return;
            renderProducts(doc,doc.getElementById('insights-top-products'),data.top_products,language,false);
            renderProducts(doc,doc.getElementById('insights-sales-top'),data.sales_top_products,language,true);
            renderPrices(doc,doc.getElementById('insights-price-list'),data.price_distribution,language);
            renderMonths(doc,doc.getElementById('insights-months'),data.monthly,language);
        }
        var controller = createController({token:token,onState:render,request:async function (auth) {
            if (abort) abort.abort(); win.clearTimeout(timeout); abort = new win.AbortController();
            var currentAbort = abort, currentTimeout = win.setTimeout(function () {currentAbort.abort();},12000); timeout = currentTimeout;
            try {
                var response = await win.fetch('/v1/supplier/insights',{headers:{Authorization:'Bearer ' + auth},cache:'no-store',signal:currentAbort.signal});
                if (!response.ok) {var error = new Error('request');error.status = response.status;throw error;}
                var body = await response.json();if(body.code !== 200) throw new Error('envelope');return body.data;
            } finally {win.clearTimeout(currentTimeout);}
        }});
        button.addEventListener('click',controller.refresh);
        doc.addEventListener('supplier:panel-changed',function (event) {if(event.detail.panel === 'dashboard') controller.refresh();});
        doc.addEventListener('visibilitychange',function () {if(!doc.hidden && root.offsetParent !== null) controller.refresh();});
        new win.MutationObserver(function () {render(state);}).observe(doc.documentElement,{attributes:true,attributeFilter:['lang']});
        win.addEventListener('pagehide',function () {controller.cancel();if(abort)abort.abort();win.clearTimeout(timeout);});
        win.addEventListener('pageshow',function (event) {if(event.persisted)controller.refresh();});
        setTab(0);controller.refresh();
    }
    return {createController:createController,renderProducts:renderProducts,renderPrices:renderPrices,renderMonths:renderMonths,width:width,mount:mount};
});
