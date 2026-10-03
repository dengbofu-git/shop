/**
 * 中台登录页 - 三语切换、RTL、四角色、登录逻辑
 */

(function() {
    'use strict';

    var i18n = {
        zh: {
            slogan: '香茗何须愁遥阻，春风直越万重关',
            slogan_sub: 'Fragrant tea knows no distance; spring breeze crosses all barriers',
            slogan_ar: 'الشاي العطِر لا يعرف المسافة؛ نسيم الربيع يتجاوز كل الحواجز',
            hero_desc: '大湾区港口 · 海上丝路 · 迪拜',
            highlight1: '9710一键报关，通关时效提升90%',
            highlight2: '广东地标茶一站式出海中东',
            highlight3: '区块链全链路溯源',
            logo_text: '茗越山关跨境电商 9710 报关数字系统',
            role_admin: '平台运营',
            role_supplier: '供应商',
            role_buyer: '中东买家',
            role_customs: '报关专员',
            admin_hint: '平台运营请使用终端管理入口登录',
            go_terminal: '前往终端登录',
            placeholder_username: '请输入账号',
            placeholder_password: '请输入密码',
            remember: '记住密码',
            btn_login: '登录中台',
            challenge_cup: '第十五届挑战杯参赛项目',
            platform_desc: '粤港澳大湾区茶产业出海中东专属平台',
            register: '新用户注册',
            forget_pwd: '忘记密码'
        },
        en: {
            slogan: 'Fragrant tea knows no distance; spring breeze crosses all barriers',
            slogan_sub: '香茗何须愁遥阻，春风直越万重关',
            slogan_ar: 'الشاي العطِر لا يعرف المسافة؛ نسيم الربيع يتجاوز كل الحواجز',
            hero_desc: 'Greater Bay Port · Maritime Silk Road · Dubai',
            highlight1: '9710 One-Click Customs, 90% Faster Clearance',
            highlight2: 'Guangdong Landmark Tea to Middle East',
            highlight3: 'Blockchain Full-Chain Traceability',
            logo_text: 'Mingyue Shanguan Cross-border E-commerce 9710 Customs Digital System',
            role_admin: 'Platform Admin',
            role_supplier: 'Supplier',
            role_buyer: 'Middle East Buyer',
            role_customs: 'Customs Officer',
            admin_hint: 'Platform admin please use terminal login',
            go_terminal: 'Go to Terminal Login',
            placeholder_username: 'Username',
            placeholder_password: 'Password',
            remember: 'Remember me',
            btn_login: 'Login',
            challenge_cup: '15th Challenge Cup Project',
            platform_desc: 'GBA Tea Industry to Middle East Platform',
            register: 'Register',
            forget_pwd: 'Forgot password'
        },
        ar: {
            slogan: 'الشاي العطِر لا يعرف المسافة؛ نسيم الربيع يتجاوز كل الحواجز',
            slogan_sub: 'Fragrant tea knows no distance',
            slogan_ar: '香茗何须愁遥阻，春风直越万重关',
            hero_desc: 'ميناء الخليج · طريق الحرير البحري · دبي',
            highlight1: 'إجراءات جمركية 9710 بنقرة واحدة، كفاءة 90٪',
            highlight2: 'شاي غوانغدونغ إلى الشرق الأوسط',
            highlight3: 'تتبع سلسلة الكتل الكاملة',
            logo_text: 'نظام مينغ يوي شانغوان 9710 الرقمي',
            role_admin: 'إدارة المنصة',
            role_supplier: 'المورد',
            role_buyer: 'مشتري الشرق الأوسط',
            role_customs: 'مسؤول الجمارك',
            admin_hint: 'يرجى استخدام تسجيل الدخول الطرفي',
            go_terminal: 'انتقل إلى تسجيل الدخول',
            placeholder_username: 'اسم المستخدم',
            placeholder_password: 'كلمة المرور',
            remember: 'تذكرني',
            btn_login: 'تسجيل الدخول',
            challenge_cup: 'مشروع كأس التحدي الخامس عشر',
            platform_desc: 'منصة شاي الخليج إلى الشرق الأوسط',
            register: 'التسجيل',
            forget_pwd: 'نسيت كلمة المرور'
        }
    };

    var currentLang = localStorage.getItem('portal_lang') || 'zh';
    var currentRole = 'admin';

    function setLang(lang) {
        currentLang = lang;
        localStorage.setItem('portal_lang', lang);
        document.documentElement.lang = lang === 'ar' ? 'ar' : (lang === 'en' ? 'en' : 'zh');
        document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
        document.body.classList.toggle('rtl-mode', lang === 'ar');

        document.querySelectorAll('.lang-btn').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.lang === lang);
        });

        var t = i18n[lang] || i18n.zh;
        document.querySelectorAll('[data-i18n]').forEach(function(el) {
            var key = el.getAttribute('data-i18n');
            if (t[key]) el.textContent = t[key];
        });

        var sub = document.querySelector('.brand-slogan-sub');
        var arEl = document.querySelector('.brand-slogan-ar');
        if (lang === 'ar') {
            if (sub) sub.style.display = 'none';
            if (arEl) { arEl.style.display = 'block'; arEl.lang = 'ar'; }
        } else {
            if (sub) sub.style.display = 'block';
            if (arEl) arEl.style.display = 'none';
        }
    }

    function switchRole(role) {
        currentRole = role;
        document.querySelectorAll('.role-tab').forEach(function(tab) {
            tab.classList.toggle('active', tab.dataset.role === role);
        });
        document.querySelectorAll('.role-form').forEach(function(form) {
            var show = form.id === 'form-' + role;
            form.style.display = show ? 'block' : 'none';
        });
    }

    function doLogin(expectedType, username, password, resultEl, btnEl, selectedRole) {
        var carts_data = null;
        try { carts_data = JSON.parse(window.localStorage.getItem('cart') || 'null'); } catch(e) {}
        var inputData = { username: username, password: password, carts: carts_data, expected_user_type: expectedType };

        btnEl.disabled = true;
        btnEl.textContent = (currentLang === 'zh' ? '登录中...' : (currentLang === 'ar' ? 'جاري تسجيل الدخول...' : 'Logging in...'));

        $.ajax({
            type: 'POST',
            url: (typeof baseUrl !== 'undefined' ? baseUrl : '') + '/v1/users/login',
            contentType: 'application/json',
            data: JSON.stringify(inputData),
            success: function(result) {
                if (result.code === 200) {
                    if (expectedType && result.user_type !== expectedType) {
                        var msg = (currentLang === 'zh' ? '账号类型不匹配' : (currentLang === 'ar' ? 'نوع الحساب غير متطابق' : 'Account type mismatch'));
                        $(resultEl).html(msg).addClass('show');
                        btnEl.disabled = false;
                        btnEl.textContent = i18n[currentLang].btn_login;
                        return;
                    }
                    if (typeof AuthStorage !== 'undefined') {
                        AuthStorage.clear();
                        AuthStorage.setToken(result.token);
                        AuthStorage.setCount(result.carts_count || 0);
                        AuthStorage.setUser(result.username);
                        if (result.shop_name) AuthStorage.setShop(result.shop_name);
                        AuthStorage.setUserType(result.user_type);
                    }
                    var redirect;
                    if (selectedRole === 'admin') {
                        redirect = 'admin_panel.html';
                    } else if (result.user_type === 'merchant') {
                        redirect = 'merchant_dashboard.html';
                    } else {
                        redirect = 'buyer_dashboard.html';
                    }
                    window.location.href = redirect;
                } else {
                    $(resultEl).html(result.error || (currentLang === 'zh' ? '登录失败' : 'Login failed')).addClass('show');
                    btnEl.disabled = false;
                    btnEl.textContent = i18n[currentLang].btn_login;
                }
            },
            error: function(xhr) {
                var err = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : (currentLang === 'zh' ? '登录失败，请重试' : 'Login failed');
                $(resultEl).html(err).addClass('show');
                btnEl.disabled = false;
                btnEl.textContent = i18n[currentLang].btn_login;
            }
        });
    }

    $(function() {
        setLang(currentLang);

        document.querySelectorAll('.lang-btn').forEach(function(btn) {
            btn.addEventListener('click', function() {
                setLang(btn.dataset.lang);
            });
        });

        document.querySelectorAll('.role-tab').forEach(function(tab) {
            tab.addEventListener('click', function() {
                switchRole(tab.dataset.role);
            });
        });

        ['admin', 'supplier', 'buyer'].forEach(function(role) {
            var form = document.getElementById('login-form-' + role);
            if (!form) return;
            var resultEl = document.getElementById('showResult-' + role);
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                var username = document.getElementById('username-' + role).value.trim();
                var password = document.getElementById('password-' + role).value;
                if (!username || !password) {
                    $(resultEl).html(currentLang === 'zh' ? '请输入账号和密码' : 'Please enter username and password').addClass('show');
                    return;
                }
                $(resultEl).empty().removeClass('show');
                var expectedType = (role === 'buyer') ? 'customer' : (role === 'admin' ? null : 'merchant');
                doLogin(expectedType, username, password, resultEl, form.querySelector('.btn-login'), role);
            });
        });
    });
})();
