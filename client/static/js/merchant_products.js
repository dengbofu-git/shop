/**
 * 商家商品管理 - 单页复用（列表 / 编辑）
 * 真实对接数据库：列表与编辑均以接口为准
 */
(function() {
  'use strict';

  // 真实对接数据库：列表与编辑均以数据库接口为唯一数据源

  var state = { list: [], page: 1, pageSize: 5, filters: { q: '', status: 'all', cat1: 'all' }, selected: new Set() };
  var currentSku = null;

  function getQuery() { return new URLSearchParams(window.location.search || ''); }

  function setMode(mode, extra) {
    var qs = new URLSearchParams();
    qs.set('mode', mode);
    if (extra) Object.keys(extra).forEach(function(k) {
      if (extra[k] != null && String(extra[k]).length) qs.set(k, extra[k]);
    });
    window.location.search = '?' + qs.toString();
  }

  function getStockLabel(stock) {
    if (stock === 0) return { text: '库存无', cls: 'tag-red' };
    if (stock <= 100) return { text: '库存紧张', cls: 'tag-blue' };
    return { text: '库存充足', cls: 'tag-ok' };
  }

  function getLaunchLabel(isLaunched) {
    return isLaunched ? { text: '上架', cls: 'tag-ok' } : { text: '下架', cls: 'tag-red' };
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function(c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function _getBaseUrl() {
    if (typeof baseUrl !== 'undefined' && baseUrl) return baseUrl;
    return '';
  }

  function fetchMyProductsFromDb() {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (typeof AuthStorage === 'undefined' || !AuthStorage.getToken()) return reject(new Error('未登录'));

      $.ajax({
        type: 'GET',
        url: _getBaseUrl() + '/v1/goods/merchant/products',
        headers: { 'Authorization': AuthStorage.getToken() },
        success: function(r) {
          if (!r || r.code !== 200) return reject(new Error((r && r.error) ? r.error : '获取商品失败'));
          resolve(r.data || []);
        },
        error: function(xhr) {
          var msg = '网络错误，获取商品失败';
          try {
            if (xhr && xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
          } catch (_) {}
          reject(new Error(msg));
        }
      });
    });
  }

  function deleteSkuFromDb(skuId) {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (!skuId) return reject(new Error('未找到该商品'));
      if (typeof AuthStorage === 'undefined' || !AuthStorage.getToken()) return reject(new Error('未登录'));

      $.ajax({
        type: 'DELETE',
        url: _getBaseUrl() + '/v1/goods/merchant/sku/' + encodeURIComponent(String(skuId)),
        headers: { 'Authorization': AuthStorage.getToken() },
        success: function(r) {
          if (r && r.code === 200) return resolve(true);
          reject(new Error((r && r.error) ? r.error : '删除失败'));
        },
        error: function(xhr) {
          var msg = '网络错误，删除失败';
          try {
            if (xhr && xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error;
          } catch (_) {}
          reject(new Error(msg));
        }
      });
    });
  }

  function createSpuToDb(payload) {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (typeof AuthStorage === 'undefined' || !AuthStorage.getToken()) return reject(new Error('未登录'));
      $.ajax({
        type: 'POST',
        url: _getBaseUrl() + '/v1/goods/merchant/spu/create',
        headers: { 'Authorization': AuthStorage.getToken(), 'Content-Type': 'application/json' },
        data: JSON.stringify(payload || {}),
        success: function(r) {
          if (r && r.code === 200) return resolve(r.data);
          reject(new Error((r && r.error) ? r.error : '创建商品失败'));
        },
        error: function(xhr) {
          var msg = '网络错误，创建商品失败';
          try { if (xhr && xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error; } catch (_) {}
          reject(new Error(msg));
        }
      });
    });
  }

  function createSkuToDb(payload) {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (typeof AuthStorage === 'undefined' || !AuthStorage.getToken()) return reject(new Error('未登录'));
      $.ajax({
        type: 'POST',
        url: _getBaseUrl() + '/v1/goods/merchant/sku/create',
        headers: { 'Authorization': AuthStorage.getToken(), 'Content-Type': 'application/json' },
        data: JSON.stringify(payload || {}),
        success: function(r) {
          if (r && r.code === 200) return resolve(r.data);
          reject(new Error((r && r.error) ? r.error : '创建商品失败'));
        },
        error: function(xhr) {
          var msg = '网络错误，创建商品失败';
          try { if (xhr && xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error; } catch (_) {}
          reject(new Error(msg));
        }
      });
    });
  }

  function updateSkuStatusToDb(skuId, isLaunched) {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (!skuId) return reject(new Error('未找到该商品'));
      if (typeof AuthStorage === 'undefined' || !AuthStorage.getToken()) return reject(new Error('未登录'));
      $.ajax({
        type: 'PUT',
        url: _getBaseUrl() + '/v1/goods/merchant/sku/' + encodeURIComponent(String(skuId)) + '/status',
        headers: { 'Authorization': AuthStorage.getToken(), 'Content-Type': 'application/json' },
        data: JSON.stringify({ is_launched: !!isLaunched }),
        success: function(r) {
          if (r && r.code === 200) return resolve(r.data || {});
          reject(new Error((r && r.error) ? r.error : '更新失败'));
        },
        error: function(xhr) {
          var msg = '网络错误，更新失败';
          try { if (xhr && xhr.responseJSON && xhr.responseJSON.error) msg = xhr.responseJSON.error; } catch (_) {}
          reject(new Error(msg));
        }
      });
    });
  }

  function fillCatalogSelect(selectId, catalogs, selectedName) {
    var sel = byId(selectId);
    if (!sel) return;
    sel.innerHTML = '';
    sel.add(new Option('请选择茶叶品种', ''));
    (catalogs || []).forEach(function(c) {
      var opt = document.createElement('option');
      opt.value = c.name;
      opt.textContent = c.name;
      sel.appendChild(opt);
    });
    if (selectedName) sel.value = selectedName;
  }

  function initCreate() {
    var err = byId('create-err');
    function setErr(msg) { if (err) err.textContent = msg || ''; }

    function refreshCreateImagePreview() {
      var inp = byId('c-image');
      var img = byId('c-img-preview');
      if (!img || !inp) return;
      var f = inp.files && inp.files[0];
      if (!f) {
        img.src = '/static/images/cart/product_normal.png';
        return;
      }
      setErr('');
      // 使用 Data URL 预览，避免部分环境下 blob: 无法在 <img> 中展示的问题
      var reader = new FileReader();
      reader.onload = function(ev) {
        var result = ev && ev.target && ev.target.result;
        if (typeof result === 'string') img.src = result;
      };
      reader.onerror = function() {
        setErr('本地预览失败（文件可能无法读取），仍可尝试提交上传');
      };
      reader.readAsDataURL(f);
    }

    var cImageInput = byId('c-image');
    if (cImageInput) {
      cImageInput.addEventListener('change', refreshCreateImagePreview);
      cImageInput.addEventListener('input', refreshCreateImagePreview);
    }

    fetchBrandsAndCatalogs().then(function(catalogs) {
      fillCatalogSelect('c-catalog', catalogs);
    }).catch(function(e) {
      setErr(e && e.message ? e.message : '获取分类失败');
    });

    var reset = byId('btn-create-reset');
    if (reset) reset.addEventListener('click', function() {
      setErr('');
      if (byId('c-catalog')) byId('c-catalog').value = '';
      if (byId('c-spu-name')) byId('c-spu-name').value = '';
      if (byId('c-introduction')) byId('c-introduction').value = '';
      if (byId('c-brand')) byId('c-brand').value = '';
      if (byId('c-price')) byId('c-price').value = 0;
      if (byId('c-stock')) byId('c-stock').value = 0;
      if (byId('c-launched')) byId('c-launched').value = 'true';
      if (byId('c-image')) byId('c-image').value = '';
      refreshCreateImagePreview();
    });

    var submit = byId('btn-create-submit');
    if (submit) submit.addEventListener('click', function() {
      setErr('');
      var spuName = (byId('c-spu-name') && byId('c-spu-name').value || '').trim();
      var introduction = (byId('c-introduction') && byId('c-introduction').value || '').trim();
      var catalog = byId('c-catalog') && byId('c-catalog').value;
      var brand = (byId('c-brand') && byId('c-brand').value || '').trim();
      var price = parseFloat((byId('c-price') && byId('c-price').value) || '0') || 0;
      var stock = parseInt((byId('c-stock') && byId('c-stock').value) || '0', 10) || 0;
      var isLaunched = ((byId('c-launched') && byId('c-launched').value) === 'true');

      if (!catalog) return setErr('请选择所属分类');
      if (!spuName) return setErr('请填写商品名称');

      var imgFile = (byId('c-image') && byId('c-image').files) ? byId('c-image').files[0] : null;
      if (imgFile && imgFile.type && imgFile.type.indexOf('image/') !== 0) {
        return setErr('请选择图片文件（jpg/png/webp 等）');
      }

      submit.disabled = true;
      var oldText = submit.textContent;
      submit.textContent = '创建中...';
      createSpuToDb({ name: spuName, catalog: catalog, brand: brand }).then(function(spu) {
        if (!spu || !spu.spu_id) throw new Error('创建商品失败');
        return createSkuToDb({ spu_id: spu.spu_id, name: spuName, caption: introduction, price: price, stock: stock, is_launched: isLaunched });
      }).then(function(sku) {
        if (!sku || !sku.sku_id) throw new Error('创建商品失败');
        return uploadSkuImageToDb(sku.sku_id, imgFile).then(function() { return sku; });
      }).then(function(sku) {
        setMode('edit', { product: sku.sku_id });
      }).catch(function(e) {
        setErr(e && e.message ? e.message : '创建失败');
      }).finally(function() {
        submit.disabled = false;
        submit.textContent = oldText;
      });
    });
  }

  function flattenProducts(apiProducts) {
    // API: [{spu_id,name,brand,catalog,skus:[{sku_id,name,caption,price,stock,is_launched,image}]}]
    var rows = [];
    (apiProducts || []).forEach(function(spu) {
      var catalog = (spu && spu.catalog) ? String(spu.catalog) : '-';
      var spuName = (spu && spu.name) ? String(spu.name) : '';
      var spuId = spu && spu.spu_id;
      var brand = (spu && spu.brand) ? String(spu.brand) : '';
      var skus = (spu && spu.skus) ? spu.skus : [];
      skus.forEach(function(sku) {
        var skuId = sku && (sku.sku_id != null ? sku.sku_id : '');
        rows.push({
          sku_id: skuId,
          spu_id: spuId,
          spu_name: spuName,
          brand: brand,
          nameZh: spuName || (sku && sku.name ? String(sku.name) : ''),
          cat1: catalog,
          priceUsd: parseFloat(sku && sku.price ? sku.price : '0') || 0,
          stock: parseInt(sku && sku.stock != null ? sku.stock : 0, 10) || 0,
          safe: 100,
          createdAt: '-',
          image: (sku && sku.image) ? String(sku.image) : '/static/images/cart/product_normal.png',
          caption: (sku && sku.caption) ? String(sku.caption) : '',
          is_launched: !!(sku && sku.is_launched),
        });
      });
    });
    return rows;
  }

  function ensureListData() {
    // 从数据库获取（强制），失败则返回空列表并提示
    var fb = document.getElementById('mp-total');
    if (fb) fb.textContent = '正在从数据库加载商品...';
    return fetchMyProductsFromDb().then(function(apiProducts) {
      state.list = flattenProducts(apiProducts);
      return state.list;
    }).catch(function(err) {
      state.list = [];
      if (fb) fb.textContent = '加载失败：' + (err && err.message ? err.message : '未知错误');
      return state.list;
    });
  }

  function applyFilters(items) {
    return items.filter(function(p) {
      if (state.filters.status !== 'all') {
        if (state.filters.status === 'none' && p.stock !== 0) return false;
        if (state.filters.status === 'low' && !(p.stock > 0 && p.stock <= 100)) return false;
        if (state.filters.status === 'good' && !(p.stock > 100)) return false;
      }
      if (state.filters.cat1 !== 'all' && p.cat1 !== state.filters.cat1) return false;
      if (state.filters.q) {
        var q = state.filters.q.toLowerCase();
        var hay = p.nameZh.toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
  }

  function renderList() {
    var tbody = document.getElementById('mp-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    var items = applyFilters(state.list);
    var total = items.length;
    var pages = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > pages) state.page = pages;
    var start = (state.page - 1) * state.pageSize;
    var pageItems = items.slice(start, start + state.pageSize);

    pageItems.forEach(function(p) {
      var st = getStockLabel(p.stock);
      var lt = getLaunchLabel(!!p.is_launched);
      var stockClass = p.stock === 0 ? 'stock-bad' : (p.stock <= 100 ? 'stock-bad' : 'stock-ok');
      var tr = document.createElement('tr');
      tr.innerHTML = ''
        + '<td><input type="checkbox" class="mp-check" data-sku-id="' + (p.sku_id != null ? p.sku_id : '') + '"></td>'
        + '<td><img class="thumb" src="' + escapeHtml(p.image) + '" alt=""></td>'
        + '<td>'
        +   '<div style="font-weight:800;color:#1b5e20;">' + escapeHtml(p.nameZh) + '</div>'
        + '</td>'
        + '<td><div style="color:#1b5e20;font-weight:700;">' + escapeHtml(p.cat1) + '</div></td>'
        + '<td class="' + stockClass + '">' + p.stock + '<div class="muted">' + (p.stock === 0 ? '库存无（=0）' : (p.stock <= 100 ? '库存紧张（<=100）' : '库存充足（>100）')) + '</div></td>'
        + '<td>USD ' + (p.priceUsd || 0).toFixed(2) + '</td>'
        + '<td><span class="tag ' + st.cls + '">' + st.text + '</span></td>'
        + '<td><span class="tag ' + lt.cls + '">' + lt.text + '</span></td>'
        + '<td class="muted">' + p.createdAt + '</td>'
        + '<td class="row-actions">'
        +   '<a href="merchant_products.html?mode=edit&product=' + encodeURIComponent(String(p.sku_id || '')) + '">编辑</a>'
        +   '<a href="#" data-act="settings" data-sku-id="' + escapeHtml(p.sku_id) + '">设置</a>'
        +   '<a href="#" data-act="view" data-sku-id="' + escapeHtml(p.sku_id) + '">查看</a>'
        +   '<a href="#" class="danger" data-act="delete" data-sku-id="' + escapeHtml(p.sku_id) + '">删除</a>'
        + '</td>';
      tbody.appendChild(tr);
    });

    document.getElementById('mp-total').textContent = '共 ' + total + ' 条';
    var pagesText = '第 ' + state.page + ' / ' + pages + ' 页';
    if (document.getElementById('mp-page')) document.getElementById('mp-page').textContent = pagesText;
    if (document.getElementById('mp-total-2')) document.getElementById('mp-total-2').textContent = pagesText;

    document.querySelectorAll('.mp-check').forEach(function(cb) {
      cb.addEventListener('change', function() {
        var id = cb.getAttribute('data-sku-id');
        if (!id) return;
        if (cb.checked) state.selected.add(String(id));
        else state.selected.delete(String(id));
      });
    });
    function ensureSettingsPopover() {
      if (document.getElementById('mp-settings-pop')) return;
      var pop = document.createElement('div');
      pop.id = 'mp-settings-pop';
      pop.style.position = 'fixed';
      pop.style.zIndex = '9999';
      pop.style.display = 'none';
      pop.style.minWidth = '220px';
      pop.style.maxWidth = '260px';
      pop.style.background = '#fff';
      pop.style.border = '1px solid rgba(27,94,32,.18)';
      pop.style.boxShadow = '0 10px 26px rgba(0,0,0,.12)';
      pop.style.borderRadius = '10px';
      pop.style.padding = '10px';
      pop.innerHTML = ''
        + '<div style="font-weight:800;color:#1b5e20;margin-bottom:8px;">设定</div>'
        + '<div style="display:grid;gap:8px;">'
        + '  <label style="font-size:12px;color:#6b7280;">上架状态</label>'
        + '  <select id="mp-pop-status" class="btn" style="width:100%;padding:8px 10px;border-radius:10px;">'
        + '    <option value="true">上架</option>'
        + '    <option value="false">下架</option>'
        + '  </select>'
        + '</div>'
        + '<div style="display:flex;justify-content:flex-end;gap:10px;margin-top:10px;">'
        + '  <button type="button" class="btn" id="mp-pop-cancel">取消</button>'
        + '  <button type="button" class="btn btn-primary" id="mp-pop-ok">确定</button>'
        + '</div>'
        + '<div id="mp-pop-tip" style="margin-top:8px;font-size:12px;color:#6b7280;"></div>';
      document.body.appendChild(pop);

      // 点击空白处关闭
      document.addEventListener('click', function(e) {
        var t = e.target;
        if (!t) return;
        var inPop = pop.contains(t);
        var isSettingsLink = (t.getAttribute && t.getAttribute('data-act') === 'settings');
        if (!inPop && !isSettingsLink) {
          pop.style.display = 'none';
          pop.removeAttribute('data-sku-id');
        }
      }, true);

      // 确定/取消按钮
      var okBtn = null;
      var cancelBtn = null;
      var statusSel = null;
      function bindOnce() {
        if (okBtn) return;
        okBtn = document.getElementById('mp-pop-ok');
        cancelBtn = document.getElementById('mp-pop-cancel');
        statusSel = document.getElementById('mp-pop-status');
        if (!okBtn || !cancelBtn || !statusSel) return;
        cancelBtn.addEventListener('click', function() {
          pop.style.display = 'none';
          pop.removeAttribute('data-sku-id');
          var tip = document.getElementById('mp-pop-tip');
          if (tip) tip.textContent = '';
        });
        okBtn.addEventListener('click', function() {
          var skuId = pop.getAttribute('data-sku-id');
          if (!skuId) {
            pop.style.display = 'none';
            return;
          }
          var isLaunched = (statusSel.value === 'true');
          okBtn.disabled = true;
          cancelBtn.disabled = true;
          statusSel.disabled = true;
          var tip = document.getElementById('mp-pop-tip');
          if (tip) tip.textContent = '正在提交...';
          updateSkuStatusToDb(skuId, isLaunched).then(function() {
            return ensureListData();
          }).then(function() {
            renderList();
            pop.style.display = 'none';
            pop.removeAttribute('data-sku-id');
          }).catch(function(err) {
            if (tip) tip.textContent = '更新失败：' + (err && err.message ? err.message : '未知错误');
          }).finally(function() {
            okBtn.disabled = false;
            cancelBtn.disabled = false;
            statusSel.disabled = false;
          });
        });
      }
      bindOnce();
    }

    ensureSettingsPopover();

    document.querySelectorAll('.row-actions a[data-act]').forEach(function(a) {
      a.addEventListener('click', function(e) {
        e.preventDefault();
        var skuId = a.getAttribute('data-sku-id');
        var act = a.getAttribute('data-act');
        if (act === 'view') {
          var product = state.list.find(function(x) { return String(x.sku_id) === skuId; });
          if (product) MerchantProductPreview.open(product);
          return;
        }
        if (act === 'settings') {
          var p = state.list.find(function(x) { return String(x.sku_id) === skuId; });
          if (!p || !p.sku_id) return alert('未找到该商品，无法设置');
          var pop = document.getElementById('mp-settings-pop');
          if (!pop) return;
          pop.setAttribute('data-sku-id', String(p.sku_id));
          var statusSel = document.getElementById('mp-pop-status');
          var tip = document.getElementById('mp-pop-tip');
          if (tip) tip.textContent = '';
          if (statusSel) statusSel.value = p.is_launched ? 'true' : 'false';

          var rect = a.getBoundingClientRect();
          var left = Math.min(window.innerWidth - 280, Math.max(8, rect.left));
          var top = Math.min(window.innerHeight - 180, Math.max(8, rect.bottom + 8));
          pop.style.left = left + 'px';
          pop.style.top = top + 'px';
          pop.style.display = 'block';
        }
        if (act === 'delete') deleteProduct(skuId);
      });
    });
  }

  // copyProduct 已移除：不再提供复制入口

  function deleteProduct(skuId) {
    var p = state.list.find(function(x) { return String(x.sku_id) === String(skuId); });
    if (!p) return;
    if (!confirm('确认删除商品「' + p.nameZh + '」？')) return;
    if (!skuId) {
      alert('未找到该商品，无法删除');
      return;
    }
    deleteSkuFromDb(skuId).then(function() {
      return ensureListData();
    }).then(function() {
      renderList();
    }).catch(function(err) {
      alert('删除失败：' + (err && err.message ? err.message : '未知错误'));
    });
  }

  function byId(id) { return document.getElementById(id); }

  function fetchBrandsAndCatalogs() {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (typeof AuthStorage === 'undefined' || !AuthStorage.getToken()) return reject(new Error('未登录'));
      $.ajax({
        type: 'GET',
        url: _getBaseUrl() + '/v1/goods/merchant/brands-catalogs',
        headers: { 'Authorization': AuthStorage.getToken() },
        success: function(r) {
          if (!r || r.code !== 200) return reject(new Error((r && r.error) ? r.error : '获取分类失败'));
          resolve((r.data && r.data.catalogs) ? r.data.catalogs : []);
        },
        error: function() { reject(new Error('获取分类失败')); }
      });
    });
  }

  function fillCatalogOptions(catalogs, selectedName) {
    var sel = byId('f-catalog');
    if (!sel) return;
    sel.innerHTML = '';
    sel.add(new Option('请选择茶叶品种', ''));
    (catalogs || []).forEach(function(c) {
      var opt = document.createElement('option');
      opt.value = c.name;
      opt.textContent = c.name;
      sel.appendChild(opt);
    });
    if (selectedName) sel.value = selectedName;
  }

  function saveSpuToDb(spuId, data) {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (!spuId) return reject(new Error('未找到该商品'));
      $.ajax({
        type: 'PUT',
        url: _getBaseUrl() + '/v1/goods/merchant/spu/' + encodeURIComponent(String(spuId)),
        headers: { 'Authorization': AuthStorage.getToken(), 'Content-Type': 'application/json' },
        data: JSON.stringify(data || {}),
        success: function(r) {
          if (r && r.code === 200) return resolve(true);
          reject(new Error((r && r.error) ? r.error : '保存商品失败'));
        },
        error: function() { reject(new Error('保存商品失败')); }
      });
    });
  }

  function saveSkuToDb(skuId, data) {
    return new Promise(function(resolve, reject) {
      if (typeof $ === 'undefined') return reject(new Error('jQuery 未加载'));
      if (!skuId) return reject(new Error('未找到该商品'));
      $.ajax({
        type: 'PUT',
        url: _getBaseUrl() + '/v1/goods/merchant/sku/' + encodeURIComponent(String(skuId)),
        headers: { 'Authorization': AuthStorage.getToken(), 'Content-Type': 'application/json' },
        data: JSON.stringify(data || {}),
        success: function(r) {
          if (r && r.code === 200) return resolve(true);
          reject(new Error((r && r.error) ? r.error : '保存商品失败'));
        },
        error: function() { reject(new Error('保存商品失败')); }
      });
    });
  }

  function uploadSkuImageToDb(skuId, file) {
    return new Promise(function(resolve, reject) {
      if (!file) return resolve(true);
      var fd = new FormData();
      fd.append('image', file);
      $.ajax({
        type: 'POST',
        url: _getBaseUrl() + '/v1/goods/merchant/sku/' + encodeURIComponent(String(skuId)) + '/image',
        headers: { 'Authorization': AuthStorage.getToken() },
        data: fd,
        processData: false,
        contentType: false,
        success: function(r) {
          if (r && r.code === 200) return resolve(true);
          reject(new Error((r && r.error) ? r.error : '上传图片失败'));
        },
        error: function() { reject(new Error('上传图片失败')); }
      });
    });
  }

  function ensureEditMeta() {
    // 编辑页分类下拉来自数据库接口（brands-catalogs）
    if (window.__mp_edit_meta) return Promise.resolve(true);
    window.__mp_edit_meta = true;
    return fetchBrandsAndCatalogs().then(function(catalogs) {
      fillCatalogOptions(catalogs);
      return true;
    }).catch(function() { return true; });
  }

  async function loadEdit(skuId) {
    await Promise.all([ensureListData(), ensureEditMeta()]);
    var p = state.list.find(function(x) { return String(x.sku_id) === String(skuId); });
    if (!p) {
      alert('未找到该商品');
      setMode('list', {});
      return;
    }
    currentSku = String(p.sku_id || '');

    if (byId('mp-edit-title')) byId('mp-edit-title').textContent = '商品编辑';
    if (byId('f-sku-id')) byId('f-sku-id').value = String(p.sku_id || '');
    if (byId('f-spu-name')) byId('f-spu-name').value = p.spu_name || '';
    if (byId('f-brand')) byId('f-brand').value = p.brand || '';
    if (byId('f-catalog')) byId('f-catalog').value = p.cat1 || '';
    if (byId('f-introduction')) byId('f-introduction').value = p.caption || '';
    if (byId('f-price')) byId('f-price').value = p.priceUsd || 0;
    if (byId('f-stock')) byId('f-stock').value = p.stock || 0;
    if (byId('f-launched')) byId('f-launched').value = p.is_launched ? 'true' : 'false';
    if (byId('f-cur-img')) byId('f-cur-img').setAttribute('src', p.image || '/static/images/cart/product_normal.png');

    if (!window.__mp_edit_wired) {
      window.__mp_edit_wired = true;
      document.getElementById('btn-preview').addEventListener('click', function() {
        MerchantProductPreview.open(p);
      });
      document.getElementById('btn-save-primary') && document.getElementById('btn-save-primary').addEventListener('click', function() {
        var skuId = byId('f-sku-id') ? byId('f-sku-id').value : null;
        var p = state.list.find(function(x) { return String(x.sku_id) === String(skuId); });
        if (!p) return alert('未找到该商品');
        if (!byId('f-catalog').value) return alert('请选择茶叶品种');

        var spuPayload = {
          name: (byId('f-spu-name').value || '').trim(),
          brand: (byId('f-brand').value || '').trim(),
          catalog: byId('f-catalog').value
        };
        if (!spuPayload.name) return alert('请填写商品名称');
        var skuPayload = {
          name: spuPayload.name,
          caption: (byId('f-introduction').value || '').trim(),
          price: parseFloat(byId('f-price').value || '0') || 0,
          stock: parseInt(byId('f-stock').value || '0', 10) || 0,
          is_launched: (byId('f-launched').value === 'true')
        };
        var file = (byId('f-image') && byId('f-image').files) ? byId('f-image').files[0] : null;

        saveSpuToDb(p.spu_id, spuPayload).then(function() {
          return saveSkuToDb(p.sku_id, skuPayload);
        }).then(function() {
          return uploadSkuImageToDb(p.sku_id, file);
        }).then(function() {
          return ensureListData();
        }).then(function() {
          alert('保存成功');
          setMode('list', {});
        }).catch(function(err) {
          alert('保存失败：' + (err && err.message ? err.message : '未知错误'));
        });
      });
    }
  }

  function initList() {
    var fltCat1 = byId('flt-cat1');
    function readFilters() {
      state.filters.q = (byId('flt-q') && byId('flt-q').value || '').trim();
      state.filters.status = byId('flt-status').value; // all | good | low | none
      state.filters.cat1 = byId('flt-cat1').value;
      state.page = 1;
    }
    byId('btn-search').addEventListener('click', function() { readFilters(); renderList(); });
    byId('btn-reset').addEventListener('click', function() {
      byId('flt-q').value = '';
      byId('flt-status').value = 'all';
      byId('flt-cat1').value = 'all';
      readFilters();
      renderList();
    });
    byId('btn-prev').addEventListener('click', function() { state.page = Math.max(1, state.page - 1); renderList(); });
    byId('btn-next').addEventListener('click', function() { state.page = state.page + 1; renderList(); });
    if (byId('btn-prev-2')) byId('btn-prev-2').addEventListener('click', function() { state.page = Math.max(1, state.page - 1); renderList(); });
    if (byId('btn-next-2')) byId('btn-next-2').addEventListener('click', function() { state.page = state.page + 1; renderList(); });
    function batchSetLaunched(isLaunched) {
      var ids = Array.from(state.selected);
      if (ids.length === 0) {
        alert('请先勾选要操作的商品');
        return;
      }
      var title = isLaunched ? '批量上架' : '批量下架';
      if (!confirm('确认' + title + ' ' + ids.length + ' 件商品？')) return;

      var fb = document.getElementById('mp-total');
      if (fb) fb.textContent = '正在' + title + ' ' + ids.length + ' 件商品...';

      // 串行执行，避免并发过高
      var i = 0;
      function next() {
        if (i >= ids.length) {
          return ensureListData().then(function() {
            if (fb) fb.textContent = title + '完成';
            renderList();
          });
        }
        var skuId = ids[i++];
        return updateSkuStatusToDb(skuId, isLaunched).then(function() {
          return next();
        }).catch(function(err) {
          var failedProduct = state.list.find(function(x) { return String(x.sku_id) === String(skuId); });
          alert(title + '中断：商品「' + (failedProduct ? failedProduct.nameZh : '未知商品') + '」操作失败：' + (err && err.message ? err.message : '未知错误'));
          return ensureListData().then(function() { renderList(); });
        });
      }
      next();
    }

    if (byId('b-on')) byId('b-on').addEventListener('click', function() { batchSetLaunched(true); });
    if (byId('b-off')) byId('b-off').addEventListener('click', function() { batchSetLaunched(false); });
    if (byId('b-del')) byId('b-del').addEventListener('click', function() {
      var ids = Array.from(state.selected);
      if (ids.length === 0) {
        alert('请先勾选要删除的商品');
        return;
      }
      if (!confirm('确认批量删除 ' + ids.length + ' 件商品？此操作不可恢复。')) return;

      var fb = document.getElementById('mp-total');
      if (fb) fb.textContent = '正在批量删除 ' + ids.length + ' 件商品...';

      // 串行删除：便于定位失败原因，且避免同时请求过多
      var i = 0;
      function next() {
        if (i >= ids.length) {
          state.selected.clear();
          return ensureListData().then(function() {
            if (fb) fb.textContent = '批量删除完成';
            renderList();
          });
        }
        var skuId = ids[i++];
        return deleteSkuFromDb(skuId).then(function() {
          return next();
        }).catch(function(err) {
          var failedProduct = state.list.find(function(x) { return String(x.sku_id) === String(skuId); });
          alert('批量删除中断：商品「' + (failedProduct ? failedProduct.nameZh : '未知商品') + '」删除失败：' + (err && err.message ? err.message : '未知错误'));
          return ensureListData().then(function() { renderList(); });
        });
      }
      next();
    });
    // 拉取数据库商品后再渲染
    ensureListData().then(function() {
      if (fltCat1) {
        fltCat1.innerHTML = '<option value="all">全部分类</option>';
        // 从数据库数据中动态抽取 catalog 列表
        var seen = {};
        state.list.forEach(function(p) {
          var k = p.cat1 || '-';
          if (!seen[k]) {
            seen[k] = true;
            var o = document.createElement('option');
            o.value = k; o.textContent = k;
            fltCat1.appendChild(o);
          }
        });
      }
      renderList();
    });
  }

  function initLogout() {
    var a = byId('btn-logout');
    if (!a) return;
    a.addEventListener('click', function(e) {
      e.preventDefault();
      if (typeof AuthStorage !== 'undefined') AuthStorage.clear();
      window.location.href = 'login.html';
    });
  }

  function init() {
    initLogout();
    if (!byId('view-list') || !byId('view-edit')) return;
    var mode = getQuery().get('mode') || 'list';
    if (mode === 'create') {
      byId('view-list').style.display = 'none';
      byId('view-edit').style.display = 'none';
      if (byId('view-create')) byId('view-create').style.display = 'block';
      initCreate();
    } else if (mode === 'edit') {
      byId('view-list').style.display = 'none';
      byId('view-edit').style.display = 'block';
      if (byId('view-create')) byId('view-create').style.display = 'none';
      var skuId = getQuery().get('product') || getQuery().get('sku_id');
      if (!skuId) {
        alert('未指定要编辑的商品');
        setMode('list', {});
        return;
      }
      loadEdit(skuId);
    } else {
      byId('view-list').style.display = 'block';
      byId('view-edit').style.display = 'none';
      if (byId('view-create')) byId('view-create').style.display = 'none';
      initList();
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
