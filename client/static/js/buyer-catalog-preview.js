/* Homepage discovery: category links and ten balanced picks, never a second catalog. */
(function () {
    'use strict';
    window.BuyerCatalogPreview = {
        start: function (options) {
            var categories = [], ready = false, revision = 0;
            var model = window.BuyerCatalogModel;
            var teaKeys = {'红茶': 'tea_black', '绿茶': 'tea_green', '乌龙茶': 'tea_oolong',
                '黑茶': 'tea_dark', '普洱茶': 'tea_puer', '白茶': 'tea_white', '黄茶': 'tea_yellow', '花茶': 'tea_scented'};
            function text(key) { return options.labels()[key] || key; }
            function updateLabels() {
                options.tabs.querySelectorAll('a').forEach(function (link, index) {
                    var cat = categories[index];
                    link.querySelector('span').textContent = teaKeys[cat.name] ? text(teaKeys[cat.name]) : cat.name;
                });
                options.retry.textContent = text('grid_retry');
            }
            function renderGuides() {
                options.tabs.replaceChildren();
                categories.forEach(function (cat) {
                    var link = document.createElement('a'); link.className = 'tea-guide';
                    link.href = 'buyer_products.html?catalog_id=' + encodeURIComponent(cat.id);
                    var img = document.createElement('img'); img.alt = ''; img.loading = 'lazy';
                    img.src = cat.rows[0] && cat.rows[0].image_url || '/static/images/tea_saas/tea_saas-logo.png';
                    img.onerror = function () { this.onerror = null; this.src = '/static/images/tea_saas/tea_saas-logo.png'; };
                    link.appendChild(img); link.appendChild(document.createElement('span'));
                    options.tabs.appendChild(link);
                });
                updateLabels();
            }
            async function load() {
                var requestRevision = ++revision;
                ready = false; options.error.style.display = 'none'; options.retry.hidden = true;
                options.grid.setAttribute('aria-busy', 'true'); options.grid.replaceChildren(); options.tabs.replaceChildren();
                var skeleton = document.createElement('div'); skeleton.className = 'product-card-skeleton';
                skeleton.textContent = text('grid_loading'); options.grid.appendChild(skeleton);
                options.empty.style.display = 'none';
                try {
                    var response = await fetch(options.url, {cache: 'no-store'});
                    if (!response.ok) throw new Error('catalog-request-failed');
                    var body = await response.json();
                    if (body.code !== 200 || !Array.isArray(body.data)) throw new Error('invalid-catalog-response');
                    if (requestRevision !== revision) return;
                    categories = model.normalize(body.data).filter(function (cat) { return cat.rows.length; });
                    ready = true; renderGuides(); options.render(model.interleave(categories).slice(0, 10));
                } catch (failure) {
                    if (requestRevision !== revision) return;
                    options.tabs.replaceChildren(); options.grid.replaceChildren();
                    options.error.style.display = 'block'; options.retry.hidden = false; updateLabels();
                } finally {
                    if (requestRevision === revision) options.grid.setAttribute('aria-busy', 'false');
                }
            }
            options.retry.addEventListener('click', load); load();
            return {setLanguage: function () { if (ready) updateLabels(); }};
        }
    };
})();
