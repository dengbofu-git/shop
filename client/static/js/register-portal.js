/**
 * 注册页：买家 / 茶企商家 双路径
 */
(function () {
    'use strict';

    var currentRole = 'customer';

    function checkUname() {
        var len = $('#uname').val().length;
        return len >= 6 && len <= 11;
    }

    function checkPWD() {
        var len = $('#upwd').val().length;
        return len >= 6 && len <= 12;
    }

    function checkEmail() {
        var myReg = /^[\w.-]+@[\w.-]+\.\w+$/;
        return myReg.test($('#email').val());
    }

    function checkPhone() {
        return /^1[3-9]\d{9}$/.test($('#phone').val());
    }

    function checkMerchantFields() {
        if (currentRole !== 'merchant') return true;
        var shop = ($('#shop_name').val() || '').trim();
        return shop.length >= 2 && shop.length <= 50;
    }

    function setRole(role) {
        currentRole = role === 'merchant' ? 'merchant' : 'customer';
        $('.register-role-tab').removeClass('active');
        $('.register-role-tab[data-register-role="' + currentRole + '"]').addClass('active');
        var isMerchant = currentRole === 'merchant';
        $('#merchant-fields').toggle(isMerchant);
        $('#shop_name').prop('required', isMerchant);
        $('#register-role-hint').text(
            isMerchant
                ? '茶企商家注册后可登录供应商工作台，管理商品与订单。'
                : '中东买家注册后可采购商品、下单与追踪物流。'
        );
    }

    function validateAll() {
        if (!checkUname() || !checkPWD() || !checkEmail() || !checkPhone() || !checkMerchantFields()) {
            alert('请按提示填写完整且合法的注册信息');
            return false;
        }
        return true;
    }

    function redirectAfterRegister(data) {
        var ut = data.user_type || currentRole;
        if (typeof AuthStorage !== 'undefined') {
            AuthStorage.setToken(data.token);
            AuthStorage.setUser(data.username);
            AuthStorage.setCount(data.carts_count || 0);
            AuthStorage.setUserType(ut);
            if (data.shop_name) AuthStorage.setShop(data.shop_name);
        }
        alert(ut === 'merchant' ? '茶企账号注册成功！' : '买家账号注册成功！');
        window.location.href = ut === 'merchant' ? 'merchant_dashboard.html' : 'buyer_dashboard.html';
    }

    $(function () {
        setRole('customer');

        $('.register-role-tab').on('click', function () {
            setRole($(this).data('register-role'));
        });

        $('#bt-register').on('click', function () {
            if (!validateAll()) return;

            var payload = {
                uname: $('#uname').val().trim(),
                password: $('#upwd').val(),
                phone: $('#phone').val().trim(),
                email: $('#email').val().trim(),
                register_as: currentRole,
                carts: localStorage.getItem('cart')
            };
            if (currentRole === 'merchant') {
                payload.shop_name = $('#shop_name').val().trim();
                payload.shop_description = ($('#shop_description').val() || '').trim();
            }

            $('#bt-register').prop('disabled', true).val('提交中…');

            $.ajax({
                type: 'POST',
                url: (typeof baseUrl !== 'undefined' ? baseUrl : '') + '/v1/users/register',
                contentType: 'application/json',
                dataType: 'json',
                data: JSON.stringify(payload),
                success: function (data) {
                    if (data.code === 200) {
                        redirectAfterRegister(data);
                    } else {
                        alert(data.error || '注册失败');
                        $('#bt-register').prop('disabled', false).val('提交注册信息');
                    }
                },
                error: function () {
                    alert('注册请求失败，请稍后重试');
                    $('#bt-register').prop('disabled', false).val('提交注册信息');
                }
            });
        });
    });
})();
