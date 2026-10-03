(function () {
    'use strict';

    var username = AuthStorage.getUser();
    var token = AuthStorage.getToken();
    var apiBase = typeof baseUrl === 'string' ? baseUrl.replace(/\/$/, '') : '';

    if (!username || !token) {
        location.href = 'login.html';
        return;
    }

    function setMsg(text, ok) {
        var $el = $('#password-msg');
        $el.text(text || '').removeClass('ok err');
        if (text) $el.addClass(ok ? 'ok' : 'err');
    }

    $('#password-form').on('submit', function (e) {
        e.preventDefault();
        var oldPwd = $('#pwd-old').val();
        var newPwd = $('#pwd-new').val();
        var confirmPwd = $('#pwd-confirm').val();
        if (newPwd !== confirmPwd) {
            setMsg('两次输入的新密码不一致', false);
            return;
        }
        if (newPwd.length < 6 || newPwd.length > 12) {
            setMsg('新密码长度须为 6–12 位', false);
            return;
        }
        setMsg('', true);
        $.ajax({
            type: 'POST',
            url: apiBase + '/v1/users/' + encodeURIComponent(username) + '/password',
            contentType: 'application/json',
            data: JSON.stringify({
                oldpassword: oldPwd,
                password1: newPwd,
                password2: confirmPwd
            }),
            beforeSend: function (xhr) {
                xhr.setRequestHeader('authorization', token);
            },
            success: function (res) {
                if (res.code == 403) {
                    alert('用户认证已过期，请重新登录');
                    AuthStorage.clear();
                    location.href = 'login.html';
                    return;
                }
                if (res.code === 200) {
                    setMsg('密码已更新，请重新登录', true);
                    AuthStorage.clear();
                    setTimeout(function () {
                        location.href = 'login.html';
                    }, 1200);
                } else {
                    setMsg(res.error || '修改失败', false);
                }
            },
            error: function () {
                setMsg('修改失败，请稍后重试', false);
            }
        });
    });
})();
