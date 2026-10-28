// Run the real bundle renderer with synthetic DOM nodes and priced plans.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(require.resolve('../static/js/buyer-support.js'), 'utf8');
const renderer = source.slice(source.indexOf('    function shownMoney('), source.indexOf('    function displayTime('));

function render(quantity, override = {}) {
    const all = [];
    const node = tag => {
        const value = {tag, children: [], attributes: {}, textContent: '',
            appendChild(child) {this.children.push(child); child.parentNode = this;},
            setAttribute(key, val) {this.attributes[key] = val;}, addEventListener() {}};
        all.push(value);
        return value;
    };
    const root = node('article'), bubble = node('div'); root.appendChild(bubble);
    const item = {sku_id: 23, product_name: 'Synthetic tea', name: '200g', currency: 'CNY',
        quantity, price: '0.01', line_subtotal: (quantity / 100).toFixed(2), ...override};
    const bundle = {bundle_id: 'bundle-aaaaaaaaaaaa', currency: 'CNY', items: [item],
        subtotal: item.line_subtotal, remaining_budget: '0.00', summary: 'Synthetic summary'};
    const context = {document: {createElement: node, getElementById: () => ({value: 'CNY'})},
        TeaMoney: {format: value => '¥' + value}, busy: false};
    vm.createContext(context);
    vm.runInContext(renderer + '\nthis.renderBundles = showBundles;', context);
    context.renderBundles(bubble, {recommendation_bundles: [bundle], primary_bundle_id: bundle.bundle_id,
        presentation_version: 'bundles-v2', intent: 'recommendation'});
    return {all, bubble};
}

test('large automatic quantities render with consistent line and plan totals', () => {
    const page = render(10000000);
    assert(page.all.some(n => n.className === 'bs-bundle-quantity' && n.textContent.includes('10000000')));
    assert(page.all.some(n => n.className === 'bs-bundle-total' && n.textContent.includes('100000.00')));
    assert.equal(page.bubble.textContent, 'Synthetic summary');
});

test('an unsafe quantity cannot be rendered as a valid priced plan', () => {
    const page = render(Number.MAX_SAFE_INTEGER + 1);
    assert(!page.all.some(n => n.className === 'bs-product'));
    assert(page.all.some(n => n.tag === 'small'));
});

test('a large quantity does not bypass line subtotal verification', () => {
    const page = render(10000000, {line_subtotal: '1.00'});
    assert(!page.all.some(n => n.className === 'bs-product'));
    assert(page.all.some(n => n.tag === 'small'));
});
