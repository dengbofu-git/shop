/** Homepage product carousel. Images stay in normal DOM, independent of theme backgrounds. */
(function () {
    'use strict';
    window.BuyerCarousel = {
        start: function (options) {
            var root = options.root;
            var viewport = root.querySelector('[data-carousel-viewport]');
            var controls = root.querySelector('[data-carousel-controls]');
            var dots = root.querySelector('[data-carousel-dots]');
            var counter = root.querySelector('[data-carousel-counter]');
            var feedback = root.querySelector('[data-carousel-feedback]');
            var retry = root.querySelector('[data-carousel-retry]');
            var announcement = root.querySelector('[data-carousel-status]');
            var heading = root.querySelector('[data-carousel-heading]');
            var hint = root.querySelector('[data-carousel-hint]');
            var media = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
            var paused = !!(media && media.matches), hovered = false, focused = false, suspended = false;
            var index = 0, rows = [], slides = [], indicators = [], prices = [], images = [];
            var timer = null, requestId = 0, destroyed = false, state = 'loading', pointer = null, suppressClick = false;
            var listeners = [], slideListeners = [];
            function text(key) { return options.labels()[key] || key; }
            function rtl() { return document.documentElement.dir === 'rtl'; }
            function on(target, event, handler, transient) {
                target.addEventListener(event, handler);
                (transient ? slideListeners : listeners).push(function () { target.removeEventListener(event, handler); });
            }
            function clearSlides() {
                slideListeners.forEach(function (remove) { remove(); }); slideListeners = [];
                viewport.replaceChildren(); dots.replaceChildren();
                slides = []; indicators = []; prices = []; images = [];
            }
            function stop() {
                if (timer !== null) { window.clearTimeout(timer); timer = null; }
                root.setAttribute('data-carousel-running', 'false');
            }
            function schedule() {
                stop();
                if (destroyed || state !== 'ready' || rows.length < 2 || paused || hovered || focused || suspended || document.hidden) return;
                root.setAttribute('data-carousel-running', 'true');
                // Recreate the decorative fill so its six-second animation follows the actual timer.
                indicators[index].replaceChildren();
                indicators[index].appendChild(node('span', 'carousel-progress-fill'));
                timer = window.setTimeout(function () { go(index + 1, false); }, 6000);
            }
            function refreshPrices() {
                prices.forEach(function (node, i) {
                    if (node) node.textContent = options.formatPrice(rows[i].price);
                });
            }
            function refresh() {
                root.setAttribute('aria-label', text('carousel_label'));
                root.setAttribute('aria-roledescription', text('carousel_role'));
                heading.textContent = text('carousel_heading');
                if (hint) hint.textContent = text('carousel_hint');
                retry.textContent = text('grid_retry');
                controls.hidden = state !== 'ready' || rows.length < 2;
                counter.hidden = state !== 'ready';
                viewport.hidden = state !== 'ready';
                feedback.hidden = state === 'ready';
                retry.hidden = state !== 'error';
                feedback.textContent = text(state === 'error' ? 'carousel_error' : state === 'empty' ? 'banner_empty' : 'banner_loading');
                root.setAttribute('aria-busy', String(state === 'loading'));
                if (state === 'ready') counter.textContent = (index + 1) + ' / ' + rows.length;
                slides.forEach(function (slide, i) {
                    slide.hidden = i !== index;
                    slide.setAttribute('aria-roledescription', text('carousel_slide'));
                    slide.setAttribute('aria-label', (i + 1) + ' / ' + rows.length + ': ' + rows[i].title);
                    indicators[i].setAttribute('aria-current', String(i === index));
                    images[i].loading = i === index || i === (index + 1) % rows.length ? 'eager' : 'lazy';
                });
                root.querySelectorAll('[data-carousel-price-label]').forEach(function (node) { node.textContent = text('carousel_price'); });
                root.querySelectorAll('[data-carousel-image-fallback]').forEach(function (node) { node.textContent = text('carousel_image_missing'); });
                refreshPrices();
            }
            function go(target, manual) {
                if (!rows.length || state !== 'ready') return;
                index = (target % rows.length + rows.length) % rows.length;
                refresh();
                if (manual) announcement.textContent = (index + 1) + ' / ' + rows.length + ': ' + rows[index].title;
                schedule();
            }
            function node(tag, className, value) {
                var element = document.createElement(tag);
                if (className) element.className = className;
                if (value != null) element.textContent = value;
                return element;
            }
            function imageSource(value) {
                try {
                    var url = new URL(String(value || ''), window.location.href);
                    return value && /^(https?:)$/.test(url.protocol) ? url.href : '/static/images/cart/product_normal.png';
                } catch (_) { return '/static/images/cart/product_normal.png'; }
            }
            function render() {
                clearSlides();
                rows.forEach(function (row, i) {
                    var slide = node('a', 'carousel-slide');
                    slide.href = 'product_details.html?skuid=' + row.skuid;
                    var copy = node('div', 'carousel-copy');
                    copy.appendChild(node('h2', 'carousel-title', row.title));
                    copy.appendChild(node('p', 'carousel-description', row.intro));
                    var purchase = node('div', 'carousel-purchase');
                    var price = null;
                    if (row.price !== null) {
                        var priceBlock = node('div', 'carousel-price-block');
                        var priceLabel = node('span', 'carousel-price-label'); priceLabel.setAttribute('data-carousel-price-label', '');
                        price = node('strong', 'carousel-price');
                        priceBlock.appendChild(priceLabel); priceBlock.appendChild(price); purchase.appendChild(priceBlock);
                    }
                    copy.appendChild(purchase); slide.appendChild(copy);
                    var picture = node('div', 'carousel-media');
                    var image = node('img'); image.src = imageSource(row.image_url); image.alt = row.title;
                    image.loading = i === 0 ? 'eager' : 'lazy'; image.decoding = 'async';
                    var fallback = node('span', 'carousel-image-fallback'); fallback.hidden = true;
                    fallback.setAttribute('data-carousel-image-fallback', '');
                    var triedFallback = false;
                    on(image, 'error', function () {
                        if (!triedFallback) { triedFallback = true; image.src = '/static/images/cart/product_normal.png'; }
                        else { image.hidden = true; fallback.hidden = false; }
                    }, true);
                    picture.appendChild(image); picture.appendChild(fallback); slide.appendChild(picture);
                    viewport.appendChild(slide); slides.push(slide); prices.push(price); images.push(image);
                    var dot = node('span', 'carousel-dot');
                    dots.appendChild(dot); indicators.push(dot);
                });
                refresh(); schedule();
            }
            function load() {
                var generation = ++requestId;
                stop(); clearSlides(); state = 'loading'; rows = [];
                announcement.textContent = ''; refresh();
                return (options.fetch || window.fetch)(options.url, {cache: 'no-store'}).then(function (response) {
                    if (!response.ok) throw new Error('carousel-response');
                    return response.json();
                }).then(function (result) {
                    if (destroyed || generation !== requestId) return;
                    if (result.code !== 200 || !Array.isArray(result.data)) throw new Error('carousel-data');
                    var seen = new Set();
                    rows = result.data.filter(function (row) {
                        var id = Number(row && row.skuid);
                        if (!Number.isInteger(id) || id <= 0 || seen.has(id)) return false;
                        seen.add(id); return true;
                    }).slice(0, 6).map(function (row) {
                        return {skuid: Number(row.skuid), title: String(row.title || row.product_name || row.name || ''),
                            intro: String(row.intro || row.caption || ''), image_url: row.image_url,
                            price: row.price != null && row.price !== '' && Number.isFinite(Number(row.price)) ? Number(row.price) : null};
                    });
                    index = 0; state = rows.length ? 'ready' : 'empty'; render();
                }).catch(function () {
                    if (destroyed || generation !== requestId) return;
                    rows = []; state = 'error'; viewport.replaceChildren(); refresh(); stop();
                });
            }
            on(retry, 'click', function (event) { event.preventDefault(); load(); });
            on(root, 'mouseenter', function () { hovered = true; schedule(); });
            on(root, 'mouseleave', function () { hovered = false; schedule(); });
            on(root, 'focusin', function () { focused = true; schedule(); });
            on(root, 'focusout', function (event) { if (!root.contains(event.relatedTarget)) { focused = false; schedule(); } });
            on(root, 'keydown', function (event) {
                if (event.altKey || event.ctrlKey || event.metaKey || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
                event.preventDefault();
                var moveFocus = slides[index] && slides[index].contains(document.activeElement);
                go(index + ((event.key === 'ArrowRight') !== rtl() ? 1 : -1), true);
                if (moveFocus) root.focus({preventScroll: true});
            });
            on(viewport, 'pointerdown', function (event) {
                suppressClick = false;
                if (event.pointerType !== 'mouse') pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
            });
            on(viewport, 'pointerup', function (event) {
                if (!pointer || pointer.id !== event.pointerId) return;
                var dx = event.clientX - pointer.x, dy = event.clientY - pointer.y; pointer = null;
                if (Math.abs(dx) < 48 || Math.abs(dx) <= Math.abs(dy)) return;
                suppressClick = true;
                go(index + ((dx < 0) !== rtl() ? 1 : -1), true);
            });
            on(viewport, 'click', function (event) { if (suppressClick) { event.preventDefault(); suppressClick = false; } });
            on(viewport, 'pointercancel', function () { pointer = null; });
            on(document, 'visibilitychange', schedule);
            on(window, 'pagehide', function () { suspended = true; stop(); });
            on(window, 'pageshow', function () { suspended = false; schedule(); });
            if (media && media.addEventListener) on(media, 'change', function () { paused = media.matches; refresh(); schedule(); });
            var ready = load();
            return {ready: ready, reload: load, refreshPrices: refreshPrices,
                setLanguage: function () { refresh(); },
                destroy: function () {
                    destroyed = true; ++requestId; stop();
                    listeners.concat(slideListeners).forEach(function (remove) { remove(); });
                    listeners = []; slideListeners = [];
                }};
        }
    };
})();
