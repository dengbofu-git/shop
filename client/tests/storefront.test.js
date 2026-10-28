// Rendering behavior: own-store navigation, literal text and non-interactive previews.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.attrs = {}; this.textContent = ''; }
    appendChild(node) { this.children.push(node); return node; }
    append(...nodes) { this.children.push(...nodes); }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(name, value) { this.attrs[name] = value; }
    getAttribute(name) { return this.attrs[name]; }
}
let language = 'zh';
const document = {createElement: tag => new Element(tag), getElementById: () => null};
const context = {TeaMoney: require('../static/js/currency.js'),window: {}, document, localStorage: {getItem: () => language}};
vm.runInNewContext(fs.readFileSync('client/static/js/storefront.js', 'utf8'), context);
const ui = context.window.Storefront;
const merchant = {id: 23, name: '<img src=x onerror=alert(1)>', url: '/store.html?merchant_id=23', is_published: true};
const link = ui.merchantLink(merchant);
assert.equal(link.children[1].href, '/store.html?merchant_id=23');
assert(link.children[0].textContent.includes('<img'), 'names render as literal text');
assert.equal(link.children[0].children.length, 0, 'no merchant HTML is interpreted');
assert.equal(ui.merchantLink({...merchant, is_published: false}).children[1].tag, 'span');
assert.equal(ui.merchantLink({...merchant, id: '../other'}).children[1].tag, 'span');
assert.equal(ui.merchantLink(null).children.length, 1);
language = 'en';
assert.equal(ui.merchantLink(merchant).children[1].textContent, 'View store →');
const hero = new Element('section');
ui.hero(hero, {name: 'Our tea', summary: '<script>bad</script>', welcome: 'Hello'});
assert.equal(hero.children.length, 2);
assert.equal(hero.children[1].children[1].children[2].textContent, '<script>bad</script>');
const favoriteActions = new Element('div');
ui.hero(hero, {name: 'Our tea'}, favoriteActions);
assert.equal(hero.children[1].children[2], favoriteActions, 'favorite control belongs inside the store identity card');
ui.hero(hero, {name: 'Updated tea'}, favoriteActions);
assert.equal(hero.children[1].children[2], favoriteActions, 'reuse the existing control and its event handlers after a redraw');
ui.hero(hero, {name: 'Merchant preview'});
assert.equal(hero.children[1].children.length, 2, 'merchant preview has no buyer favorite controls');
const cards = new Element('div');
const row = {skuid: 51, product_name: 'Black tea', name: '150g', price: '12.50'};
ui.cards(cards, [row], false);
assert.equal(cards.children[0].children[0].href, '/product_details.html?skuid=51');
assert.equal(cards.children[0].children[4].children[0].disabled, false);
ui.cards(cards, [row], true);
assert.equal(cards.children[0].children[0].tag, 'div');
assert.equal(cards.children[0].children[4].children[0].disabled, true);
ui.cards(cards, [], false);
assert.equal(cards.children[0].className, 'store-empty');
console.log('Storefront rendering checks passed.');
