(function () {
    'use strict';

    var username = AuthStorage.getUser();
    var token = AuthStorage.getToken();
    var apiBase = typeof baseUrl === 'string' ? baseUrl.replace(/\/$/, '') : '';

    if (!username || !token) {
        location.href = 'login.html';
        return;
    }

    if (window.location.search.indexOf('embed=1') >= 0) {
        var lp = document.getElementById('link-password');
        if (lp) lp.href = 'supplier_password.html?embed=1';
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

    function loadProfile() {
        var shop = typeof AuthStorage.getShop === 'function' ? AuthStorage.getShop() : '';
        $('#pf-shop').val(shop || '—');
        $.ajax({
            type: 'GET',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/profile',
            beforeSend: authHeaders,
            success: function (res) {
                if (handleAuthError(res.code)) return;
                if (res.code !== 200) {
                    setMsg('#profile-msg', res.error || '加载失败', false);
                    return;
                }
                $('#pf-username').val(res.data.username || '');
                if (typeof res.data.shop_name === 'string') $('#pf-shop').val(res.data.shop_name || '—');
                $('#pf-email').val(res.data.email || '');
                $('#pf-phone').val(res.data.phone || '');
            },
            error: function () {
                setMsg('#profile-msg', '无法加载账户信息', false);
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

    loadProfile();
})();
