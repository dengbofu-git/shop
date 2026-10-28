/* Spreadsheet import is a normal merchant service; no Agent/model is involved. */
(function () {
    'use strict';
    var dialog, job = null, busy = false, page = 1, requestKey = null, jobToken = null;
    var pageSize = 25, api = '/v1/goods/merchant/imports';
    function el(id) { return document.getElementById(id); }
    function token() { return window.AuthStorage ? AuthStorage.getToken() : ''; }
    function message(text, error) {
        el('import-message').textContent = text;
        el('import-message').dataset.error = error ? 'true' : 'false';
    }
    function remember(id) {
        var url = new URL(window.location.href);
        if (id) url.searchParams.set('import_job', id); else url.searchParams.delete('import_job');
        window.history.replaceState(null, '', url);
    }
    function ready() {
        return job && jobToken === token() && job.status === 'ready' && !job.expired && !job.needs_reupload && job.error_count === 0;
    }
    function controls() {
        ['import-file', 'import-preview', 'import-close', 'import-reload', 'import-template-xlsx', 'import-template-csv'].forEach(function (id) { el(id).disabled = busy; });
        el('import-commit').disabled = busy || !ready() || !el('import-confirmed').checked;
        el('import-confirmed').disabled = busy || !ready();
        dialog.setAttribute('aria-busy', busy ? 'true' : 'false');
    }
    async function request(path, options, blob) {
        var auth = token();
        if (!auth) throw new Error('请先登录商家账号');
        options = options || {};
        options.headers = Object.assign({}, options.headers, {Authorization: 'Bearer ' + auth.replace(/^Bearer\s+/i, '')});
        options.credentials = 'same-origin';
        options.redirect = 'error';
        options.cache = 'no-store';
        var controller = new AbortController();
        options.signal = controller.signal;
        var timer = window.setTimeout(function () { controller.abort(); }, 45000);
        try {
            var response = await fetch(api + path, options);
            if (token() !== auth) throw new Error('账号已变化，请重新打开导入');
            if (blob && response.ok) {
                var file = await response.blob();
                if (token() !== auth) throw new Error('账号已变化，请重新打开导入');
                return file;
            }
            var body;
            try { body = await response.json(); } catch (_) { throw new Error('导入服务响应异常，请联系管理员'); }
            if (token() !== auth) throw new Error('账号已变化，请重新打开导入');
            if (!response.ok || body.code !== 200) throw new Error(body.error || '商品导入服务暂不可用');
            return body.data;
        } catch (error) {
            if (error.name === 'AbortError') throw new Error('请求超时，结果尚未确认；请重新加载任务后再操作');
            throw error;
        } finally { window.clearTimeout(timer); }
    }
    function showRows() {
        var rows = job.rows.filter(function (row) { return !el('import-errors-only').checked || row.errors.length; });
        var pages = Math.max(1, Math.ceil(rows.length / pageSize));
        page = Math.min(page, pages);
        var body = el('import-rows');
        body.replaceChildren();
        rows.slice((page - 1) * pageSize, page * pageSize).forEach(function (row) {
            var tr = document.createElement('tr'), data = row.data;
            if (row.errors.length) tr.className = 'import-row-error';
            [row.row_number, data.name, data.sku_name, data.catalog + (data.brand ? ' / ' + data.brand : ''),
                data.price + ' / ' + data.market_price, data.stock,
                data.caption || '—', row.errors.join('；') || '通过 · 未上架'].forEach(function (value) {
                var td = document.createElement('td');
                td.textContent = String(value);
                tr.appendChild(td);
            });
            body.appendChild(tr);
        });
        if (!rows.length) {
            var tr = document.createElement('tr'), td = document.createElement('td');
            td.colSpan = 8; td.textContent = '没有错误行'; tr.appendChild(td); body.appendChild(tr);
        }
        el('import-page').textContent = '第 ' + page + ' / ' + pages + ' 页 · 当前筛选 ' + rows.length + ' 行';
        el('import-prev').disabled = page <= 1;
        el('import-next').disabled = page >= pages;
    }
    function render(value) {
        var valid = value && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value.id) &&
            /^[0-9a-f]{64}$/i.test(value.review_digest) && typeof value.filename === 'string' &&
            Array.isArray(value.rows) && value.rows.length > 0 && value.rows.length <= 500 &&
            ['ready', 'invalid', 'committed'].indexOf(value.status) >= 0;
        if (valid) {
            valid = value.row_count === value.rows.length && value.rows.every(function (row) {
                return row && Number.isInteger(row.row_number) && row.data && Array.isArray(row.errors) &&
                    row.errors.every(function (error) { return typeof error === 'string'; }) &&
                    ['name', 'sku_name', 'catalog', 'brand', 'caption', 'price', 'market_price'].every(function (key) { return typeof row.data[key] === 'string'; }) &&
                    (typeof row.data.stock === 'string' || Number.isInteger(row.data.stock));
            }) && value.error_count === value.rows.filter(function (row) { return row.errors.length; }).length &&
                value.valid_count === value.row_count - value.error_count;
        }
        if (!valid) {
            job = null; el('import-review').hidden = true; remember(null);
            throw new Error('导入预览格式异常，请重新上传或联系管理员');
        }
        job = value; jobToken = token(); page = 1;
        el('import-review').hidden = false;
        el('import-confirmed').checked = false;
        el('import-errors-only').checked = false;
        el('import-summary').textContent = job.filename + ' · 共 ' + job.row_count + ' 行，通过 ' + job.valid_count + ' 行，错误 ' + job.error_count + ' 行';
        el('import-view-products').hidden = job.status !== 'committed';
        if (job.status === 'committed') message('导入成功：新增 ' + job.result.spu_count + ' 个商品、' + job.result.sku_count + ' 个规格，均为未上架。重复确认不会再次创建。');
        else if (job.needs_reupload) message('商品导入模板已更新，请下载新模板并重新上传。', true);
        else if (job.expired) message('预览已过期，请重新上传文件校验。', true);
        else if (job.error_count) message('请修改标记的错误行后重新上传；本批尚未创建商品。', true);
        else message('校验通过。请核对明细，勾选确认后导入为未上架商品。');
        remember(job.id); showRows(); controls();
    }
    async function run(action) {
        if (busy) return;
        busy = true; controls();
        try { await action(); } catch (error) {
            if (jobToken && jobToken !== token()) {
                job = null; el('import-review').hidden = true; remember(null);
            }
            message(error.message || '操作失败，请重试', true);
        } finally { busy = false; controls(); }
    }
    function newKey() {
        if (window.crypto.randomUUID) return window.crypto.randomUUID();
        var bytes = window.crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
        return Array.from(bytes, function (b, i) { return ([4, 6, 8, 10].indexOf(i) >= 0 ? '-' : '') + b.toString(16).padStart(2, '0'); }).join('');
    }
    async function upload() {
        var file = el('import-file').files[0];
        if (!file || !/\.(xlsx|csv)$/i.test(file.name)) throw new Error('请选择 XLSX 或 CSV 文件');
        if (!file.size || file.size > 5 * 1024 * 1024) throw new Error('文件不能为空，且不得超过 5 MB');
        requestKey = requestKey || newKey();
        var form = new FormData(); form.append('file', file); form.append('request_key', requestKey);
        message('正在上传并校验，尚未创建商品…');
        render(await request('', {method: 'POST', body: form}));
        requestKey = null;
    }
    async function reload() {
        var id = job ? job.id : new URL(window.location.href).searchParams.get('import_job');
        if (id && /^[0-9a-f-]{36}$/i.test(id)) render(await request('/' + id));
    }
    async function download(kind) {
        var blob = await request('/template?format=' + kind, {}, true);
        var url = URL.createObjectURL(blob), anchor = document.createElement('a');
        anchor.href = url; anchor.download = '商品导入模板.' + kind;
        document.body.appendChild(anchor); anchor.click(); anchor.remove();
        window.setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    }
    document.addEventListener('DOMContentLoaded', function () {
        dialog = el('product-import-dialog');
        if (!dialog || !el('btn-product-import')) return;
        el('btn-product-import').addEventListener('click', function () {
            if (jobToken && jobToken !== token()) { job = null; el('import-review').hidden = true; remember(null); }
            dialog.showModal(); controls();
        });
        el('import-close').addEventListener('click', function () { if (!busy) dialog.close(); });
        dialog.addEventListener('cancel', function (event) { if (busy) event.preventDefault(); });
        el('import-file').addEventListener('change', function () {
            job = null; jobToken = null; requestKey = null; remember(null);
            el('import-review').hidden = true; el('import-view-products').hidden = true;
            message('文件已选择，请点击上传并校验。'); controls();
        });
        el('import-preview').addEventListener('click', function () { run(upload); });
        el('import-reload').addEventListener('click', function () { run(reload); });
        ['xlsx', 'csv'].forEach(function (kind) { el('import-template-' + kind).addEventListener('click', function () { run(function () { return download(kind); }); }); });
        el('import-confirmed').addEventListener('change', controls);
        el('import-errors-only').addEventListener('change', function () { page = 1; showRows(); });
        el('import-prev').addEventListener('click', function () { page--; showRows(); });
        el('import-next').addEventListener('click', function () { page++; showRows(); });
        el('import-commit').addEventListener('click', function () {
            if (!ready() || !el('import-confirmed').checked) return;
            run(async function () {
                message('正在导入，请勿关闭或切换账号…');
                render(await request('/' + job.id + '/commit', {method: 'POST',
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({review_digest: job.review_digest})}));
            });
        });
        if (new URL(window.location.href).searchParams.get('import_job') && new URL(window.location.href).searchParams.get('mode') === 'create') {
            dialog.showModal(); run(reload);
        }
    });
})();
