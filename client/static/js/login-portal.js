/**
 * 中台登录页 - 三语切换、RTL、服务端权限跳转
 */

(function() {
    'use strict';

    var i18n = {
        zh: {
            slogan: '香茗何须愁遥阻，春风直越万重关',
            slogan_sub: 'Fragrant tea knows no distance; spring breeze crosses all barriers',
            slogan_ar: 'الشاي العطِر لا يعرف المسافة؛ نسيم الربيع يتجاوز كل الحواجز',
            hero_desc: '大湾区港口 · 海上丝路 · 迪拜',
            highlight1: '商品采购、订单与经营协同',
            highlight2: '茶叶采购与商家经营工作台',
            highlight3: '智能客服与茶品推荐',
            logo_text: '茗越山关跨境茶叶 SaaS 平台',
            placeholder_username: '请输入账号',
            placeholder_password: '请输入密码',
            btn_login: '登录',
            backend_mismatch: '登录服务尚未更新，请重启后端服务后刷新页面重试',
            challenge_cup: '第十五届挑战杯参赛项目',
            platform_desc: '面向买家、茶企与运营的协作平台',
            register: '新用户注册',
            forget_pwd: '忘记密码'
        },
        en: {
            slogan: 'Fragrant tea knows no distance; spring breeze crosses all barriers',
            slogan_sub: '香茗何须愁遥阻，春风直越万重关',
            slogan_ar: 'الشاي العطِر لا يعرف المسافة؛ نسيم الربيع يتجاوز كل الحواجز',
            hero_desc: 'Greater Bay Port · Maritime Silk Road · Dubai',
            highlight1: 'Connected Tea Procurement, Orders and Operations',
            highlight2: 'Tea Procurement and Merchant Workspaces',
            highlight3: 'AI Support and Tea Recommendations',
            logo_text: 'Mingyue Shanguan Cross-border Tea SaaS Platform',
            placeholder_username: 'Username',
            placeholder_password: 'Password',
            btn_login: 'Login',
            backend_mismatch: 'The login service is out of date. Restart the backend and reload this page.',
            challenge_cup: '15th Challenge Cup Project',
            platform_desc: 'A Shared Platform for Buyers, Tea Merchants and Operators',
            register: 'Register',
            forget_pwd: 'Forgot password'
        },
        ar: {
            slogan: 'الشاي العطِر لا يعرف المسافة؛ نسيم الربيع يتجاوز كل الحواجز',
            slogan_sub: 'Fragrant tea knows no distance',
            slogan_ar: '香茗何须愁遥阻，春风直越万重关',
            hero_desc: 'ميناء الخليج · طريق الحرير البحري · دبي',
            highlight1: 'إدارة مشتريات الشاي والطلبات والأعمال',
            highlight2: 'مساحات عمل لمشتريات الشاي والتجار',
            highlight3: 'دعم ذكي وتوصيات الشاي',
            logo_text: 'منصة مينغ يوي شانغوان SaaS لتجارة الشاي عبر الحدود',
            placeholder_username: 'اسم المستخدم',
            placeholder_password: 'كلمة المرور',
            btn_login: 'تسجيل الدخول',
            backend_mismatch: 'خدمة تسجيل الدخول غير محدثة. يرجى إعادة تشغيل الخادم وتحديث الصفحة.',
            challenge_cup: 'مشروع كأس التحدي الخامس عشر',
            platform_desc: 'منصة مشتركة للمشترين وتجار الشاي والمشغلين',
            register: 'التسجيل',
            forget_pwd: 'نسيت كلمة المرور'
        }
    };

    var currentLang = localStorage.getItem('portal_lang') || 'zh';
    if (!i18n[currentLang]) currentLang = 'zh';

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

    var destinations = ['/admin_panel.html', '/admin_users.html', '/admin_agents.html', '/merchant_dashboard.html', '/buyer_dashboard.html'];

    function doLogin(username, password, resultEl, btnEl) {
        var carts_data = null;
        try { carts_data = JSON.parse(window.localStorage.getItem('cart') || 'null'); } catch(e) {}
        var inputData = { username: username, password: password, carts: carts_data };

        btnEl.disabled = true;
        btnEl.textContent = (currentLang === 'zh' ? '登录中...' : (currentLang === 'ar' ? 'جاري تسجيل الدخول...' : 'Logging in...'));

        $.ajax({
            type: 'POST',
            url: (typeof baseUrl !== 'undefined' ? baseUrl : '') + '/v1/users/login',
            contentType: 'application/json',
            data: JSON.stringify(inputData),
            success: function(result) {
                if (result.code === 200) {
                    if (typeof result.redirect_url === 'undefined') {
                        $(resultEl).text(i18n[currentLang].backend_mismatch).addClass('show');
                        btnEl.disabled = false;
                        btnEl.textContent = i18n[currentLang].btn_login;
                        return;
                    }
                    if (destinations.indexOf(result.redirect_url) === -1) {
                        $(resultEl).text(currentLang === 'zh' ? '账号没有可访问的工作台，请联系管理员' : (currentLang === 'ar' ? 'يرجى التواصل مع المسؤول لتفعيل صلاحية الدخول' : 'No workspace access. Please contact an administrator.')).addClass('show');
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
                    window.location.href = result.redirect_url;
                } else {
                    $(resultEl).text(result.error || (currentLang === 'zh' ? '登录失败' : 'Login failed')).addClass('show');
                    btnEl.disabled = false;
                    btnEl.textContent = i18n[currentLang].btn_login;
                }
            },
            error: function(xhr) {
                var err = (xhr.responseJSON && xhr.responseJSON.error) ? xhr.responseJSON.error : (currentLang === 'zh' ? '登录失败，请重试' : 'Login failed');
                $(resultEl).text(err).addClass('show');
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

        var form = document.getElementById('login-form');
        var resultEl = document.getElementById('showResult');
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var button = form.querySelector('.btn-login');
            if (button.disabled) return;
            var username = document.getElementById('username').value.trim();
            var password = document.getElementById('password').value;
            if (!username || !password) {
                $(resultEl).text(currentLang === 'zh' ? '请输入账号和密码' : (currentLang === 'ar' ? 'يرجى إدخال اسم المستخدم وكلمة المرور' : 'Please enter username and password')).addClass('show');
                return;
            }
            $(resultEl).empty().removeClass('show');
            doLogin(username, password, resultEl, button);
        });
    });
})();
