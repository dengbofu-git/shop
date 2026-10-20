(function () {
    'use strict';
    var $ = function (id) { return document.getElementById(id); };
    var fields = {name: 'sm-name', summary: 'sm-summary', welcome: 'sm-welcome', story: 'sm-story'};
    var revision = 0, draft = null, saved = '', owned = [], busy = false, loaded = false;
    var published = false, unpublished = false;
    if (new URLSearchParams(location.search).get('embed') === '1') document.body.classList.add('store-embedded');
    async function api(path, method, data) {
        var token = AuthStorage.getToken();
        if (!token) throw new Error('请先登录商家账号。');
        var multipart = data instanceof FormData;
        var response = await fetch(path, {method: method || 'GET', cache: 'no-store',
            headers: Object.assign({Authorization: 'Bearer ' + token}, multipart ? {} : {'Content-Type': 'application/json'}),
            body: data === undefined ? undefined : multipart ? data : JSON.stringify(data)});
        var result;
        try { result = await response.json(); }
        catch (error) { throw new Error('服务暂时不可用，请稍后重试。'); }
        if (!response.ok || result.code !== 200) throw new Error(result.error || '请求失败，请稍后重试。');
        return result.data;
    }
    function message(value, bad) { $('sm-message').textContent = value; $('sm-message').classList.toggle('is-error', !!bad); }
    function lock(value) {
        busy = value;
        ['sm-save', 'sm-preview', 'sm-publish'].forEach(function (id) { $(id).disabled = value || !loaded; });
        $('sm-unpublish').disabled = value || !loaded || !published;
        $('sm-reload').disabled = value;
        $('sm-form').querySelectorAll('input,textarea,select,button').forEach(function (el) {
            var edge = el.dataset.action === 'up' && Number(el.dataset.index) === 0 ||
                el.dataset.action === 'down' && draft && Number(el.dataset.index) === draft.featured_ids.length - 1;
            el.disabled = value || !!edge;
        });
        renderProductSearch();
    }
    function content() {
        var result = Object.assign({}, draft);
        Object.keys(fields).forEach(function (key) { result[key] = $(fields[key]).value.trim(); });
        result.featured_ids = draft.featured_ids.slice();
        return result;
    }
    function dirty() { return loaded && JSON.stringify(content()) !== saved; }
    function renderPreview() {
        if (!draft) return;
        var value = content();
        Storefront.hero($('sm-preview-hero'), value);
        var selected = value.featured_ids.map(function (id) { return owned.find(function (row) { return row.skuid === id; }); }).filter(function (row) { return row && row.is_launched && row.stock > 0; });
        Storefront.cards($('sm-preview-products'), selected, true);
        $('sm-preview-story').textContent = value.story || '在这里介绍你的茶园、品牌故事与选茶理念。';
        $('sm-state').textContent = (published ? '已发布' : '未发布') +
            (dirty() ? ' · 有未保存修改' : unpublished ? ' · 草稿尚未发布' : '');
    }
    function renderSelected() {
        $('sm-selected').replaceChildren();
        draft.featured_ids.forEach(function (id, index) {
            var row = owned.find(function (item) { return item.skuid === id; });
            var line = document.createElement('div'); line.className = 'store-selected-product';
            var name = document.createElement('span'); name.textContent = (index + 1) + '. ' + (row ? row.product_name + ' · ' + row.name + (!row.is_launched || row.stock <= 0 ? '（暂不展示）' : '') : '商品 #' + id + '（已不可用，请移除）');
            line.appendChild(name);
            [['up', '上移', index === 0], ['down', '下移', index === draft.featured_ids.length - 1], ['remove', '移除', false]].forEach(function (action) {
                var button = document.createElement('button'); button.type = 'button'; button.textContent = action[1];
                button.disabled = action[2]; button.dataset.action = action[0]; button.dataset.index = index; line.appendChild(button);
            });
            $('sm-selected').appendChild(line);
        });
        renderPreview();
        renderProductSearch();
    }
    function renderProductSearch() {
        var query = $('sm-product-search').value.trim().toLocaleLowerCase();
        var results = $('sm-product-results');
        results.replaceChildren();
        results.hidden = !query;
        if (!query) { $('sm-search-message').textContent = '输入商品名称或规格，搜索后点击“添加”即可推荐。'; return; }
        var words = query.split(/\s+/);
        var matches = owned.filter(function (row) {
            var value = [row.product_name, row.name, row.caption].join(' ').toLocaleLowerCase();
            return words.every(function (word) { return value.includes(word); });
        });
        $('sm-search-message').textContent = !matches.length ? '没有找到匹配的本店商品，请更换关键词。' :
            '找到 ' + matches.length + ' 件商品' + (matches.length > 6 ? '，显示前 6 件，请细化关键词。' : '。');
        if (draft && draft.featured_ids.length >= 8) $('sm-search-message').textContent += ' 推荐已满 8 件，请先移除后再添加。';
        matches.slice(0, 6).forEach(function (row) {
            var line = document.createElement('div'); line.className = 'store-search-result';
            var copy = document.createElement('div'); copy.className = 'store-search-result-copy';
            var title = document.createElement('strong'); title.textContent = row.product_name;
            var spec = document.createElement('span'); spec.textContent = row.name +
                (!row.is_launched ? ' · 已下架，暂不展示' : row.stock <= 0 ? ' · 无库存，暂不展示' : '');
            copy.append(title, spec);
            var picked = draft && draft.featured_ids.includes(row.skuid);
            var add = document.createElement('button'); add.type = 'button';
            add.textContent = picked ? '已添加' : '添加'; add.dataset.productId = row.skuid;
            add.setAttribute('aria-label', (picked ? '已添加 ' : '添加 ') + row.product_name + ' ' + row.name);
            add.disabled = busy || picked || !draft || draft.featured_ids.length >= 8;
            line.append(copy, add); results.appendChild(line);
        });
    }
    function accept(data, fill) {
        revision = data.revision; draft = data.draft; published = data.is_published;
        unpublished = data.has_unpublished_changes;
        saved = JSON.stringify(draft);
        if (fill) Object.keys(fields).forEach(function (key) { $(fields[key]).value = draft[key] || ''; });
        $('sm-public').href = data.public_url; $('sm-public').hidden = !published;
        $('sm-published-at').textContent = data.published_at ? '最近发布：' + new Date(data.published_at).toLocaleString() : data.is_published ? '公开页面已上线' : '尚无公开页面';
        renderSelected();
    }
    async function loadProducts() {
        $('sm-products-retry').hidden = true;
        try {
            var groups = await api('/v1/goods/merchant/products');
            owned = groups.flatMap(function (group) { return group.skus.map(function (sku) { return Object.assign({}, sku, {skuid: sku.sku_id, product_name: group.name}); }); });
            $('sm-products-message').textContent = owned.length ? '已加载 ' + owned.length + ' 件本店商品' : '本店还没有商品，请先到“商品管理”添加。';
        } catch (error) {
            $('sm-products-message').textContent = error.message; $('sm-products-retry').hidden = false;
        }
        if (draft) renderSelected();
    }
    async function load() {
        if (busy) return;
        lock(true); message('正在加载店铺资料…');
        try {
            var data = await api('/v1/supplier/store-page'); loaded = true;
            $('sm-form').hidden = false; accept(data, true); await loadProducts(); message('');
        } catch (error) { message(error.message, true); }
        finally { lock(false); }
    }
    async function save() {
        var data = await api('/v1/supplier/store-page', 'PUT', {revision: revision, content: content()});
        accept(data, true);
    }
    async function action(kind) {
        if (busy || !loaded) return;
        if (kind === 'unpublish' && dirty()) { message('下线前请先保存草稿，避免丢失未保存内容。', true); return; }
        if (kind === 'publish' && !$('sm-name').value.trim()) { $('sm-name').focus(); message('发布前请填写店铺名称。', true); return; }
        lock(true); message(kind === 'save' ? '正在保存草稿…' : kind === 'publish' ? '正在发布…' : '正在下线主页…');
        try {
            if (kind === 'save' || (kind === 'publish' && dirty())) await save();
            if (kind !== 'save') accept(await api('/v1/supplier/store-page', 'POST', {revision: revision, action: kind}), true);
            message(kind === 'save' ? '草稿已保存，公开页面尚未更新。' : kind === 'publish' ? '店铺已发布，买家现在可以通过店铺详情访问。' : '店铺主页已下线，商品上下架状态不变。');
        } catch (error) { message(error.message, true); }
        finally { lock(false); }
    }
    $('sm-form').addEventListener('submit', function (event) { event.preventDefault(); });
    $('sm-form').addEventListener('input', renderPreview);
    $('sm-reload').addEventListener('click', function () { if (!dirty() || confirm('重新加载将丢弃未保存的修改，继续吗？')) load(); });
    $('sm-save').addEventListener('click', function () { action('save'); });
    $('sm-publish').addEventListener('click', function () { action('publish'); });
    $('sm-unpublish').addEventListener('click', function () { action('unpublish'); });
    $('sm-products-retry').addEventListener('click', loadProducts);
    $('sm-product-search').addEventListener('input', renderProductSearch);
    $('sm-product-search').addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { this.value = ''; renderProductSearch(); event.preventDefault(); }
        if (event.key === 'Enter') { renderProductSearch(); event.preventDefault(); }
    });
    $('sm-product-results').addEventListener('click', function (event) {
        var button = event.target.closest('button[data-product-id]');
        if (!button || busy || !draft || button.disabled) return;
        var id = Number(button.dataset.productId);
        if (!owned.some(function (row) { return row.skuid === id; })) return;
        if (draft.featured_ids.includes(id)) { message('该商品已在推荐列表中。', true); return; }
        if (draft.featured_ids.length >= 8) { message('最多选择 8 件推荐商品。', true); return; }
        draft.featured_ids.push(id); renderSelected();
    });
    $('sm-selected').addEventListener('click', function (event) {
        var button = event.target.closest('button'); if (!button) return;
        var index = Number(button.dataset.index), ids = draft.featured_ids;
        if (button.dataset.action === 'remove') ids.splice(index, 1);
        else { var next = index + (button.dataset.action === 'up' ? -1 : 1); if (next < 0 || next >= ids.length) return; var old = ids[index]; ids[index] = ids[next]; ids[next] = old; }
        renderSelected();
    });
    ['logo', 'banner'].forEach(function (kind) {
        $('sm-' + kind).addEventListener('change', async function () {
            var file = this.files[0]; if (!file) return;
            if (file.size > (kind === 'logo' ? 4 : 8) * 1024 * 1024) { this.value = ''; message('Logo 最大 4MB，横幅最大 8MB。', true); return; }
            lock(true); message('正在上传图片…');
            try {
                var form = new FormData(); form.append('image', file); form.append('kind', kind);
                var data = await api('/v1/supplier/store-page/image', 'POST', form);
                draft[kind + '_url'] = data.url; renderPreview(); message('图片已上传，请保存草稿或发布更新。');
            } catch (error) { message(error.message, true); }
            finally { this.value = ''; lock(false); }
        });
    });
    document.querySelectorAll('[data-clear-image]').forEach(function (button) { button.addEventListener('click', function () { draft[button.dataset.clearImage] = ''; renderPreview(); }); });
    document.querySelectorAll('[data-preview-size]').forEach(function (button) { button.addEventListener('click', function () {
        $('sm-preview-window').classList.toggle('is-mobile', button.dataset.previewSize === 'mobile');
        document.querySelectorAll('[data-preview-size]').forEach(function (item) { item.setAttribute('aria-pressed', String(item === button)); });
    }); });
    $('sm-preview').addEventListener('click', function () {
        renderPreview(); $('sm-dialog-content').replaceChildren($('sm-preview-window').cloneNode(true));
        $('sm-dialog-content').querySelectorAll('[id]').forEach(function (node) { node.removeAttribute('id'); });
        $('sm-dialog').showModal();
    });
    $('sm-close-preview').addEventListener('click', function () { $('sm-dialog').close(); });
    window.addEventListener('beforeunload', function (event) { if (dirty()) { event.preventDefault(); event.returnValue = ''; } });
    load();
}());
