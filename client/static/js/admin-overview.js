PlatformAccess.requirePermission(['data_view', 'system_config', 'user_manage']).then(function (allowed) {
    'use strict';
    if (!allowed) return;
    var $ = function (id) { return document.getElementById(id); };
    var money = function (value) {
        return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value));
    };
    var number = function (value) { return Number(value).toLocaleString('zh-CN'); };
    var fields = ['total_sales', 'total_flow', 'order_count', 'paid_order_count', 'buyer_count', 'merchant_count'];

    function cell(row, value) {
        var td = document.createElement('td');
        td.textContent = value;
        row.appendChild(td);
    }

    function render(data) {
        fields.forEach(function (key) {
            $(key).textContent = key === 'total_sales' || key === 'total_flow' ? money(data.summary[key]) : number(data.summary[key]);
        });
        $('overview-updated').textContent = '更新于 ' + new Date(data.updated_at).toLocaleString('zh-CN', { hour12: false });
        var chart = $('sales-chart'), rows = $('daily-rows'), states = $('order-states');
        chart.replaceChildren(); rows.replaceChildren(); states.replaceChildren();
        var maximum = Math.max.apply(null, data.daily.map(function (day) { return Number(day.sales); }));
        chart.className = maximum > 0 ? 'overview-chart' : 'overview-zero muted';
        if (maximum <= 0) chart.textContent = '近 30 天暂无销售额';
        data.daily.forEach(function (day) {
            if (maximum > 0) {
                var column = document.createElement('div'), bar = document.createElement('div');
                column.className = 'overview-day';
                column.title = day.date + '：' + money(day.sales);
                column.setAttribute('aria-hidden', 'true');
                bar.className = 'overview-bar';
                bar.style.height = Math.max(0, Number(day.sales) / maximum * 100) + '%';
                column.appendChild(bar); chart.appendChild(column);
            }
            var row = document.createElement('tr');
            cell(row, day.date); cell(row, money(day.sales)); cell(row, money(day.flow)); cell(row, number(day.order_count));
            rows.prepend(row);
        });
        $('trend-start').textContent = data.daily[0].date;
        $('trend-end').textContent = data.daily[data.daily.length - 1].date;
        $('trend-peak').textContent = '单日最高 ' + money(maximum);
        data.states.forEach(function (state) {
            var row = document.createElement('div'), name = document.createElement('span'), count = document.createElement('strong');
            row.className = 'overview-state'; name.textContent = state.name; count.textContent = number(state.count);
            row.appendChild(name); row.appendChild(count); states.appendChild(row);
        });
    }

    async function load() {
        var button = $('refresh-overview'), status = $('overview-status');
        button.disabled = true;
        status.className = 'message muted'; status.textContent = '正在读取平台交易数据…';
        try {
            var response = await fetch('/v1/admin-panel/overview', {
                headers: { Authorization: 'Bearer ' + AuthStorage.getToken() }, cache: 'no-store'
            });
            if (response.status === 401 || response.status === 403) {
                location.replace('/login.html'); return;
            }
            var result = await response.json();
            if (!response.ok || result.code !== 200) throw new Error(result.error || '交易数据读取失败');
            render(result.data); status.textContent = '';
        } catch (error) {
            fields.forEach(function (key) { $(key).textContent = '—'; });
            $('sales-chart').replaceChildren(); $('daily-rows').replaceChildren(); $('order-states').replaceChildren();
            $('overview-updated').textContent = '数据未更新';
            ['trend-start', 'trend-end', 'trend-peak'].forEach(function (id) { $(id).textContent = ''; });
            status.className = 'message overview-error';
            status.textContent = (error.message || '交易数据读取失败') + '，请点击刷新重试。';
        } finally { button.disabled = false; }
    }
    $('refresh-overview').addEventListener('click', load);
    $('btn-admin-logout').addEventListener('click', function () { AuthStorage.clear(); location.href = '/login.html'; });
    var sections = {
        overview: { permission: 'data_view', title: '交易总览' },
        agents: { permission: 'system_config', title: 'Agent 管理', url: '/admin_agents.html?embedded=1' },
        users: { permission: 'user_manage', title: '账号管理', url: '/admin_users.html?embedded=1' }
    };
    var permissions = PlatformAccess.currentAccess.permissions;
    var currentSection = null;
    function route() {
        var section = location.hash.slice(1);
        if (!Object.prototype.hasOwnProperty.call(sections, section) || permissions.indexOf(sections[section].permission) === -1) {
            section = ['overview', 'users', 'agents'].find(function (key) { return permissions.indexOf(sections[key].permission) !== -1; });
            history.replaceState(null, '', '#'+section);
        }
        if (section === currentSection) return;
        currentSection = section;
        document.title = '平台运营 · ' + sections[section].title;
        document.querySelectorAll('[data-platform-section]').forEach(function (link) {
            if (link.dataset.platformSection === section) link.setAttribute('aria-current', 'page');
            else link.removeAttribute('aria-current');
        });
        var overview = section === 'overview', frame = $('platform-workspace');
        $('overview-content').hidden = !overview;
        $('workspace-content').hidden = overview;
        if (overview) {
            frame.contentWindow.location.replace('about:blank');
            load();
        } else {
            frame.title = sections[section].title;
            // Keep each workspace change in the parent hash history only.
            frame.contentWindow.location.replace(sections[section].url);
        }
    }
    window.addEventListener('hashchange', route);
    route();
});
