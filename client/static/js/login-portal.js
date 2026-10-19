/**
 * tea_saas 登录入口：茶文化品牌、三语切换及服务端权限跳转
 */

(function() {
    'use strict';

    var i18n = {
        zh: {
            hero_eyebrow: '茶有源 · 合作无界',
            slogan: '一叶好茶，连接每一份用心。',
            slogan_sub: '从茶园到茶杯，让采购更从容，让合作更有温度。',
            scene_caption: '山间一叶，杯中万千。',
            highlight1: '发现好茶',
            highlight2: '协同经营',
            highlight3: '智能选茶',
            logo_text: 'tea_saas',
            brand_tagline: '茶叶采购与经营协作',
            welcome_eyebrow: '从这里，开启茶的旅程',
            welcome_title: '欢迎回来',
            welcome_desc: '登录你的账号，继续发现好茶与新的合作。',
            placeholder_username: '账号',
            placeholder_password: '密码',
            btn_login: '进入工作台',
            access_note: '登录后，根据账号权限进入对应工作台。',
            backend_mismatch: '登录服务尚未更新，请重启后端服务后刷新页面重试',
            platform_desc: '让好茶被发现，让合作更简单。',
            register_hint: '初次来到这里？',
            register: '创建账号',
            page_title: 'tea_saas · 茶叶采购与经营协作',
            page_description: '以茶为媒，连接好生意。在 tea_saas 发现茶品、协作订单，与智能助手一起找到适合的好茶。',
            hero_alt: '晨雾茶山间的青瓷盖碗与一盏清茶',
            logo_alt: 'tea_saas 茶芽与茶盏标志'
        },
        en: {
            hero_eyebrow: 'ROOTED IN TEA · OPEN TO THE WORLD',
            slogan: 'Good tea. Meaningful connections.',
            slogan_sub: 'From the garden to the cup, bring care to every purchase and every partnership.',
            scene_caption: 'A small leaf. A world of possibilities.',
            highlight1: 'Discover tea',
            highlight2: 'Work together',
            highlight3: 'Find your tea',
            logo_text: 'tea_saas',
            brand_tagline: 'Tea trade, connected',
            welcome_eyebrow: 'YOUR TEA JOURNEY STARTS HERE',
            welcome_title: 'Welcome back',
            welcome_desc: 'Sign in to discover fine tea and your next collaboration.',
            placeholder_username: 'Account',
            placeholder_password: 'Password',
            btn_login: 'Enter workspace',
            access_note: 'Your account permissions determine your workspace.',
            backend_mismatch: 'The login service is out of date. Restart the backend and reload this page.',
            platform_desc: 'Good tea, discovered. Partnerships, simplified.',
            register_hint: 'New to tea_saas?',
            register: 'Create an account',
            page_title: 'tea_saas · Tea Trade Workspace',
            page_description: 'Discover tea, coordinate orders and find your next tea with an intelligent assistant on tea_saas.',
            hero_alt: 'Celadon tea ware overlooking misty tea terraces at dawn',
            logo_alt: 'tea_saas tea leaf and tea bowl symbol'
        },
        ar: {
            hero_eyebrow: 'جذور في الشاي · آفاق بلا حدود',
            slogan: 'شاي أصيل، وشراكات بعناية.',
            slogan_sub: 'من المزرعة إلى الفنجان، نجعل شراء الشاي والتعاون أكثر سهولة ودفئاً.',
            scene_caption: 'ورقة صغيرة، وعالم من الإمكانات.',
            highlight1: 'اكتشف الشاي',
            highlight2: 'تعاون في أعمالك',
            highlight3: 'اختر شايك بذكاء',
            logo_text: 'tea_saas',
            brand_tagline: 'تجارة الشاي والتعاون',
            welcome_eyebrow: 'تبدأ رحلة الشاي من هنا',
            welcome_title: 'مرحباً بعودتك',
            welcome_desc: 'سجّل الدخول لاكتشاف الشاي المميز ومتابعة شراكاتك.',
            placeholder_username: 'الحساب',
            placeholder_password: 'كلمة المرور',
            btn_login: 'الدخول إلى مساحة العمل',
            access_note: 'تُحدَّد مساحة عملك وفق صلاحيات حسابك.',
            backend_mismatch: 'خدمة تسجيل الدخول غير محدثة. يرجى إعادة تشغيل الخادم وتحديث الصفحة.',
            platform_desc: 'نقرّب الشاي الجيد، ونجعل الشراكات أسهل.',
            register_hint: 'هل أنت جديد هنا؟',
            register: 'إنشاء حساب',
            page_title: 'tea_saas · مساحة تجارة الشاي',
            page_description: 'اكتشف الشاي وتابع الطلبات وتعاون مع الشركاء بمساعدة ذكية عبر tea_saas.',
            hero_alt: 'أواني شاي خزفية أمام مدرجات الشاي في ضباب الصباح',
            logo_alt: 'رمز ورقة الشاي وفنجان tea_saas'
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

        document.title = t.page_title;
        var description = document.getElementById('page-description');
        if (description) description.setAttribute('content', t.page_description);
        document.querySelectorAll('[data-i18n-alt]').forEach(function(el) {
            el.alt = t[el.getAttribute('data-i18n-alt')];
        });
        document.querySelectorAll('.lang-btn').forEach(function(btn) {
            btn.setAttribute('aria-pressed', String(btn.dataset.lang === lang));
        });
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
