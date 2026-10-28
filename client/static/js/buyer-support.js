(function () {
    'use strict';
    var form = document.getElementById('bs-form');
    var input = document.getElementById('bs-input');
    var send = document.getElementById('bs-send');
    var messages = document.getElementById('bs-messages');
    var newConversation = document.getElementById('bs-new-conversation');
    var preferenceForm = document.getElementById('bs-preferences-form');
    var preferenceStatus = document.getElementById('bs-preference-status');
    var preferenceFields = {
        categories: document.getElementById('bs-pref-categories'),
        brands: document.getElementById('bs-pref-brands'),
        keywords: document.getElementById('bs-pref-keywords')
    };
    var labels = { recommendation: '商品推荐', recommendation_explanation: '推荐理由', question_answering: '咨询问答', product_details: '商品详情', after_sales: '售后服务', clarification: '补充信息', multi_intent: '多任务', unavailable: '其他问题' };
    var storageKey = 'support-conversation:' + (AuthStorage.getUser() || '');
    var conversation = null;
    var pending = null;
    var selectedBundle = null;
    var busy = false;
    var composing = false;
    var initialMessage = messages.innerHTML;
    var historyToggle = document.getElementById('bs-history-toggle');
    var historyPanel = document.getElementById('bs-history');
    var historyList = document.getElementById('bs-history-list');
    var historyStatus = document.getElementById('bs-history-status');
    var historyRefresh = document.getElementById('bs-history-refresh');
    var historyMore = document.getElementById('bs-history-more');
    var historyOlder = document.getElementById('bs-history-older');
    var historyMenu = document.getElementById('bs-history-menu');
    var historyDelete = document.getElementById('bs-history-delete');
    var menuConversation = null;
    var currentLabel = document.getElementById('bs-current-conversation');
    var conversationStatus = document.getElementById('bs-conversation-status');
    var identityToken = AuthStorage.getToken();
    var identityUser = AuthStorage.getUser();
    var identityCleared = false;
    var cartOperations = Object.create(null);
    var historyCursor = null;
    var olderCursor = null;
    var historyLoaded = false;
    var restoreBlocked = false;
    var sessionTitle = '';
    var drafts = Object.create(null);
    var hiddenHistoryKey = 'support-hidden-history:' + (identityUser || '');
    var hiddenHistory = new Set();
    try {
        var savedHidden = JSON.parse(localStorage.getItem(hiddenHistoryKey) || '[]');
        if (Array.isArray(savedHidden)) savedHidden.forEach(function (id) { if (typeof id === 'string') hiddenHistory.add(id); });
    } catch (_) { /* An unavailable browser store must not affect server history. */ }

    function sameIdentity() {
        return identityToken === AuthStorage.getToken() && identityUser === AuthStorage.getUser();
    }

    function checkIdentity() {
        if (sameIdentity()) return;
        if (!identityCleared) {
            identityCleared = true;
            drafts = Object.create(null);
            cartOperations = Object.create(null);
            conversation = pending = null;
            selectedBundle = null;
            historyCursor = olderCursor = null;
            input.value = '';
            fillPreferences({});
            preferenceStatus.textContent = '登录账号已变化，请刷新页面后继续。';
            historyList.textContent = '';
            messages.innerHTML = initialMessage;
            sessionStorage.removeItem(storageKey);
            closeHistory();
            updateSession();
            conversationStatus.textContent = '登录账号已变化，请刷新页面后继续。';
            setBusy(true);
        }
        var error = new Error('登录账号已变化，请刷新页面后继续。');
        error.status = 401;
        throw error;
    }

    function ensureIdentity() {
        try { checkIdentity(); return true; }
        catch (error) { return false; }
    }

    async function api(path, method, data) {
        checkIdentity();
        var token = AuthStorage.getToken();
        if (!token) throw new Error('请先登录后再使用智能客服。');
        var response;
        try {
            response = await fetch('/v1/support/' + path, {
                method: method || 'GET',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: data === undefined ? undefined : JSON.stringify(data)
            });
        } catch (networkError) { checkIdentity(); throw networkError; }
        checkIdentity();
        var result;
        try { result = await response.json(); }
        catch (parseError) { checkIdentity(); throw new Error('服务响应异常，请稍后重试。'); }
        checkIdentity();
        if (!response.ok) {
            var error = new Error(result.error || '暂时无法回答，请稍后重试。');
            error.status = response.status;
            error.errorCode = result.error_code || '';
            throw error;
        }
        return result;
    }

    async function downloadKnowledgePdf(event, url, link, label) {
        event.preventDefault();
        if (link.dataset.loading === 'true') return;
        link.dataset.loading = 'true';
        try {
            checkIdentity();
            var response = await fetch(url.href, {
                headers: { Authorization: 'Bearer ' + identityToken }, redirect: 'error', cache: 'no-store'
            });
            checkIdentity();
            if (!response.ok) throw new Error(response.status === 503 ? '资料服务暂不可用' : '资料不可访问或已撤回');
            var blob = await response.blob();
            checkIdentity();
            var objectUrl = URL.createObjectURL(blob);
            var download = document.createElement('a');
            download.href = objectUrl;
            download.download = 'knowledge-' + url.pathname.split('/')[5] + '.pdf';
            document.body.appendChild(download);
            download.click();
            download.remove();
            window.setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 60000);
            link.textContent = label;
        } catch (error) {
            if (sameIdentity()) link.textContent = label + '（' + (error.message || '下载失败') + '）';
        } finally { delete link.dataset.loading; }
    }

    function uuid() {
        var bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 15) | 64;
        bytes[8] = (bytes[8] & 63) | 128;
        var hex = Array.from(bytes, function (byte) { return byte.toString(16).padStart(2, '0'); }).join('');
        return hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' + hex.slice(16, 20) + '-' + hex.slice(20);
    }

    function setBusy(value) {
        busy = value || !sameIdentity();
        if (busy) closeHistoryMenu(false);
        send.disabled = busy || restoreBlocked;
        newConversation.disabled = busy;
        historyToggle.disabled = busy;
        historyRefresh.disabled = busy;
        historyMore.disabled = busy;
        historyOlder.disabled = busy;
        historyList.querySelectorAll('button').forEach(function (button) { button.disabled = busy; });
        messages.querySelectorAll('.bs-bundle-tabs button').forEach(function (button) { button.disabled = busy; });
    }

    function addMessage(text, kind, container) {
        var item = document.createElement('div');
        item.className = 'bs-message bs-' + kind;
        var body = document.createElement('div');
        var bubble = document.createElement('div');
        bubble.className = 'bs-bubble';
        bubble.textContent = text;
        body.appendChild(bubble);
        item.appendChild(body);
        (container || messages).appendChild(item);
        if (!container) messages.scrollTop = messages.scrollHeight;
        return bubble;
    }

    function showResult(bubble, result, historicalAt) {
        bubble.textContent = result.answer;
        var note = result.intents && result.intents.length ? result.intents.map(function (intent) { return labels[intent] || intent; }).join(' → ') : labels[result.intent] || '智能客服';
        if (result.pii_redacted) note += ' · 已脱敏';
        if (result.memory_used) note += ' · 使用了长期偏好';
        if (historicalAt) note += ' · 历史记录 · ' + displayTime(historicalAt) + ' · 价格、库存和状态可能已变化';
        var meta = document.createElement('small');
        meta.textContent = note;
        bubble.parentNode.appendChild(meta);
        if (result.knowledge_sources && result.knowledge_sources.length) {
            var sources = document.createElement('small');
            sources.className = 'bs-sources';
            sources.appendChild(document.createTextNode('参考资料：'));
            result.knowledge_sources.forEach(function (source, index) {
                try {
                    var sourceUrl = new URL(source.url, window.location.origin);
                    if (sourceUrl.username || sourceUrl.password) return;
                    var localPdf = sourceUrl.origin === window.location.origin &&
                        /^\/v1\/support\/knowledge\/documents\/[a-f0-9-]{36}\/file$/i.test(sourceUrl.pathname) &&
                        !sourceUrl.search && !sourceUrl.hash;
                    if (!localPdf && (sourceUrl.protocol !== 'https:' || !/^https:\/\//i.test(source.url))) return;
                    if (index) sources.appendChild(document.createTextNode(' · '));
                    var link = document.createElement('a');
                    link.href = sourceUrl.href;
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                    link.textContent = source.title + (source.year ? ' (' + source.year + ')' : '');
                    if (localPdf) {
                        link.removeAttribute('target');
                        var sourceLabel = link.textContent + ' · 第' + source.page_start + '—' + source.page_end + '页（下载PDF）';
                        link.textContent = sourceLabel;
                        link.addEventListener('click', function (event) {
                            downloadKnowledgePdf(event, sourceUrl, link, sourceLabel);
                        });
                    }
                    sources.appendChild(link);
                } catch (error) {
                    // Ignore malformed source URLs in response data.
                }
            });
            bubble.parentNode.appendChild(sources);
        }
        if (result.compliance_blocked) return;
        if (result.order_result && Array.isArray(result.order_result.orders)) {
            var orderActions = document.createElement('div');
            orderActions.className = 'bs-order-actions';
            result.order_result.orders.forEach(function (order) {
                if (typeof order.detail_url !== 'string' || !/^\/buyer_orders\.html#support-order=os-[a-p]{64}$/.test(order.detail_url)) return;
                var link = document.createElement('a');
                link.className = 'bs-order-link';
                link.href = order.detail_url;
                link.textContent = '查看' + order.reference;
                link.setAttribute('aria-label', '查看' + order.reference + '的订单详情');
                orderActions.appendChild(link);
            });
            if (orderActions.children.length) bubble.parentNode.appendChild(orderActions);
        }
        if (showBundles(bubble, result, historicalAt)) return;
        if (result.recommendations && result.recommendations.length) {
            var cards = document.createElement('div');
            cards.className = 'bs-products';
            result.recommendations.forEach(function (product) {
                if (!Number.isInteger(product.sku_id) || product.sku_id <= 0) return;
                var card = document.createElement('a');
                card.className = 'bs-product';
                card.href = '/product_details.html?skuid=' + product.sku_id;
                var image = document.createElement('img');
                image.src = '/v1/goods/sku/' + product.sku_id + '/image';
                image.alt = product.product_name || product.name;
                image.loading = 'lazy';
                card.appendChild(image);
                var info = document.createElement('div');
                var title = document.createElement('strong');
                title.textContent = product.product_name || product.name;
                info.appendChild(title);
                if (product.product_name && product.name && product.name !== product.product_name) {
                    var specification = document.createElement('p');
                    specification.textContent = product.name;
                    info.appendChild(specification);
                }
                var price = document.createElement('p');
                if (historicalAt && !product.currency) {
                    price.textContent = '原记录金额 ' + product.price + '（币种未记录） · ' + product.category;
                } else if (!product.currency || product.currency === 'CNY') {
                    price.dataset.basePrice = product.price;
                    price.dataset.category = product.category || '';
                    price.textContent = shownMoney(product.price, 'CNY') + ' · ' + (product.category || '');
                } else {
                    // Old snapshots keep the currency recorded at that time.
                    price.textContent = product.currency + ' ' + product.price + ' · ' + product.category;
                }
                info.appendChild(price);
                var reason = document.createElement('p');
                reason.textContent = (product.reasons || []).join('、');
                info.appendChild(reason);
                card.appendChild(info);
                var entry = document.createElement('div'); entry.className = 'bs-product-entry';
                entry.appendChild(card);
                var action = cartAction(result, {sku_id: product.sku_id}, '加入采购车', 1, true);
                if (action) entry.appendChild(action);
                cards.appendChild(entry);
            });
            bubble.parentNode.appendChild(cards);
        }
    }

    function shownMoney(amount, currency) {
        var text = currency === 'CNY' ? TeaMoney.format(amount, 'CNY') : currency + ' ' + amount;
        var selected = document.getElementById('currency-select').value;
        if (currency === 'CNY' && selected !== 'CNY') text += '（参考 ' + TeaMoney.format(amount, selected) + '）';
        return text;
    }

    function cartAction(result, selection, label, initialQuantity, editable) {
        // 旧记录没有可信请求引用时，不提供无法绑定来源的写操作。
        if (!result.request_id || !/^[0-9a-f-]{32,36}$/i.test(result.request_id)) return null;
        var group = document.createElement('div');
        group.className = 'bs-cart-actions';
        var quantity;
        if (editable) {
            var quantityLabel = document.createElement('label');
            quantityLabel.textContent = '本次加入件数 ';
            quantity = document.createElement('input');
            quantity.type = 'number'; quantity.min = '1'; quantity.max = '999999999'; quantity.step = '1';
            quantity.value = String(initialQuantity || 1);
            quantity.setAttribute('aria-label', '本次加入采购车的件数');
            quantityLabel.appendChild(quantity); group.appendChild(quantityLabel);
        }
        var button = document.createElement('button');
        button.type = 'button'; button.textContent = label;
        var status = document.createElement('span'); status.setAttribute('role', 'status');
        var link = document.createElement('a'); link.href = '/cart.html'; link.textContent = '查看采购车';
        group.appendChild(button); group.appendChild(link); group.appendChild(status);
        if (quantity) quantity.addEventListener('input', function () { button.disabled = false; button.textContent = label; status.textContent = ''; });
        button.addEventListener('click', async function () {
            if (button.disabled || !ensureIdentity()) return;
            var count = quantity ? Number(quantity.value) : null;
            if (quantity && (!Number.isInteger(count) || count < 1 || count > 999999999)) {
                status.textContent = '购买件数必须为正整数。'; return;
            }
            var payload = Object.assign({recommendation_request_id: result.request_id}, selection);
            if (quantity) payload.count = count;
            var actionKey = JSON.stringify(payload);
            var operation = cartOperations[actionKey];
            if (!operation) operation = cartOperations[actionKey] = {id: uuid(), complete: false, busy: false};
            if (operation.busy) return;
            if (operation.complete) { status.textContent = '本次操作已加入采购车。'; button.disabled = true; return; }
            operation.busy = true; button.disabled = true; if (quantity) quantity.disabled = true;
            payload.request_id = operation.id;
            status.textContent = '正在核查商品并加入采购车…';
            try {
                checkIdentity();
                var response = await fetch('/v1/carts/' + encodeURIComponent(identityUser) + '/recommendations', {
                    method: 'POST', headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + identityToken},
                    body: JSON.stringify(payload)
                });
                var data = await response.json(); checkIdentity();
                if (!response.ok || data.code !== 200) throw new Error(data.error || '加入失败，请重试同一次操作。');
                syncCartCount(data.data && data.data.carts_count);
                operation.complete = true; button.textContent = '已加入';
                status.textContent = data.replayed ? '已确认此前加入成功，没有重复添加。' : '已加入本人采购车，未下单、未锁定库存。';
            } catch (error) {
                if (sameIdentity()) status.textContent = error.message || '结果尚未确认，请重试同一次操作。';
            } finally {
                operation.busy = false; button.disabled = operation.complete;
                if (quantity) quantity.disabled = false;
            }
        });
        return group;
    }

    function syncCartCount(count) {
        if (count === null || count === undefined) return;
        var value = Number(count);
        if (!Number.isSafeInteger(value) || value < 0) return;
        // 后端返回采购车商品种类数；存储受限时仍即时更新当前页图标。
        try { if (typeof AuthStorage !== 'undefined' && AuthStorage.setCount) AuthStorage.setCount(value); } catch (_) {}
        if (document.querySelectorAll) document.querySelectorAll('#cart-count,.my_cart_count').forEach(function (node) {
            node.textContent = String(value);
        });
    }

    function amountCents(value) {
        if (!/^\d+(?:\.\d{1,2})?$/.test(String(value))) return null;
        var parts = String(value).split('.');
        var cents = Number(parts[0]) * 100 + Number(((parts[1] || '') + '00').slice(0, 2));
        return Number.isSafeInteger(cents) ? cents : null;
    }

    function showBundles(bubble, result, historicalAt) {
        if (!Array.isArray(result.recommendation_bundles) || !result.recommendation_bundles.length) return false;
        var bundles = result.recommendation_bundles.slice(0, 3);
        // Reject a whole malformed plan rather than silently dropping a priced line.
        var valid = bundles.every(function (bundle) {
            if (!/^bundle-[0-9a-f]{12}$/.test(bundle.bundle_id) || !Array.isArray(bundle.items) ||
                !bundle.items.length || bundle.items.length > 4 || typeof bundle.currency !== 'string') return false;
            var sum = 0;
            var good = bundle.items.every(function (item) {
                var price = amountCents(item.price), subtotal = amountCents(item.line_subtotal);
                if (!Number.isInteger(item.sku_id) || item.sku_id <= 0 || !Number.isSafeInteger(item.quantity) ||
                    item.quantity < 1 || price === null || subtotal === null ||
                    price * item.quantity !== subtotal || (item.currency && item.currency !== bundle.currency)) return false;
                sum += subtotal;
                return Number.isSafeInteger(sum);
            });
            return good && sum === amountCents(bundle.subtotal);
        });
        if (!valid) {
            var warning = document.createElement('small');
            warning.textContent = '方案明细暂无法完整展示，请重新获取搭配。';
            bubble.parentNode.appendChild(warning);
            return true;
        }
        var section = document.createElement('section');
        section.className = 'bs-bundles';
        section.setAttribute('aria-label', '总价搭配方案');
        var tabs = document.createElement('div');
        tabs.className = 'bs-bundle-tabs';
        tabs.setAttribute('role', 'group');
        tabs.setAttribute('aria-label', '切换搭配方案');
        var panel = document.createElement('div');
        panel.className = 'bs-bundle-panel';
        panel.setAttribute('aria-live', 'polite');
        section.appendChild(tabs);
        section.appendChild(panel);
        bubble.parentNode.appendChild(section);
        var active = Math.max(0, bundles.findIndex(function (bundle) { return bundle.bundle_id === result.primary_bundle_id; }));
        var buttons = bundles.map(function (bundle, index) {
            var button = document.createElement('button');
            button.type = 'button';
            button.textContent = '方案' + (bundle.position || index + 1);
            button.disabled = busy;
            button.addEventListener('click', function () {
                if (busy || !ensureIdentity()) return;
                active = index;
                render();
                if (conversation && result.conversation_id === conversation.conversation_id && result.request_id) {
                    selectedBundle = { request_id: result.request_id, bundle_id: bundle.bundle_id };
                    conversationStatus.textContent = '已选择方案' + (bundle.position || index + 1) + '，接下来的商品追问将按这套方案理解。';
                }
            });
            tabs.appendChild(button);
            return button;
        });
        function render() {
            var bundle = bundles[active];
            buttons.forEach(function (button, index) { button.setAttribute('aria-pressed', String(index === active)); });
            panel.textContent = '';
            // A mixed reply may also contain a knowledge/order answer. Keep it intact.
            if (result.presentation_version === 'bundles-v2' && bundle.summary) {
                var summary = bundle.summary;
                if (bundles.length > 1) summary += '\n可以切换下方方案，比较商品和购买件数。';
                if (result.bundle_primary_answer && result.answer.indexOf(result.bundle_primary_answer) !== -1) {
                    bubble.textContent = result.answer.replace(result.bundle_primary_answer, summary);
                } else if (result.intent === 'recommendation') bubble.textContent = summary;
            }
            var cards = document.createElement('div');
            cards.className = 'bs-products';
            bundle.items.forEach(function (item) {
                var card = document.createElement('a');
                card.className = 'bs-product';
                card.href = '/product_details.html?skuid=' + item.sku_id;
                var image = document.createElement('img');
                image.src = '/v1/goods/sku/' + item.sku_id + '/image';
                image.alt = item.product_name || item.name || '';
                image.loading = 'lazy';
                card.appendChild(image);
                var info = document.createElement('div');
                var title = document.createElement('strong');
                title.textContent = item.product_name || item.name;
                info.appendChild(title);
                if (item.name && item.name !== item.product_name) {
                    var specification = document.createElement('p');
                    specification.textContent = item.name;
                    info.appendChild(specification);
                }
                var quantity = document.createElement('p');
                quantity.className = 'bs-bundle-quantity';
                quantity.textContent = shownMoney(item.price, bundle.currency) + ' / 件 × ' + item.quantity + '件';
                info.appendChild(quantity);
                var subtotal = document.createElement('p');
                subtotal.textContent = '小计 ' + shownMoney(item.line_subtotal, bundle.currency);
                info.appendChild(subtotal);
                if (item.reasons && item.reasons.length) {
                    var reason = document.createElement('p');
                    reason.textContent = item.reasons.slice(0, 2).join('，');
                    info.appendChild(reason);
                }
                card.appendChild(info);
                var entry = document.createElement('div'); entry.className = 'bs-product-entry';
                entry.appendChild(card);
                var action = cartAction(result, {bundle_id: bundle.bundle_id, sku_id: item.sku_id}, '仅加入这款', item.quantity, true);
                if (action) entry.appendChild(action);
                cards.appendChild(entry);
            });
            panel.appendChild(cards);
            var total = document.createElement('p');
            total.className = 'bs-bundle-total';
            total.textContent = '商品合计 ' + shownMoney(bundle.subtotal, bundle.currency);
            if (amountCents(bundle.remaining_budget) !== null) total.textContent += ' · 预算余量 ' + shownMoney(bundle.remaining_budget, bundle.currency);
            panel.appendChild(total);
            var units = bundle.items.reduce(function (sum, item) { return sum + item.quantity; }, 0);
            var addBundle = cartAction(result, {bundle_id: bundle.bundle_id}, '整套加入采购车，共' + units + '件', null, false);
            if (addBundle) panel.appendChild(addBundle);
            var notice = document.createElement('small');
            notice.textContent = result.bundle_notice || '商品合计不含运费、税费，价格及可购买状态以下单校验为准。';
            panel.appendChild(notice);
        }
        section.addEventListener('support-currency-change', render);
        render();
        return true;
    }

    function displayTime(value) {
        var date = new Date(value);
        return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { hour12: false });
    }

    function closeHistory() {
        closeHistoryMenu(false);
        historyPanel.hidden = true;
        historyToggle.setAttribute('aria-expanded', 'false');
    }

    function closeHistoryMenu(restoreFocus) {
        var target = menuConversation;
        menuConversation = null;
        historyMenu.hidden = true;
        if (target) {
            target.button.setAttribute('aria-expanded', 'false');
            if (restoreFocus && target.button.isConnected) target.button.focus();
        }
    }

    function openHistoryMenu(event, item, button, keyboard) {
        if (busy || !ensureIdentity()) return;
        event.preventDefault();
        closeHistoryMenu(false);
        menuConversation = { id: item.conversation_id, title: item.title, button: button };
        button.setAttribute('aria-expanded', 'true');
        historyMenu.hidden = false;
        var rect = button.getBoundingClientRect();
        var x = keyboard ? rect.left : event.clientX;
        var y = keyboard ? rect.bottom : event.clientY;
        historyMenu.style.left = Math.max(8, Math.min(x, window.innerWidth - historyMenu.offsetWidth - 8)) + 'px';
        historyMenu.style.top = Math.max(8, Math.min(y, window.innerHeight - historyMenu.offsetHeight - 8)) + 'px';
        historyDelete.focus();
    }

    historyDelete.addEventListener('click', async function () {
        var target = menuConversation;
        if (!target || busy || !ensureIdentity()) return;
        closeHistoryMenu(true);
        setBusy(true);
        historyStatus.textContent = '正在删除咨询…';
        try {
            var nextHidden = new Set(hiddenHistory); nextHidden.add(target.id);
            localStorage.setItem(hiddenHistoryKey, JSON.stringify(Array.from(nextHidden)));
            hiddenHistory = nextHidden;
            delete drafts[target.id];
            var deletingCurrent = conversation && conversation.conversation_id === target.id;
            if (!conversation) {
                try {
                    var saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
                    deletingCurrent = saved && saved.conversation_id === target.id;
                } catch (error) { /* An invalid saved reference is not an active conversation. */ }
            }
            if (deletingCurrent) {
                conversation = pending = null;
                restoreBlocked = false;
                olderCursor = null;
                sessionTitle = '';
                input.value = '';
                messages.innerHTML = initialMessage;
                sessionStorage.removeItem(storageKey);
                conversationStatus.textContent = '可开始新咨询。';
            }
            historyList.querySelectorAll('[data-conversation-id]').forEach(function (row) {
                if (row.dataset.conversationId === target.id) row.remove();
            });
            updateSession();
            historyStatus.textContent = historyList.children.length ? '对话已移出列表。' :
                (historyCursor ? '本页咨询已删除，可加载更多咨询。' : '还没有已保存的咨询。');
        } catch (error) {
            if (sameIdentity()) historyStatus.textContent = error.message || '删除失败，请稍后重试。';
        } finally {
            setBusy(false);
            if (sameIdentity()) historyRefresh.focus();
        }
    });
    historyMenu.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' || event.key === 'Tab') {
            if (event.key === 'Escape') event.preventDefault();
            closeHistoryMenu(true);
        }
    });
    document.addEventListener('pointerdown', function (event) {
        if (!historyMenu.contains(event.target)) closeHistoryMenu(false);
    });
    window.addEventListener('resize', function () { closeHistoryMenu(false); });
    document.addEventListener('scroll', function () { closeHistoryMenu(false); }, true);

    function updateSession() {
        currentLabel.textContent = conversation ? '当前咨询：' + (sessionTitle || '历史咨询') : '当前：新咨询';
        historyOlder.hidden = !conversation || !olderCursor;
        historyOlder.parentNode.hidden = historyOlder.hidden;
        historyList.querySelectorAll('[data-conversation-id]').forEach(function (button) {
            if (conversation && button.dataset.conversationId === conversation.conversation_id) button.setAttribute('aria-current', 'true');
            else button.removeAttribute('aria-current');
        });
    }

    function saveDraft() {
        drafts[conversation ? conversation.conversation_id : 'new'] = { text: input.value, pending: pending };
    }

    function renderTurns(turns, prepend) {
        var fragment = document.createDocumentFragment();
        turns.forEach(function (turn) {
            addMessage(turn.message, 'user', fragment);
            showResult(addMessage('', 'assistant', fragment), turn.response, turn.created_at || 'unknown');
        });
        if (prepend) messages.insertBefore(fragment, messages.firstChild);
        else messages.appendChild(fragment);
    }

    async function loadConversation(id) {
        var result = await api('conversations/' + encodeURIComponent(id) + '/?limit=20');
        saveDraft();
        conversation = { conversation_id: result.conversation_id, revision: result.revision };
        sessionTitle = result.title;
        var draft = drafts[result.conversation_id];
        input.value = draft ? draft.text : '';
        pending = draft ? draft.pending : null;
        selectedBundle = null;
        sessionStorage.setItem(storageKey, JSON.stringify(conversation));
        olderCursor = result.next_before_sequence || null;
        restoreBlocked = false;
        messages.innerHTML = result.turns.length ? '' : initialMessage;
        renderTurns(result.turns, false);
        updateSession();
        conversationStatus.textContent = '已打开历史咨询；旧回复仅供回看，可继续提问。';
        messages.scrollTop = messages.scrollHeight;
    }

    async function switchConversation(id) {
        if (busy || !ensureIdentity()) return;
        setBusy(true);
        historyStatus.textContent = '正在打开咨询…';
        try {
            await loadConversation(id);
            closeHistory();
            input.focus();
        } catch (error) {
            historyStatus.textContent = error.message || '咨询加载失败，请重试。';
        } finally { setBusy(false); }
    }

    async function loadHistory(reset) {
        if (busy || !ensureIdentity()) return;
        setBusy(true);
        historyList.setAttribute('aria-busy', 'true');
        historyStatus.textContent = '正在加载历史咨询…';
        try {
            var path = 'conversations/?limit=20' + (!reset && historyCursor ? '&cursor=' + encodeURIComponent(historyCursor) : '');
            var result = await api(path);
            if (reset) historyList.textContent = '';
            result.conversations.forEach(function (item) {
                if (hiddenHistory.has(item.conversation_id)) return;
                if (Array.from(historyList.children).some(function (row) { return row.dataset.conversationId === item.conversation_id; })) return;
                var button = document.createElement('button');
                button.type = 'button';
                button.className = 'bs-history-item';
                button.dataset.conversationId = item.conversation_id;
                button.setAttribute('aria-haspopup', 'menu');
                button.setAttribute('aria-controls', 'bs-history-menu');
                button.setAttribute('aria-expanded', 'false');
                var title = document.createElement('strong');
                title.textContent = item.title;
                var detail = document.createElement('small');
                detail.textContent = displayTime(item.updated_at) + ' · ' + item.turn_count + ' 轮';
                button.appendChild(title);
                button.appendChild(detail);
                button.addEventListener('click', function () { switchConversation(item.conversation_id); });
                button.addEventListener('contextmenu', function (event) { openHistoryMenu(event, item, button, false); });
                button.addEventListener('keydown', function (event) {
                    if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
                        openHistoryMenu(event, item, button, true);
                    }
                });
                historyList.appendChild(button);
            });
            historyCursor = result.next_cursor || null;
            historyMore.hidden = !historyCursor;
            historyLoaded = true;
            historyStatus.textContent = historyList.children.length ? '按最近更新时间排序，点击咨询可继续聊天。' : '还没有已保存的咨询，发送第一条消息后会自动保存。';
            updateSession();
        } catch (error) {
            historyStatus.textContent = error.message || '历史咨询加载失败，请刷新列表重试。';
        } finally {
            historyList.setAttribute('aria-busy', 'false');
            setBusy(false);
        }
    }

    async function loadOlder() {
        if (busy || !ensureIdentity() || !conversation || !olderCursor) return;
        setBusy(true);
        var previousHeight = messages.scrollHeight;
        var previousTop = messages.scrollTop;
        conversationStatus.textContent = '正在加载更早记录…';
        try {
            var result = await api('conversations/' + encodeURIComponent(conversation.conversation_id) + '/?limit=20&before_sequence=' + olderCursor);
            renderTurns(result.turns, true);
            olderCursor = result.next_before_sequence || null;
            updateSession();
            messages.scrollTop = previousTop + messages.scrollHeight - previousHeight;
            conversationStatus.textContent = olderCursor ? '已加载更早记录，可继续向前查看。' : '已显示该咨询的全部记录。';
            // Loading older pages does not advance the revision of the latest
            // messages shown here; an external update must still cause 409.
        } catch (error) {
            conversationStatus.textContent = error.message || '更早记录加载失败，请重试。';
        } finally { setBusy(false); }
    }

    async function restoreConversation() {
        var saved;
        try { saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null'); }
        catch (error) { sessionStorage.removeItem(storageKey); return; }
        if (!saved || !saved.conversation_id) return;
        if (hiddenHistory.has(saved.conversation_id)) { sessionStorage.removeItem(storageKey); return; }
        try {
            await loadConversation(saved.conversation_id);
        } catch (error) {
            if (error.status === 404 || error.status === 401) {
                sessionStorage.removeItem(storageKey);
                conversation = null;
                restoreBlocked = false;
            } else {
                restoreBlocked = true;
                conversationStatus.textContent = '原咨询尚未恢复，请从历史咨询重新打开，或明确开始新对话。';
            }
            throw error;
        }
    }

    input.addEventListener('compositionstart', function () { composing = true; });
    input.addEventListener('compositionend', function () { composing = false; });
    input.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' || event.shiftKey || composing || event.isComposing || event.keyCode === 229) return;
        event.preventDefault();
        if (busy || restoreBlocked || event.repeat) return;
        form.requestSubmit(send);
    });

    form.addEventListener('submit', async function (event) {
        event.preventDefault();
        var question = input.value.trim();
        if (busy || restoreBlocked || !question) return;
        try { checkIdentity(); }
        catch (error) { return; }
        if (!AuthStorage.getToken()) { addMessage('请先登录后再使用智能客服。', 'assistant'); return; }
        setBusy(true);
        input.value = '';
        addMessage(question, 'user');
        var waiting = addMessage('正在整理回复，请稍候…', 'assistant');
        try {
            if (!pending || pending.message !== question) {
                pending = { message: question, request_id: uuid() };
                if (conversation) {
                    pending.conversation_id = conversation.conversation_id;
                    pending.expected_revision = conversation.revision;
                    if (selectedBundle) pending.bundle_selection = Object.assign({}, selectedBundle);
                }
            }
            var result = await api('chat/', 'POST', pending);
            if (!conversation) sessionTitle = question.replace(/\s+/g, ' ').slice(0, 60);
            conversation = { conversation_id: result.conversation_id, revision: result.revision };
            sessionStorage.setItem(storageKey, JSON.stringify(conversation));
            pending = null;
            selectedBundle = null;
            showResult(waiting, result);
            updateSession();
            conversationStatus.textContent = '咨询已保存，可在“历史咨询”中找回。';
            historyLoaded = false;
        } catch (error) {
            if (!sameIdentity()) return;
            waiting.textContent = error.message || '网络连接失败，请稍后重试。';
            input.value = question;
            conversationStatus.textContent = (error.errorCode || '').indexOf('MEMORY_STORAGE_') === 0 ?
                '长期偏好服务异常；恢复后可继续当前咨询，无须新建对话。' :
                '本轮未收到成功回复，可重试原问题或输入新问题。';
            // Keep the ID only for uncertain network/5xx outcomes, so a retry
            // can replay a possibly committed response without adding a turn.
            if (error.status && error.status < 500) pending = null;
            if (error.status === 404) selectedBundle = null;
            if (error.status === 409) {
                pending = null;
                try { await restoreConversation(); addMessage('会话已刷新，请重新发送问题。', 'assistant'); }
                catch (restoreError) { addMessage(restoreError.message, 'assistant'); }
            }
        } finally {
            setBusy(false);
            input.focus();
            messages.scrollTop = messages.scrollHeight;
            if (!historyPanel.hidden && !historyLoaded && sameIdentity()) loadHistory(true);
        }
    });

    newConversation.addEventListener('click', function () {
        if (busy || !ensureIdentity()) return;
        saveDraft();
        conversation = null;
        pending = null;
        selectedBundle = null;
        restoreBlocked = false;
        sessionStorage.removeItem(storageKey);
        messages.innerHTML = initialMessage;
        sessionTitle = '';
        olderCursor = null;
        input.value = '';
        delete drafts.new;
        updateSession();
        conversationStatus.textContent = '已开启新咨询，旧咨询仍可从“历史咨询”进入。';
        historyLoaded = false;
        input.focus();
        if (!historyPanel.hidden) loadHistory(true);
    });

    historyToggle.addEventListener('click', function () {
        if (busy || !ensureIdentity()) return;
        if (!historyPanel.hidden) { closeHistory(); return; }
        historyPanel.hidden = false;
        historyToggle.setAttribute('aria-expanded', 'true');
        if (!historyLoaded) loadHistory(true);
    });
    historyRefresh.addEventListener('click', function () { loadHistory(true); });
    historyMore.addEventListener('click', function () { if (historyCursor) loadHistory(false); });
    historyOlder.addEventListener('click', loadOlder);
    historyPanel.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') { closeHistory(); historyToggle.focus(); }
    });
    window.addEventListener('storage', function () {
        if (!sameIdentity()) { try { checkIdentity(); } catch (error) { /* Page awaits refresh. */ } }
    });

    function fillPreferences(values) {
        Object.keys(preferenceFields).forEach(function (field) {
            preferenceFields[field].value = (values[field] || []).join('，');
        });
    }

    async function updatePreferences(method) {
        var values = {};
        Object.keys(preferenceFields).forEach(function (field) {
            values[field] = preferenceFields[field].value.split(/[,，\n]/).map(function (term) { return term.trim(); }).filter(Boolean);
        });
        var buttons = preferenceForm.querySelectorAll('button');
        buttons.forEach(function (button) { button.disabled = true; });
        try {
            var result = await api('preferences/', method, method === 'DELETE' ? undefined : values);
            fillPreferences(result.preferences);
            preferenceStatus.textContent = method === 'DELETE' ? '长期偏好已清除。' : '长期偏好已保存。';
        } catch (error) { preferenceStatus.textContent = error.message; }
        finally { buttons.forEach(function (button) { button.disabled = false; }); }
    }
    preferenceForm.addEventListener('submit', function (event) { event.preventDefault(); updatePreferences('PUT'); });
    document.getElementById('bs-clear-preferences').addEventListener('click', function () { updatePreferences('DELETE'); });
    document.querySelectorAll('.bs-suggestions button').forEach(function (button) {
        button.addEventListener('click', function () { input.value = button.getAttribute('data-question') || ''; input.focus(); });
    });

    if (AuthStorage.getToken()) {
        setBusy(true);
        restoreConversation().catch(function (error) { addMessage(error.message, 'assistant'); }).finally(function () { setBusy(false); });
        api('preferences/').then(function (result) { fillPreferences(result.preferences); })
            .catch(function (error) { preferenceStatus.textContent = error.message; });
    }
    document.getElementById('currency-select').addEventListener('change', function () {
        messages.querySelectorAll('[data-base-price]').forEach(function (node) {
            node.textContent = shownMoney(node.dataset.basePrice, 'CNY') + ' · ' + node.dataset.category;
        });
        messages.querySelectorAll('.bs-bundles').forEach(function (node) { node.dispatchEvent(new Event('support-currency-change')); });
    });
    updateSession();
})();
