// Run: node client/tests/tea-saas-brand.test.js; no browser or model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = file => fs.readFileSync(path.join(__dirname, '../static/js', file), 'utf8');
const forbidden = /9710|报关|清关|customs|الجمارك|الجمرك|جمركية/i;
for (const file of ['login-portal.js', 'buyer-workbench.js', 'buyer-products.js', 'supplier-workbench.js']) {
    const source = read(file);
    assert(!forbidden.test(source), file);
    const start = source.indexOf('    var i18n = {');
    const end = source.indexOf('\n    };', start) + '\n    };'.length;
    const labels = vm.runInNewContext(source.slice(start, end) + '\ni18n;');
    for (const language of ['zh', 'en', 'ar']) {
        const values = labels[language];
        if (values.logo_text) assert(values.logo_text.includes('SaaS'));
        if (values.brand_name) assert(values.brand_name.includes('SaaS'));
        if (values.procure_title) assert(values.procure_title.includes('SaaS'));
        if (values.stat_in_transit) assert.equal('stat_customs' in values, false);
    }
}

const source = read('operations-dashboard.js');
const functions = source.slice(source.indexOf('    function initSalesTrendChart('), source.indexOf('    function initMapChart('));
let options;
const context = {
    document: {getElementById: () => ({})},
    echarts: {init: () => ({setOption: option => {options = option;}})},
    registerChart() {}, colorPrimary: '#185c3b', colorMuted: '#6a7d73', colorGold: '#91b19b', colorTea: '#50886a'
};
vm.runInNewContext(functions, context);
context.initSalesTrendChart({monthly: [{label: '01', sales: 45}, {label: '02', sales: 0}]});
assert.deepEqual(Array.from(options.series[0].data), [45, 0]);
assert.equal(options.series.length, 1, 'no invented benchmark series');
context.initSalesTrendChart({monthly: []});
assert.equal(options.series[0].data.length, 0, 'empty data never fills demo points');
context.initOrderStatusChart({summary: {unpaid: 1, pending_ship: 2, in_transit: 3, completed: 4}});
assert.deepEqual(Array.from(options.series[0].data, row => row.value), [1, 2, 3, 4]);
context.initOrderStatusChart({summary: {}});
assert(options.series[0].data.every(row => row.value === 0));
console.log('PASS: three-language SaaS branding, order-state chart and actual monthly-sales chart contracts');
