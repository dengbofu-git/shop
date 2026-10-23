/* Shared, text-only storefront rendering for public pages and merchant previews. */
(function () {
    'use strict';
    function text(tag, cls, value) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        node.textContent = value || '';
        return node;
    }
    function lang() { return localStorage.getItem('buyer_lang') || 'zh'; }
    var labels = {
        zh: {shop: '店铺', enter: '店铺详情 →', soon: '店铺筹备中', unknown: '暂未登记店铺', add: '加入采购车', price: '参考价格'},
        en: {shop: 'Store', enter: 'View store →', soon: 'Store coming soon', unknown: 'Store unavailable', add: 'Add to Cart', price: 'Reference price'},
        ar: {shop: 'المتجر', enter: 'عرض المتجر ←', soon: 'المتجر قيد التجهيز', unknown: 'المتجر غير متاح', add: 'أضف للسلة', price: 'سعر مرجعي'}
    };
    function t(key) { return (labels[lang()] || labels.zh)[key]; }
    function merchantLink(merchant) {
        var line = text('div', 'product-store');
        if (!merchant) { line.appendChild(text('span', 'store-muted', t('unknown'))); return line; }
        line.appendChild(text('span', 'product-store-name', t('shop') + ' · ' + merchant.name));
        if (merchant.url && merchant.is_published && Number.isSafeInteger(merchant.id) && merchant.id > 0) {
            var link = text('a', 'product-store-link', t('enter'));
            link.href = '/store.html?merchant_id=' + merchant.id;
            line.appendChild(link);
        } else line.appendChild(text('span', 'store-muted', t('soon')));
        return line;
    }
    function hero(root, content, actions) {
        root.replaceChildren();
        var banner = text('div', 'store-banner');
        if (content.banner_url) {
            var image = document.createElement('img'); image.src = content.banner_url; image.alt = ''; banner.appendChild(image);
        } else {
            banner.appendChild(text('span', 'store-banner-word', 'TEA & ORIGIN'));
            banner.appendChild(text('p', '', content.welcome || '从一杯好茶，认识一家好店'));
        }
        var identity = text('div', 'store-identity');
        var logo = text('div', 'store-logo', (content.name || '茶').slice(0, 1));
        if (content.logo_url) {
            logo.textContent = ''; var logoImage = document.createElement('img');
            logoImage.src = content.logo_url; logoImage.alt = '店铺 Logo'; logo.appendChild(logoImage);
        }
        var copy = text('div', 'store-identity-copy');
        copy.appendChild(text('p', 'store-eyebrow', 'MERCHANT STOREFRONT · 商家主页'));
        copy.appendChild(text('h1', '', content.name || '我的店铺'));
        copy.appendChild(text('p', 'store-summary', content.summary || '商家正在完善店铺介绍。'));
        if (content.banner_url && content.welcome) copy.appendChild(text('p', 'store-welcome', content.welcome));
        identity.append(logo, copy);
        if (actions) identity.appendChild(actions);
        root.append(banner, identity);
    }
    function card(item, preview) {
        var node = text('article', 'product-card store-product-card');
        var id = Number(item.skuid);
        node.setAttribute('data-sku-id', String(id)); node.setAttribute('data-pname', item.product_name || item.name || '');
        node.setAttribute('data-cny', String(item.price || 0)); node.setAttribute('data-pimg', item.image || '');
        var link = text(preview ? 'div' : 'a', 'product-img-wrap');
        if (!preview) link.href = '/product_details.html?skuid=' + id;
        var img = document.createElement('img'); img.src = '/v1/goods/sku/' + id + '/image';
        img.alt = item.product_name || item.name || ''; img.loading = 'lazy'; link.appendChild(img);
        var title = text('h3', 'product-name');
        var titleLink = text(preview ? 'span' : 'a', '', item.product_name || item.spu_name || item.name);
        if (!preview) titleLink.href = '/product_details.html?skuid=' + id;
        title.appendChild(titleLink);
        var price = text('div', 'product-price');
        price.setAttribute('data-cny', String(item.price || 0));
        var currency = document.getElementById('currency-select');
        price.textContent = TeaMoney.format(item.price || 0, currency && currency.value);
        var actions = text('div', 'product-actions-row');
        var add = text('button', 'btn-add-cart', preview ? '预览 · 不可采购' : t('add'));
        add.type = 'button'; add.disabled = !!preview; actions.appendChild(add);
        node.append(link, title, text('p', 'product-spec', item.caption || item.name), price, actions);
        return node;
    }
    function cards(root, items, preview) {
        root.replaceChildren();
        if (!items.length) { root.appendChild(text('p', 'store-empty', '当前没有符合条件的商品。')); return; }
        items.forEach(function (item) { root.appendChild(card(item, preview)); });
    }
    window.Storefront = {hero: hero, cards: cards, merchantLink: merchantLink};
}());
