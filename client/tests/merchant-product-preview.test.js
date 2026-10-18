const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const nodes = [];
function element(tag) {
    const el = { tag, children: [], listeners: {}, setAttribute(key, value) { this[key] = value; },
        append(...children) { this.children.push(...children); },
        appendChild(child) { this.children.push(child); return child; },
        replaceChildren() { this.children = []; },
        addEventListener(key, callback) { this.listeners[key] = callback; },
        showModal() { this.open = true; }, close() { this.open = false; } };
    nodes.push(el); return el;
}
const body = element('body');
const context = { document: { body, createElement: element,
    getElementById: id => nodes.find(el => el.id === id) || null } };
context.window = context;
const source = name => fs.readFileSync(path.join(__dirname, '../static/js', name), 'utf8');
vm.runInNewContext(source('merchant-product-preview.js'), context);
context.MerchantProductPreview.open({ sku_id: 8, nameZh: '<test-product>', image: '/test.png',
    cat1: 'Black tea', priceUsd: 3.5, stock: 12, is_launched: false, caption: '<script>synthetic</script>' });
const dialog = context.document.getElementById('merchant-product-preview');
assert.equal(dialog.open, true);
assert.equal(body.children.length, 1);
assert.ok(nodes.some(el => el.textContent === '<script>synthetic</script>')); // text, never HTML
assert.ok(nodes.some(el => el.textContent === 'USD 3.50'));
assert.ok(nodes.some(el => el.textContent === '下架'));
assert.equal(nodes.some(el => ['a', 'form', 'input'].includes(el.tag)), false);
nodes.find(el => el.tag === 'button').listeners.click();
assert.equal(dialog.open, false);
context.MerchantProductPreview.open({ sku_id: 9, nameZh: 'Next', priceUsd: 4, stock: 0, is_launched: true });
assert.equal(dialog.open, true);
assert.equal(body.children.length, 1);
assert.equal(dialog.children.length, 2);
const merchantScript = source('merchant_products.js');
assert.equal(merchantScript.includes('product_details.html'), false);
assert.equal(merchantScript.includes('window.open('), false);
assert.ok(merchantScript.includes('data-act="view"'));
console.log('PASS: read-only merchant preview, safe text, close/reopen and no buyer navigation');
