(function () {
    'use strict';

    var username = AuthStorage.getUser();
    var token = AuthStorage.getToken();
    var apiBase = typeof baseUrl === 'string' ? baseUrl.replace(/\/$/, '') : '';

    if (!username || !token) {
        location.href = 'login.html';
        return;
    }

    function authHeaders(xhr) {
        xhr.setRequestHeader('authorization', token);
    }

    function handleAuthError(code) {
        if (code == 403) {
            alert('用户认证已过期，请重新登录');
            AuthStorage.clear();
            location.href = 'login.html';
            return true;
        }
        return false;
    }

    function setMsg(el, text, ok) {
        var $el = $(el);
        $el.text(text || '').removeClass('ok err');
        if (text) $el.addClass(ok ? 'ok' : 'err');
    }

    function switchTab(name) {
        $('.ba-tab').removeClass('active').attr('aria-selected', 'false');
        $('.ba-tab[data-tab="' + name + '"]').addClass('active').attr('aria-selected', 'true');
        $('.ba-panel').removeClass('active');
        $('#panel-' + name).addClass('active');
    }

    $('.ba-tab').on('click', function () {
        switchTab($(this).data('tab'));
    });

    if (location.hash === '#addresses') {
        switchTab('addresses');
    }

    function loadProfile() {
        $.ajax({
            type: 'GET',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/profile',
            beforeSend: authHeaders,
            success: function (res) {
                if (handleAuthError(res.code)) return;
                if (res.code !== 200) {
                    if (window.NicknameEditor) NicknameEditor.unavailable();
                    setMsg('#profile-msg', res.error || '加载失败', false);
                    return;
                }
                $('#pf-username').val(res.data.username || '');
                if (window.NicknameEditor) NicknameEditor.load(res.data.nickname);
                $('#pf-email').val(res.data.email || '');
                $('#pf-phone').val(res.data.phone || '');
            },
            error: function () {
                setMsg('#profile-msg', '无法加载账户信息', false);
                if (window.NicknameEditor) NicknameEditor.unavailable();
            }
        });
    }

    $('#profile-form').on('submit', function (e) {
        e.preventDefault();
        setMsg('#profile-msg', '', true);
        $.ajax({
            type: 'PUT',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/profile',
            contentType: 'application/json',
            data: JSON.stringify({
                email: $('#pf-email').val().trim(),
                phone: $('#pf-phone').val().trim()
            }),
            beforeSend: authHeaders,
            success: function (res) {
                if (handleAuthError(res.code)) return;
                if (res.code === 200) {
                    setMsg('#profile-msg', res.data || '保存成功', true);
                } else {
                    setMsg('#profile-msg', res.error || '保存失败', false);
                }
            },
            error: function () {
                setMsg('#profile-msg', '保存失败，请稍后重试', false);
            }
        });
    });

    $('.ba-tag-pick').on('click', function () {
        $('#addressName').val($(this).data('tag'));
    });

    function loadAddresses() {
        $.ajax({
            type: 'GET',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/address',
            beforeSend: authHeaders,
            success: function (res) {
                if (handleAuthError(res.code)) return;
                var $body = $('#address-list-body');
                if (res.code !== 200) {
                    $body.html('<tr><td colspan="5">' + (res.error || '加载失败') + '</td></tr>');
                    return;
                }
                var list = res.addresslist || [];
                if (!list.length) {
                    $body.html('<tr><td colspan="5">暂无收货地址，请在上方添加。</td></tr>');
                    return;
                }
                var html = '';
                list.forEach(function (row) {
                    html += '<tr class="' + (row.is_default ? 'is-default' : '') + '" data-id="' + row.id + '">';
                    html += '<td>' + (row.is_default ? '<span class="ba-badge-default">默认</span>' : '') + escapeHtml(row.tag) + '</td>';
                    html += '<td>' + escapeHtml(row.receiver) + '</td>';
                    html += '<td>' + escapeHtml(row.address) + '</td>';
                    html += '<td>' + escapeHtml(row.receiver_mobile) + '</td>';
                    html += '<td>';
                    if (!row.is_default) {
                        html += '<button type="button" class="ba-link-btn js-default">设为默认</button>';
                    }
                    html += '<button type="button" class="ba-link-btn danger js-delete">删除</button></td></tr>';
                });
                $body.html(html);
            },
            error: function () {
                $('#address-list-body').html('<tr><td colspan="5">地址加载失败</td></tr>');
            }
        });
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    $('#address-form').on('submit', function (e) {
        e.preventDefault();
        setMsg('#address-msg', '', true);
        var receiverName = $('#receiverName').val().trim();
        var receiverState = $('#receiverState').val();
        var receiverCity = $('#receiverCity').val();
        var receiverDistrict = $('#receiverDistrict').val();
        var receiverAddress = $('#receiverAddress').val().trim();
        var receiverMobile = $('#receiverMobile').val().trim();
        var receiverZip = $('#receiverZip').val().trim();
        var addressName = $('#addressName').val().trim();
        if (!receiverName || !receiverState || !receiverCity || !receiverDistrict || !receiverAddress || !receiverMobile || !receiverZip || !addressName) {
            setMsg('#address-msg', '请填写完整必填项', false);
            return;
        }
        $.ajax({
            type: 'POST',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/address',
            contentType: 'application/json',
            data: JSON.stringify({
                receiver: receiverName,
                address: receiverState + receiverCity + receiverDistrict + receiverAddress,
                receiver_phone: receiverMobile,
                postcode: receiverZip,
                tag: addressName
            }),
            beforeSend: authHeaders,
            success: function (res) {
                if (handleAuthError(res.code)) return;
                if (res.code === 200) {
                    setMsg('#address-msg', res.data || '地址已保存', true);
                    $('#address-form')[0].reset();
                    loadAddresses();
                } else {
                    setMsg('#address-msg', res.error || '保存失败', false);
                }
            },
            error: function () {
                setMsg('#address-msg', '保存失败', false);
            }
        });
    });

    $('#address-list-body').on('click', '.js-delete', function () {
        var id = $(this).closest('tr').data('id');
        if (!id || !confirm('确定删除该地址吗？')) return;
        $.ajax({
            type: 'DELETE',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/address/' + id,
            contentType: 'application/json',
            data: JSON.stringify({ id: id }),
            beforeSend: authHeaders,
            success: function (res) {
                if (handleAuthError(res.code)) return;
                if (res.code === 200) {
                    loadAddresses();
                } else {
                    alert(res.error || '删除失败');
                }
            }
        });
    });

    $('#address-list-body').on('click', '.js-default', function () {
        var id = $(this).closest('tr').data('id');
        $.ajax({
            type: 'POST',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/address/default',
            contentType: 'application/json',
            data: JSON.stringify({ id: id }),
            beforeSend: authHeaders,
            success: function (res) {
                if (handleAuthError(res.code)) return;
                if (res.code === 200) {
                    loadAddresses();
                } else {
                    alert(res.error || '设置失败');
                }
            }
        });
    });

    loadProfile();
    loadAddresses();
})();
