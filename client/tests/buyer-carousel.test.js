// Run: node client/tests/buyer-carousel.test.js [isolated-carousel-response.json]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/js/buyer-carousel.js'), 'utf8');
class Element {
    constructor(tag = 'div') { this.tag = tag; this.children = []; this.attrs = {}; this.events = {}; this.hidden = false; this.textContent = ''; }
    setAttribute(key, value) { this.attrs[key] = String(value); }
    addEventListener(type, fn) { (this.events[type] ||= new Set()).add(fn); }
    removeEventListener(type, fn) { this.events[type]?.delete(fn); }
    appendChild(child) { child.parent = this; this.children.push(child); return child; }
    replaceChildren() { this.children = []; }
    querySelectorAll(selector) {
        const matches = [];
        const visit = el => { if (selector.startsWith('[') && Object.hasOwn(el.attrs, selector.slice(1, -1))) matches.push(el); el.children.forEach(visit); };
        this.children.forEach(visit); return matches;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0]; }
    contains(target) { return target === this || this.children.some(child => child.contains(target)); }
    event(type, fields = {}) {
        const event = {prevented: false, preventDefault() { this.prevented = true; }, ...fields};
        [...(this.events[type] || [])].forEach(fn => fn(event)); return event;
    }
}
const data = [1, 2, 3].map(id => ({skuid: id, title: 'Tea ' + id, intro: 'Spec ' + id, price: '100.00',
    image_url: '/v1/goods/sku/' + id + '/image', link_url: 'javascript:invalid'}));
