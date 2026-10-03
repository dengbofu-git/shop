/**
 * 平台运营后台 - 买家/茶企账号 CRUD
 */
(function () {
    'use strict';

    var token = AuthStorage.getToken();
    if (!token) {
        alert('请先使用平台运营账号登录');
        location.href = 'login.html';
        return;
    }

    var listFilterType = '';
    var apiHeaders = { Authorization: token, 'Content-Type': 'application/json' };

    function setCreateMsg(text, ok) {
        var $el = $('#user-create-msg');
        $el.text(text || '').removeClass('ok err');
        if (text) $el.addClass(ok ? 'ok' : 'err');
    }

    function toggleCreateShopField() {
        var isMerchant = $('#user-type').val() === 'merchant';
        $('#create-shop-wrap').toggle(isMerchant);
    }

    function loadUsers() {
        var keyword = ($('#user-keyword').val() || '').trim();
        var url = baseUrl + '/v1/admin-panel/users?';
        if (listFilterType) url += 'user_type=' + encodeURIComponent(listFilterType) + '&';
        if (keyword) url += 'keyword=' + encodeURIComponent(keyword);

        $('#user-list').html('<p class="pa-tip">加载中…</p>');
        $.ajax({
            url: url,
            headers: { Authorization: token },
            success: function (r) {
                if (r.code !== 200) {
                    $('#user-list').html('<p class="pa-msg err">' + (r.error || '加载失败') + '</p>');
                    return;
                }
                var list = r.data || [];
                if (!list.length) {
                    $('#user-list').html('<p class="pa-tip">暂无账号</p>');
                    return;
                }
                var html = '<table class="pa-table"><thead><tr>' +
                    '<th>账号</th><th>类型</th><th>邮箱</th><th>手机</th><th>店铺</th><th>状态</th><th>注册时间</th><th>操作</th>' +
                    '</tr></thead><tbody>';
                list.forEach(function (u) {
                    var typeCls = u.user_type === 'merchant' ? 'pa-badge-merchant' : 'pa-badge-customer';
                    var statusHtml = u.is_active
                        ? '<span class="pa-badge pa-badge-merchant">正常</span>'
                        : '<span class="pa-badge pa-badge-off">停用</span>';
                    html += '<tr data-user-id="' + u.id + '">';
                    html += '<td><strong>' + escapeHtml(u.username) + '</strong></td>';
                    html += '<td><span class="pa-badge ' + typeCls + '">' + escapeHtml(u.user_type_label) + '</span></td>';
                    html += '<td class="pa-edit-row"><input class="inp-email" value="' + escapeAttr(u.email) + '"></td>';
                    html += '<td class="pa-edit-row"><input class="inp-phone" value="' + escapeAttr(u.phone) + '"></td>';
                    html += '<td class="pa-edit-row"><input class="inp-shop" value="' + escapeAttr(u.shop_name) + '" placeholder="—"></td>';
                    html += '<td class="pa-edit-row"><select class="inp-type">' +
                        '<option value="customer"' + (u.user_type === 'customer' ? ' selected' : '') + '>买家</option>' +
                        '<option value="merchant"' + (u.user_type === 'merchant' ? ' selected' : '') + '>茶企</option>' +
                        '</select><select class="inp-active" style="margin-top:4px;">' +
                        '<option value="1"' + (u.is_active ? ' selected' : '') + '>启用</option>' +
                        '<option value="0"' + (!u.is_active ? ' selected' : '') + '>停用</option>' +
                        '</select></td>';
                    html += '<td>' + escapeHtml(u.created_time || '—') + '</td>';
                    html += '<td><button type="button" class="pa-btn pa-btn-green btn-save-user" style="padding:4px 10px;font-size:12px;margin-bottom:4px;">保存</button>' +
                        '<br><input class="inp-pwd" type="password" placeholder="新密码" maxlength="12" style="max-width:100px;margin:4px 0;">' +
                        '<br><button type="button" class="pa-btn pa-btn-danger btn-del-user" style="padding:4px 10px;font-size:12px;">删除</button></td>';
                    html += '</tr>';
                });
                html += '</tbody></table>';
                $('#user-list').html(html);

                $('.btn-save-user').on('click', function () {
                    var $tr = $(this).closest('tr');
                    saveUserRow($tr);
                });
                $('.btn-del-user').on('click', function () {
                    var $tr = $(this).closest('tr');
                    deleteUserRow($tr);
                });
            },
            error: function (xhr) {
                var msg = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : '网络错误';
                $('#user-list').html('<p class="pa-msg err">' + msg + '</p>');
            }
        });
    }

    function saveUserRow($tr) {
        var id = $tr.data('user-id');
        var payload = {
            id: id,
            email: $tr.find('.inp-email').val().trim(),
            phone: $tr.find('.inp-phone').val().trim(),
            shop_name: $tr.find('.inp-shop').val().trim(),
            user_type: $tr.find('.inp-type').val(),
            is_active: $tr.find('.inp-active').val() === '1'
        };
        var pwd = $tr.find('.inp-pwd').val();
        if (pwd) payload.password = pwd;

        $.ajax({
            url: baseUrl + '/v1/admin-panel/users',
            type: 'PUT',
            headers: apiHeaders,
            data: JSON.stringify(payload),
            success: function (r) {
                if (r.code === 200) {
                    alert('已保存');
                    $tr.find('.inp-pwd').val('');
                    loadUsers();
                } else {
                    alert(r.error || '保存失败');
                }
            },
            error: function (xhr) {
                alert((xhr.responseJSON && xhr.responseJSON.error) || '保存失败');
            }
        });
    }

    function deleteUserRow($tr) {
        var id = $tr.data('user-id');
        var name = $tr.find('strong').first().text();
        if (!confirm('确定删除账号「' + name + '」？此操作不可恢复。')) return;
        $.ajax({
            url: baseUrl + '/v1/admin-panel/users?id=' + encodeURIComponent(id),
            type: 'DELETE',
            headers: { Authorization: token },
            success: function (r) {
                if (r.code === 200) {
                    loadUsers();
                } else {
                    alert(r.error || '删除失败');
                }
            },
            error: function (xhr) {
                alert((xhr.responseJSON && xhr.responseJSON.error) || '删除失败');
            }
        });
    }

    function escapeHtml(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    }

    function escapeAttr(s) {
        return escapeHtml(s).replace(/'/g, '&#39;');
    }

    $('#btn-add-user').on('click', function () {
        var username = $('#user-username').val().trim();
        var password = $('#user-password').val();
        var email = $('#user-email').val().trim();
        var phone = $('#user-phone').val().trim();
        var userType = $('#user-type').val();
        var shopName = $('#user-shop-name').val().trim();

        if (!username || !password) {
            setCreateMsg('请填写账号与密码', false);
            return;
        }
        var body = {
            username: username,
            password: password,
            email: email,
            phone: phone,
            user_type: userType
        };
        if (userType === 'merchant') body.shop_name = shopName;

        $.ajax({
            url: baseUrl + '/v1/admin-panel/users',
            type: 'POST',
            headers: apiHeaders,
            data: JSON.stringify(body),
            success: function (r) {
                if (r.code === 200) {
                    setCreateMsg('创建成功：' + r.data.username, true);
                    $('#user-username, #user-password, #user-email, #user-phone, #user-shop-name').val('');
                    loadUsers();
                } else {
                    setCreateMsg(r.error || '创建失败', false);
                }
            },
            error: function (xhr) {
                setCreateMsg((xhr.responseJSON && xhr.responseJSON.error) || '创建失败', false);
            }
        });
    });

    $('#user-type').on('change', toggleCreateShopField);

    $('.pa-list-tabs .register-role-tab').on('click', function () {
        $('.pa-list-tabs .register-role-tab').removeClass('active');
        $(this).addClass('active');
        listFilterType = $(this).data('filter-type') || '';
        loadUsers();
    });

    $('#btn-search-users, #btn-reload-users').on('click', function () {
        loadUsers();
    });
    $('#user-keyword').on('keypress', function (e) {
        if (e.which === 13) loadUsers();
    });

    $('#btn-admin-logout').on('click', function () {
        AuthStorage.clear();
        location.href = 'login.html';
    });

    $(function () {
        toggleCreateShopField();
        loadUsers();
    });
})();
