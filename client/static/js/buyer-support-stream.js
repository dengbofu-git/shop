/* SSE over an authenticated POST. No automatic reconnect or duplicate submission. */
(function (root) {
    'use strict';
    function failure(message, status, code) {
        var error = new Error(message);
        error.status = status || 0;
        error.errorCode = code || '';
        return error;
    }
    function parser(deliver) {
        var buffer = '';
        return function (text, eof) {
            buffer += text;
            if (buffer.length > 1048576) throw failure('回复数据过长，请重试。');
            // Each delimiter can itself straddle network chunks, including CRLF.
            var match;
            while ((match = /\r?\n\r?\n/.exec(buffer))) {
                var block = buffer.slice(0, match.index);
                buffer = buffer.slice(match.index + match[0].length);
                var event = 'message', data = [];
                block.split(/\r?\n/).forEach(function (line) {
                    if (line.indexOf('event:') === 0) event = line.slice(6).trim();
                    if (line.indexOf('data:') === 0) data.push(line.slice(5).replace(/^ /, ''));
                });
                if (!data.length || ['status', 'answer', 'ping', 'error', 'done'].indexOf(event) < 0) continue;
                var value;
                try { value = JSON.parse(data.join('\n')); }
                catch (_) { throw failure('回复数据异常，请重试。'); }
                if (!value || typeof value !== 'object' || Array.isArray(value)) throw failure('回复格式异常，请重试。');
                deliver(event, value);
            }
            if (eof && buffer.trim()) throw failure('回复连接中断，可重试原问题。');
        };
    }
    async function chat(data, options) {
        var reader, terminal = false, result;
        options.checkIdentity();
        try {
            var response = await fetch('/v1/support/chat/', {
                method: 'POST', signal: options.signal,
                headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream',
                    'Authorization': 'Bearer ' + options.token },
                body: JSON.stringify(data)
            });
            options.checkIdentity();
            if (!response.ok || !(response.headers.get('Content-Type') || '').includes('text/event-stream')) {
                try { result = await response.json(); }
                catch (_) { options.checkIdentity(); throw failure('服务响应异常，请稍后重试。'); }
                options.checkIdentity();
                if (!result || typeof result !== 'object' || Array.isArray(result)) throw failure('回复格式异常，请重试。');
                if (!response.ok) throw failure(result.error || '暂时无法回答，请重试。', response.status, result.error_code);
                if (typeof result.answer !== 'string') throw failure('回复格式异常，请重试。');
                return result; // Compatibility with an older JSON server.
            }
            if (!response.body || !response.body.getReader) throw failure('当前浏览器不支持流式回复，请更新浏览器。');
            reader = response.body.getReader();
            var decoder = new TextDecoder('utf-8', { fatal: true });
            var accept = parser(function (event, value) {
                options.checkIdentity();
                if (terminal) throw failure('回复结束标记异常，请重试。');
                if (event === 'error') throw failure(value.error || '暂时无法回答，请重试。', value.status, value.error_code);
                if (event === 'done') {
                    if (typeof value.answer !== 'string' || typeof value.conversation_id !== 'string' ||
                        !Number.isInteger(value.revision)) throw failure('回复保存信息异常，请重试。');
                    terminal = true;
                    result = value;
                } else if (event === 'status' && typeof value.message === 'string') {
                    options.onStatus(value.message);
                } else if (event === 'answer' && typeof value.text === 'string') {
                    options.onAnswer(value.text);
                }
            });
            while (!terminal) {
                var chunk = await reader.read();
                options.checkIdentity();
                accept(decoder.decode(chunk.value, { stream: !chunk.done }), chunk.done);
                if (chunk.done) break;
            }
            if (!terminal) throw failure('回复连接中断，可重试原问题；已保存的回复会自动找回。');
            return result;
        } finally {
            if (reader) {
                try { await reader.cancel(); } catch (_) { /* The network may already be closed. */ }
                reader.releaseLock();
            }
        }
    }
    var api = { chat: chat, parser: parser };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.SupportStream = api;
}(typeof window === 'undefined' ? globalThis : window));
