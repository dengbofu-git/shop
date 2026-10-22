PlatformAccess.requirePermission('system_config').then(function (allowed) {
    'use strict';
    if (!allowed) return;
    var token = AuthStorage.getToken();
    if (!token) { location.href = '/login.html'; return; }
    var config = null, page = 1, total = 0, loading = false;
    var $ = function (id) { return document.getElementById(id); };
    var intents = { question_answering: '咨询问答', recommendation: '商品推荐', recommendation_explanation: '推荐理由', product_details: '商品详情', after_sales: '订单售后', clarification: '补充信息', multi_intent: '多任务', unavailable: '其他问题' };
    function element(tag, text, cls) { var el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; }
    function message(id, text, error) { $(id).textContent = text || ''; $(id).className = 'message ' + (error ? 'error' : 'ok'); }
    function number(value) { return Number(value || 0).toLocaleString('zh-CN'); }
    function date(value) { return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'; }
    async function api(path, method, body) {
        var response = await fetch('/v1/admin-panel/agent/' + path, { method: method || 'GET', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
        var data = await response.json();
        if (!response.ok) throw new Error(data.error || '请求失败，请稍后重试');
        return data;
    }
    function modelOption(id) { if (!Array.from($('agent-model').options).some(function (o) { return o.value === id; })) $('agent-model').appendChild(new Option(id, id)); }
    function fillSettings(data) {
        config = data.settings;
        modelOption(config.model); $('agent-model').value = config.model;
        $('thinking').value = config.thinking;
        $('telemetry-enabled').checked = config.telemetry_enabled;
        $('export-enabled').checked = config.export_enabled;
        $('otlp-endpoint').value = config.otlp_endpoint;
        $('rerank-enabled').checked = config.rerank_enabled;
        $('rerank-fallback').checked = config.rerank_fallback;
        $('rerank-model').replaceChildren();
        (data.rerank_models || [config.rerank_model]).forEach(function (model) { $('rerank-model').appendChild(new Option(model, model)); });
        $('rerank-model').value = config.rerank_model;
        ['retrieval_candidates', 'retrieval_top_k', 'retrieval_per_document', 'retrieval_context_chars', 'rerank_timeout_ms', 'rerank_min_score'].forEach(function (key) { $(key.replaceAll('_', '-')).value = config[key] === null ? '' : config[key]; });
        $('current-model').textContent = config.model;
        $('config-revision').textContent = '版本 ' + config.revision;
        $('config-history').replaceChildren();
        (data.history || []).forEach(function (item) {
            var row = element('div'); row.appendChild(element('strong', item.operator + ' · ' + date(item.created_at)));
            row.appendChild(element('p', item.before.model + ' → ' + item.after.model));
            row.appendChild(element('p', '版本 ' + item.after.revision + ' · 监控' + (item.after.telemetry_enabled ? '开启' : '关闭') + ' · OTLP' + (item.after.export_enabled ? '开启' : '关闭')));
            if (item.after.rerank_model) row.appendChild(element('p', '重排序' + (item.after.rerank_enabled ? '开启' : '关闭') + ' · ' + item.after.rerank_model + ' · ' + item.after.retrieval_candidates + ' → ' + item.after.retrieval_top_k));
            $('config-history').appendChild(row);
        });
        if (!(data.history || []).length) $('config-history').textContent = '暂无变更记录';
        if (!data.api_key_configured) message('page-status', '服务器尚未配置 DeepSeek API Key，模型调用暂不可用。', true);
    }
    async function loadSettings() { fillSettings(await api('settings')); }
    async function loadReranker() {
        $('refresh-reranker').disabled = true;
        try {
            var service = (await api('retrieval-status')).service;
            var names = {ready: '已就绪', loading: '模型下载或预热中', error: '模型加载失败', unavailable: '服务不可达', version_mismatch: '模型版本不匹配'};
            $('rerank-service-status').textContent = (names[service.status] || '状态未知') + (service.device ? ' · ' + service.device.toUpperCase() : '') + (service.revision ? ' · ' + service.revision.slice(0, 8) : '');
            $('rerank-service-status').className = service.status === 'ready' ? 'ok' : 'muted';
        } catch (error) { $('rerank-service-status').textContent = error.message; }
        finally { $('refresh-reranker').disabled = false; }
    }
    async function loadModels() {
        $('refresh-models').disabled = true;
        try {
            var data = await api('models'), selected = $('agent-model').value || data.current;
            $('agent-model').replaceChildren();
            data.models.forEach(modelOption); modelOption(selected); $('agent-model').value = selected;
            $('model-status').textContent = '已读取 DeepSeek 官方可用模型列表（' + data.models.length + ' 个）。';
        } catch (error) { $('model-status').textContent = error.message; }
        finally { $('refresh-models').disabled = false; }
    }
    var metricNoteId = 0;
    function metric(label, value, caption) {
        var box = element('div', undefined, 'metric metric-help');
        var note = element('span', caption, 'metric-tooltip'); note.id = 'agent-metric-note-' + (++metricNoteId); note.setAttribute('role', 'tooltip');
        var help = element('button', 'i', 'metric-info'); help.type = 'button';
        help.setAttribute('aria-label', label + '说明'); help.setAttribute('aria-describedby', note.id);
        box.append(element('small', label), element('strong', value), help, note);
        help.addEventListener('click', function () {
            var open = !box.classList.contains('is-tooltip-open');
            box.classList.toggle('is-tooltip-open', open); box.classList.toggle('is-tooltip-dismissed', !open);
        });
        help.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') { event.preventDefault(); box.classList.remove('is-tooltip-open'); box.classList.add('is-tooltip-dismissed'); }
        });
        help.addEventListener('blur', function () { box.classList.remove('is-tooltip-open', 'is-tooltip-dismissed'); });
        box.addEventListener('mouseleave', function () { box.classList.remove('is-tooltip-dismissed'); });
        return box;
    }
    document.addEventListener('click', function (event) {
        $('metrics').querySelectorAll('.metric-help').forEach(function (box) {
            if (!box.contains(event.target)) box.classList.remove('is-tooltip-open', 'is-tooltip-dismissed');
        });
    });
    async function loadMonitoring() {
        if (loading) return;
        loading = true; $('refresh-monitor').disabled = true;
        try {
            var data = await api('monitoring?hours=' + $('time-window').value + '&page=' + page), s = data.summary;
            total = data.total; $('metrics').replaceChildren();
            [metric('Agent 请求', number(s.requests), number(s.model_calls) + ' 次模型调用'), metric('请求成功率', s.success_rate === null ? '—' : s.success_rate + '%', number(s.errors) + ' 次执行失败'), metric('平均响应耗时', (s.average_ms / 1000).toFixed(2) + 's', 'Agent 工作流耗时'), metric('输入 Token', number(s.input_tokens), '模型返回的实际用量'), metric('输出 Token', number(s.output_tokens), '模型返回的实际用量'), metric('知识检索命中', number(s.retrieval_hits), number(s.retrieval_errors) + ' 次检索异常 · ' + number(s.blocked) + ' 次安全拦截')].forEach(function (card) { $('metrics').appendChild(card); });
            var rerank = data.reranking;
            if (rerank) [metric('重排序调用', number(rerank.calls), number(rerank.errors) + ' 次失败 · ' + rerank.error_rate + '%'), metric('重排序平均耗时', (rerank.average_ms / 1000).toFixed(2) + 's', number(rerank.fallbacks) + ' 次降级 · ' + rerank.fallback_rate + '%'), metric('重排序 P95', (rerank.p95_ms / 1000).toFixed(2) + 's', '最近最多 10,000 次调用')].forEach(function (card) { $('metrics').appendChild(card); });
            var health = data.export_status, names = { success: '正常', error: '失败', waiting: '等待首批数据', disabled: '未启用' };
            $('export-status').textContent = !data.telemetry_enabled ? 'Agent 监控已关闭，以下为历史记录' : !health.initialized ? '等待首个 Agent 请求初始化采集' : !health.export_enabled ? '本地采集运行中 · OTLP 导出未启用' : 'OTLP 链路：' + names[health.trace_export_status] + ' · 指标：' + names[health.metric_export_status] + ' · 最近链路导出 ' + date(health.trace_export_at);
            $('export-status').className = health.trace_export_status === 'error' || health.metric_export_status === 'error' ? 'error' : 'ok';
            $('model-distribution').textContent = Object.keys(data.per_model).map(function (key) { return key + ' · ' + data.per_model[key] + ' 次'; }).join(' / ');
            $('trace-rows').replaceChildren();
            data.traces.forEach(function (trace) {
                var attrs = trace.attributes, row = element('tr');
                row.appendChild(element('td', date(trace.started_at)));
                var model = element('td', attrs['gen_ai.request.model']); model.appendChild(element('small', intents[attrs['agent.intent']] || attrs['agent.intent'] || '未完成')); row.appendChild(model);
                var status = element('td'); status.appendChild(element('span', trace.status === 'ERROR' ? '执行失败' : attrs['agent.compliance.blocked'] ? '安全拦截' : '完成', 'status ' + (trace.status === 'ERROR' ? 'error' : 'ok'))); row.appendChild(status);
                row.appendChild(element('td', (trace.duration_ms / 1000).toFixed(2) + 's'));
                row.appendChild(element('td', number(attrs['gen_ai.usage.input_tokens']) + ' / ' + number(attrs['gen_ai.usage.output_tokens'])));
                var action = element('td'), button = element('button', '查看链路', 'link-button'); button.type = 'button'; button.addEventListener('click', function () { showTrace(trace.trace_id); }); action.appendChild(button); row.appendChild(action);
                $('trace-rows').appendChild(row);
            });
            if (!data.traces.length) { var empty = element('td', '暂无记录。启用监控后，向茶品智能助手发送一个问题即可生成链路。', 'empty'); empty.colSpan = 6; var row = element('tr'); row.appendChild(empty); $('trace-rows').appendChild(row); }
            $('trace-count').textContent = '共 ' + number(total) + ' 次请求 · 第 ' + page + ' 页';
            $('previous-page').disabled = page <= 1; $('next-page').disabled = page * 20 >= total;
            message('page-status', '');
        } catch (error) { message('page-status', error.message, true); }
        finally { loading = false; $('refresh-monitor').disabled = false; }
    }
    async function showTrace(id) {
        $('trace-detail').showModal(); $('detail-trace-id').textContent = id; $('span-list').replaceChildren(); message('detail-status', '读取链路中…');
        try {
            var data = await api('traces/' + id), root = data.spans.find(function (s) { return !s.parent_span_id; }) || data.spans[0], start = new Date(root.started_at).getTime();
            data.spans.forEach(function (span) {
                var depth = 0, parent = span.parent_span_id;
                while (parent && depth < 8) { var match = data.spans.find(function (s) { return s.span_id === parent; }); if (!match) break; depth++; parent = match.parent_span_id; }
                var row = element('div', undefined, 'span-row ' + (span.status === 'ERROR' ? 'error' : ''));
                row.style.marginLeft = depth * 14 + 'px';
                var title = element('div', undefined, 'span-title'); title.appendChild(element('strong', span.name)); title.appendChild(element('span', span.status + ' · ' + span.duration_ms.toFixed(1) + 'ms')); row.appendChild(title);
                var bar = element('div', undefined, 'span-bar'), fill = element('span');
                fill.style.width = Math.max(.5, Math.min(100, span.duration_ms / Math.max(root.duration_ms, 1) * 100)) + '%';
                fill.style.marginLeft = Math.min(99, Math.max(0, (new Date(span.started_at).getTime() - start) / Math.max(root.duration_ms, 1) * 100)) + '%'; bar.appendChild(fill); row.appendChild(bar);
                row.appendChild(element('div', Object.keys(span.attributes).map(function (key) { return key + ': ' + span.attributes[key]; }).join('\n'), 'span-attrs'));
                if (span.name === 'knowledge.rerank' && span.attributes['agent.rerank.output_ids']) {
                    var inputs = span.attributes['agent.rerank.input_ids'], outputs = span.attributes['agent.rerank.output_ids'], scores = span.attributes['agent.rerank.scores'];
                    var table = element('table'), head = element('tr');
                    ['片段 ID', '召回候选排名', '重排序排名', '相关性分数'].forEach(function (label) { head.appendChild(element('th', label)); });
                    var thead = element('thead'); thead.appendChild(head); table.appendChild(thead);
                    var tbody = element('tbody');
                    outputs.forEach(function (chunk, index) { var item = element('tr'); [chunk, inputs.indexOf(chunk) + 1, index + 1, Number(scores[index]).toFixed(4)].forEach(function (value) { item.appendChild(element('td', value)); }); tbody.appendChild(item); });
                    table.appendChild(tbody); var wrapper = element('div', undefined, 'table-wrap'); wrapper.appendChild(table); row.appendChild(wrapper);
                }
                $('span-list').appendChild(row);
            }); message('detail-status', '');
        } catch (error) { message('detail-status', error.message, true); }
    }
    $('agent-settings').addEventListener('submit', async function (event) {
        event.preventDefault(); if (!config) return;
        $('save-settings').disabled = true; message('settings-status', '正在保存…');
        try {
            var settings = { model: $('agent-model').value, thinking: $('thinking').value, telemetry_enabled: $('telemetry-enabled').checked, export_enabled: $('export-enabled').checked, otlp_endpoint: $('otlp-endpoint').value.trim(), revision: config.revision,
                rerank_enabled: $('rerank-enabled').checked, rerank_fallback: $('rerank-fallback').checked, rerank_model: $('rerank-model').value };
            ['retrieval_candidates', 'retrieval_top_k', 'retrieval_per_document', 'retrieval_context_chars', 'rerank_timeout_ms', 'rerank_min_score'].forEach(function (key) { var value = $(key.replaceAll('_', '-')).value; settings[key] = value === '' && key === 'rerank_min_score' ? null : Number(value); });
            await api('settings', 'PUT', settings);
            await loadSettings(); message('settings-status', '已保存，新请求将使用新设置。'); loadMonitoring();
        } catch (error) { message('settings-status', error.message, true); }
        finally { $('save-settings').disabled = false; }
    });
    $('refresh-models').addEventListener('click', loadModels);
    $('refresh-reranker').addEventListener('click', loadReranker);
    $('refresh-monitor').addEventListener('click', loadMonitoring);
    $('time-window').addEventListener('change', function () { page = 1; loadMonitoring(); });
    $('previous-page').addEventListener('click', function () { if (!loading && page > 1) { page--; loadMonitoring(); } });
    $('next-page').addEventListener('click', function () { if (!loading && page * 20 < total) { page++; loadMonitoring(); } });
    $('close-trace').addEventListener('click', function () { $('trace-detail').close(); });
    loadSettings().then(loadModels).catch(function (error) { message('page-status', error.message, true); });
    loadMonitoring(); loadReranker(); setInterval(function () { if (!document.hidden) { loadMonitoring(); loadReranker(); } }, 30000);
});
