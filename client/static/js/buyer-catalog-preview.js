/** Database-backed tea categories for the buyer homepage. */
(function () {
    'use strict';
    window.BuyerCatalogPreview = {
        start: function (options) {
            var categories = [], allRows = [], selected = 'all', currentPage = 1, revision = 0, ready = false;
            var tabs = options.tabs, grid = options.grid, summary = options.summary;
            var error = options.error, retry = options.retry, viewAll = options.viewAll;
            var pager = options.pager, pageSize = 10;
            var teaKeys = {'红茶': 'tea_black', '绿茶': 'tea_green', '乌龙茶': 'tea_oolong',
                '黑茶': 'tea_dark', '普洱茶': 'tea_puer', '白茶': 'tea_white', '黄茶': 'tea_yellow', '花茶': 'tea_scented'};
            function text(key) { return options.labels()[key] || key; }
            function label(category) { return teaKeys[category.name] ? text(teaKeys[category.name]) : category.name; }
            function interleaveRows() {
                // Keep every SKU in a stable interleaved order, then paginate.
                var rows = [], seen = new Set(), index = 0;
                while (true) {
                    var found = false;
                    categories.forEach(function (cat) {
                        var row = cat.rows[index];
                        if (row) {
                            found = true;
                            if (!seen.has(String(row.skuid))) { rows.push(row); seen.add(String(row.skuid)); }
                        }
                    });
                    if (!found) break;
                    index++;
                }
                return rows;
            }
            function pageResult() {
                var category = categories.find(function (cat) { return cat.id === selected; });
                var rows = category ? category.rows : allRows;
                var pages = Math.max(1, Math.ceil(rows.length / pageSize));
                currentPage = Math.max(1, Math.min(currentPage, pages));
                var offset = (currentPage - 1) * pageSize;
                return {rows: rows.slice(offset, offset + pageSize), total: rows.length, pages: pages,
                    start: rows.length ? offset + 1 : 0, end: Math.min(offset + pageSize, rows.length)};
            }
            function changePage(page) {
                if (!ready || page === currentPage || page < 1 || page > pageResult().pages) return;
                currentPage = page;
                renderSelection();
                var current = Array.from(pager.querySelectorAll('button')).find(function (button) {
                    return button.dataset.kind === 'number' && Number(button.dataset.page) === currentPage;
                });
                if (current) current.focus({preventScroll: true});
                if (options.section) options.section.scrollIntoView({block: 'start'});
            }
            function renderPager(result) {
                pager.replaceChildren(); pager.hidden = !result.total;
                pager.setAttribute('aria-label', text('grid_pagination'));
                if (!result.total) return;
                function button(label, target, kind, disabled) {
                    var control = document.createElement('button');
                    control.type = 'button'; control.className = 'featured-page-button';
                    control.textContent = label; control.dataset.page = String(target); control.dataset.kind = kind;
                    control.disabled = !!disabled; control.setAttribute('aria-controls', 'product-grid');
                    if (kind === 'number' && target === currentPage) {
                        control.classList.toggle('active', true); control.setAttribute('aria-current', 'page');
                    }
                    control.addEventListener('click', function () { changePage(target); });
                    pager.appendChild(control);
                }
                button(text('grid_prev'), currentPage - 1, 'previous', currentPage === 1);
                var numbers = new Set([1, result.pages]);
                for (var page = Math.max(1, currentPage - 2); page <= Math.min(result.pages, currentPage + 2); page++) numbers.add(page);
                var previous = 0;
                Array.from(numbers).sort(function (a, b) { return a - b; }).forEach(function (number) {
                    if (previous && number > previous + 1) {
                        var ellipsis = document.createElement('span'); ellipsis.textContent = '…';
                        ellipsis.setAttribute('aria-hidden', 'true'); pager.appendChild(ellipsis);
                    }
                    button(String(number), number, 'number', false); previous = number;
                });
                button(text('grid_next'), currentPage + 1, 'next', currentPage === result.pages);
            }
            function updateLabels() {
                tabs.querySelectorAll('button').forEach(function (button) {
                    var cat = categories.find(function (entry) { return entry.id === button.dataset.catalogId; });
                    var count = cat ? cat.rows.length : allRows.length;
                    button.textContent = (cat ? label(cat) : text('tea_all')) + ' (' + count + ')';
                    var active = button.dataset.catalogId === selected;
                    button.classList.toggle('active', active);
                    button.setAttribute('aria-pressed', String(active));
                });
                retry.textContent = text('grid_retry');
                if (ready) {
                    var result = pageResult();
                    summary.textContent = text('grid_summary').replace('{start}', result.start).replace('{end}', result.end).replace('{total}', result.total);
                    renderPager(result);
                }
            }
            function select(id) {
                selected = id; currentPage = 1;
                renderSelection();
            }
            function renderSelection() {
                options.render(pageResult().rows);
                viewAll.href = 'buyer_products.html' + (selected === 'all' ? '' : '?catalog_id=' + encodeURIComponent(selected));
                updateLabels();
            }
            function renderTabs() {
                tabs.replaceChildren();
                [{id: 'all'}].concat(categories).forEach(function (cat) {
                    var button = document.createElement('button');
                    button.type = 'button'; button.className = 'tea-tab';
                    button.dataset.catalogId = cat.id;
                    button.setAttribute('aria-controls', 'product-grid');
                    button.addEventListener('click', function () { select(cat.id); });
                    tabs.appendChild(button);
                });
            }
            async function load() {
                var requestRevision = ++revision;
                ready = false; error.style.display = 'none'; retry.hidden = true;
                pager.hidden = true; pager.replaceChildren();
                grid.setAttribute('aria-busy', 'true'); grid.replaceChildren();
                var skeleton = document.createElement('div');
                skeleton.className = 'product-card-skeleton'; skeleton.textContent = text('grid_loading');
                grid.appendChild(skeleton); summary.textContent = text('grid_loading');
                options.empty.style.display = 'none';
                try {
                    var response = await fetch(options.url, {cache: 'no-store'});
                    if (!response.ok) throw new Error('catalog-request-failed');
                    var body = await response.json();
                    if (body.code !== 200 || !Array.isArray(body.data)) throw new Error('invalid-catalog-response');
                    if (requestRevision !== revision) return;
                    categories = body.data.filter(function (cat) {
                        return Number.isInteger(Number(cat.catalog_id)) && Number(cat.catalog_id) > 0 && Array.isArray(cat.sku);
                    }).map(function (cat) {
                        var seen = new Set();
                        var rows = cat.sku.filter(function (row) {
                            if (!row.skuid || seen.has(String(row.skuid))) return false;
                            seen.add(String(row.skuid)); return true;
                        }).map(function (row) {
                            return Object.assign({}, row, {catalog_id: cat.catalog_id, catalog_name: cat.catalog_name});
                        }).sort(function (a, b) { return Number(b.skuid) - Number(a.skuid); });
                        return {id: String(cat.catalog_id), name: String(cat.catalog_name || ''), rows: rows};
                    });
                    allRows = interleaveRows();
                    if (selected !== 'all' && !categories.some(function (cat) { return cat.id === selected; })) { selected = 'all'; currentPage = 1; }
                    ready = true; renderTabs(); renderSelection();
                } catch (failure) {
                    if (requestRevision !== revision) return;
                    tabs.replaceChildren(); grid.replaceChildren();
                    summary.textContent = ''; error.style.display = 'block'; retry.hidden = false;
                    retry.textContent = text('grid_retry');
                } finally {
                    if (requestRevision === revision) grid.setAttribute('aria-busy', 'false');
                }
            }
            retry.addEventListener('click', load);
            load();
            return {setLanguage: updateLabels};
        }
    };
})();
