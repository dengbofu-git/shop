/** Read-only preview of a row returned by the authenticated merchant products API. */
window.MerchantProductPreview = {
    open: function (product) {
        var dialog = document.getElementById('merchant-product-preview');
        if (!dialog) {
            dialog = document.createElement('dialog');
            dialog.id = 'merchant-product-preview';
            dialog.className = 'mp-preview';
            dialog.setAttribute('aria-labelledby', 'mp-preview-title');
            document.body.appendChild(dialog);
        }
        dialog.replaceChildren();
        function node(tag, text, cls) {
            var el = document.createElement(tag);
            if (text !== undefined) el.textContent = text;
            if (cls) el.className = cls;
            return el;
        }
        var heading = node('div', undefined, 'mp-preview-heading');
        var title = node('h2', '商品详情');
        title.id = 'mp-preview-title';
        var close = node('button', '关闭', 'btn');
        close.type = 'button';
        close.addEventListener('click', function () { dialog.close(); });
        heading.append(title, close);
        var body = node('div', undefined, 'mp-preview-body');
        var image = node('img');
        image.src = product.image;
        image.alt = product.nameZh || '商品图片';
        var info = node('section');
        info.appendChild(node('h3', product.nameZh));
        var fields = node('dl');
        [['商品编号', product.sku_id], ['茶类', product.cat1], ['品牌', product.brand || '未设置'],
         ['售价', 'CNY ' + Number(product.priceCny || 0).toFixed(2)], ['库存', product.stock],
         ['状态', product.is_launched ? '上架' : '下架']].forEach(function (pair) {
            fields.append(node('dt', pair[0]), node('dd', String(pair[1])));
        });
        info.appendChild(fields);
        info.appendChild(node('p', product.caption || '暂无商品介绍', 'mp-preview-caption'));
        info.appendChild(node('p', '当前商家已保存的商品信息', 'muted'));
        body.append(image, info);
        dialog.append(heading, body);
        dialog.showModal();
    }
};