const response = rows => ({ok: true, json: async () => ({code: 200, data: rows})});
function setup(fetcher = () => Promise.resolve(response(data)), reduced = false) {
    const root = new Element('section'), elements = {};
    for (const name of ['viewport','controls','dots','counter','feedback','retry','status','heading','hint']) {
        elements[name] = root.appendChild(new Element()); elements[name].setAttribute('data-carousel-' + name, '');
    }
    elements.viewport.id = 'buyer-banner-slider';
    const document = new Element(); document.documentElement = {dir: 'ltr'}; document.hidden = false;
    root.focus = () => { document.activeElement = root; };
    document.createElement = tag => new Element(tag);
    const window = new Element(), media = new Element(); media.matches = reduced;
    const timers = new Map(); let nextTimer = 1;
    Object.assign(window, {location: {href: 'http://fixture/buyer_dashboard.html'}, matchMedia: () => media,
        setTimeout(fn, ms) { assert.equal(ms, 6000); const id = nextTimer++; timers.set(id, fn); return id; },
        clearTimeout(id) { timers.delete(id); }});
    const labels = {carousel_heading: 'Discover tea', carousel_goto: 'View {n}', btn_view_sku: 'Details',
        carousel_play: 'Play', carousel_pause: 'Pause', carousel_price: 'Reference price'};
    const workbench = fs.readFileSync(path.join(__dirname, '../static/js/buyer-workbench.js'), 'utf8');
    const formatter = workbench.slice(workbench.indexOf('    function formatDisplayPrice('), workbench.indexOf('    function updatePrices('));
    const pricing = {currentCurrency: 'USD', TeaMoney:require('../static/js/currency.js')}; vm.runInNewContext(formatter, pricing);
    const context = {window, document, URL}; vm.runInNewContext(source, context);
    const controller = window.BuyerCarousel.start({root, url: '/v1/goods/carousel?stable=1&limit=6',
        fetch: fetcher, labels: () => labels, formatPrice: value => pricing.formatDisplayPrice(value)});
    return {root, elements, document, window, media, timers, labels, pricing, controller,
        get slides() { return elements.viewport.children; },
        get index() { return elements.viewport.children.findIndex(slide => !slide.hidden); },
        fire() { const [id, fn] = timers.entries().next().value; timers.delete(id); fn(); }};
}
const tick = () => new Promise(resolve => setImmediate(resolve));
async function main() {
    const app = setup(() => Promise.resolve(response([...data, data[0], null, {skuid: -1}])));
    assert.equal(app.root.attrs['aria-busy'], 'true');
    await app.controller.ready;
    assert.equal(app.slides.length, 3); assert.equal(app.index, 0); assert.equal(app.timers.size, 1);
    assert.equal(app.slides.filter(slide => !slide.hidden).length, 1);
    const [copy, picture] = app.slides[0].children;
    assert.equal(picture.tag, 'div');
    assert.equal(app.slides[0].tag, 'a'); assert.equal(app.slides[0].href, 'product_details.html?skuid=1');
    assert.equal(picture.children[0].tag, 'img'); assert.equal(picture.children[0].src, 'http://fixture/v1/goods/sku/1/image');
    assert.equal(app.slides[1].children[1].children[0].loading, 'eager', 'preload the next photo');
    assert.equal(app.slides[2].children[1].children[0].loading, 'lazy');
    const price = copy.children[2].children[0].children[1]; assert.equal(price.textContent, '$14.00');
    app.pricing.currentCurrency = 'CNY'; app.controller.refreshPrices(); assert.equal(price.textContent, '\u00a5100.00');
    app.pricing.currentCurrency = 'AED'; app.controller.refreshPrices(); assert.equal(price.textContent, 'AED 51.00');
    app.fire(); assert.equal(app.index, 1); assert.equal(app.timers.size, 1);
    app.root.event('keydown', {key: 'ArrowLeft'}); app.root.event('keydown', {key: 'ArrowLeft'}); assert.equal(app.index, 2);
    app.root.event('keydown', {key: 'ArrowRight'}); assert.equal(app.index, 0);
    assert.equal(app.elements.dots.children[0].attrs['aria-current'], 'true');
    assert(app.elements.dots.children.every(dot => dot.tag === 'span' && !dot.events.click));
    assert.equal(copy.children[2].children.length, 1, 'price only; no product CTA button');
    app.labels.carousel_heading = 'Translated heading';
    app.controller.setLanguage(); assert.equal(app.elements.heading.textContent, 'Translated heading');
    assert.equal(app.timers.size, 1);
    assert.equal(app.root.attrs['data-carousel-running'], 'true');
    app.root.event('mouseenter'); assert.equal(app.timers.size, 0);
    assert.equal(app.root.attrs['data-carousel-running'], 'false');
    app.root.event('mouseleave'); assert.equal(app.timers.size, 1);
    app.root.event('focusin'); assert.equal(app.timers.size, 0);
    app.root.event('focusout', {relatedTarget: copy}); assert.equal(app.timers.size, 0);
    app.root.event('focusout', {relatedTarget: null}); assert.equal(app.timers.size, 1);
    app.document.hidden = true; app.document.event('visibilitychange'); assert.equal(app.timers.size, 0);
    app.document.hidden = false; app.document.event('visibilitychange'); assert.equal(app.timers.size, 1);
    app.window.event('pagehide'); assert.equal(app.timers.size, 0);
    app.window.event('pageshow'); app.window.event('pageshow'); assert.equal(app.timers.size, 1);
    const announcement = app.elements.status.textContent; app.fire(); assert.equal(app.index, 1);
    assert.equal(app.elements.status.textContent, announcement, 'automatic rotation does not repeatedly announce');
    app.document.documentElement.dir = 'rtl'; app.controller.setLanguage();
    app.document.activeElement = app.slides[1].children[1];
    assert(app.root.event('keydown', {key: 'ArrowRight'}).prevented); assert.equal(app.index, 0);
    assert.equal(app.document.activeElement, app.root, 'arrow navigation never leaves focus inside a hidden slide');
    app.document.documentElement.dir = 'ltr';
    app.elements.viewport.event('pointerdown', {pointerId: 1, pointerType: 'touch', clientX: 200, clientY: 20});
    app.elements.viewport.event('pointerup', {pointerId: 1, clientX: 100, clientY: 22}); assert.equal(app.index, 1);
    assert(app.elements.viewport.event('click').prevented, 'swipe must not activate product link');
    app.elements.viewport.event('pointerdown', {pointerId: 2, pointerType: 'touch', clientX: 100, clientY: 20});
    app.elements.viewport.event('pointerup', {pointerId: 2, clientX: 98, clientY: 150}); assert.equal(app.index, 1);
    assert(!app.elements.viewport.event('click').prevented, 'vertical scrolling does not block normal taps');
    picture.children[0].event('error'); assert.equal(picture.children[0].src, '/static/images/cart/product_normal.png');
    picture.children[0].event('error'); assert(picture.children[0].hidden); assert(!picture.children[1].hidden);
    await app.controller.reload(); assert.equal(app.slides.length, 3); assert.equal(app.timers.size, 1, 'manual switching does not require a play button to resume');
    assert.equal(picture.children[0].events.error.size, 0, 'reload releases detached slide listeners');
    app.controller.destroy(); app.root.event('mouseleave'); assert.equal(app.timers.size, 0);

    const reduced = setup(undefined, true); await reduced.controller.ready;
    assert.equal(reduced.timers.size, 0); reduced.root.event('keydown', {key: 'ArrowRight'}); assert.equal(reduced.index, 1);
    reduced.media.matches = true; reduced.media.event('change'); assert.equal(reduced.timers.size, 0);
    reduced.media.matches = false; reduced.media.event('change'); assert.equal(reduced.timers.size, 1);
    reduced.media.matches = true; reduced.media.event('change'); assert.equal(reduced.timers.size, 0);
    const single = setup(() => Promise.resolve(response(data.slice(0, 1)))); await single.controller.ready;
    assert(single.elements.controls.hidden); assert.equal(single.timers.size, 0);
    const empty = setup(() => Promise.resolve(response([]))); await empty.controller.ready;
    assert(empty.elements.viewport.hidden && empty.elements.controls.hidden); assert.equal(empty.elements.feedback.textContent, 'banner_empty');
    let failures = true;
    const retry = setup(() => failures ? Promise.reject(Error('offline')) : Promise.resolve(response(data)));
    await retry.controller.ready; assert(!retry.elements.retry.hidden); assert.equal(retry.elements.feedback.textContent, 'carousel_error');
    failures = false; retry.elements.retry.event('click'); await tick(); assert.equal(retry.slides.length, 3); assert(retry.elements.retry.hidden);
    assert.equal(retry.root.events.mouseenter.size, 1, 'retry never duplicates persistent listeners');
    for (const fetcher of [
        () => Promise.resolve({ok: false}),
        () => Promise.resolve({ok: true, json: async () => {throw Error('not JSON');}}),
        () => Promise.resolve({ok: true, json: async () => ({code: 200, data: {}})})
    ]) {
        const invalid = setup(fetcher); await invalid.controller.ready;
        assert(!invalid.elements.retry.hidden && invalid.elements.controls.hidden);
        invalid.controller.destroy();
    }
    const noImage = setup(() => Promise.resolve(response([{...data[0], image_url: 'javascript:invalid', price: null}])));
    await noImage.controller.ready;
    assert.equal(noImage.slides[0].children[1].children[0].src, '/static/images/cart/product_normal.png');
    assert.equal(noImage.slides[0].children[0].children[2].children.length, 0, 'unknown price is omitted instead of invented');
    noImage.controller.destroy();
    let resolveOld;
    const race = setup(() => new Promise(resolve => {resolveOld = resolve;}));
    const firstResolve = resolveOld, latest = race.controller.reload();
    resolveOld(response(data.slice(1))); await latest; firstResolve(response(data)); await race.controller.ready;
    assert.equal(race.slides.length, 2, 'stale load must not replace newer response');
    const pending = setup(() => new Promise(resolve => {resolveOld = resolve;}));
    pending.controller.destroy(); resolveOld(response(data)); await pending.controller.ready; assert.equal(pending.slides.length, 0);
    if (process.argv[2]) {
        const actualBody = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
        const actual = setup(() => Promise.resolve({ok: true, json: async () => actualBody}));
        await actual.controller.ready; assert.equal(actual.slides.length, 6);
        actual.slides.forEach(slide => assert(slide.href.includes('product_details.html?skuid=')));
        actual.controller.destroy();
    }
    [reduced, single, empty, retry, race].forEach(item => item.controller.destroy());
    console.log('PASS: full-slide links, no button controls, price/progress, autoplay resumption, keyboard/RTL/swipe, reduced motion, empty/error/retry, stale requests and cleanup');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
