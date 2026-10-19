/**
 * 认证存储层 - 身份只属于当前标签页。
 * 同源 iframe 使用所属标签页的 sessionStorage；刷新保留会话。
 * 新开且不继承会话的标签页须登录，不从全浏览器共享存储猜测身份。
 */
var AuthStorage = {
    getToken: function() { return sessionStorage.getItem('tea_saas_token'); },
    setToken: function(v) {
        if (v != null) {
            sessionStorage.setItem('tea_saas_token', v);
        }
    },
    getUser: function() { return sessionStorage.getItem('tea_saas_user'); },
    setUser: function(v) {
        if (v != null) {
            sessionStorage.setItem('tea_saas_user', v);
        }
    },
    getCount: function() { return sessionStorage.getItem('tea_saas_count'); },
    setCount: function(v) {
        if (v != null) {
            sessionStorage.setItem('tea_saas_count', v);
        }
    },
    getShop: function() { return sessionStorage.getItem('tea_saas_shop'); },
    setShop: function(v) {
        if (v != null) {
            sessionStorage.setItem('tea_saas_shop', v);
        }
    },
    getUserType: function() { return sessionStorage.getItem('tea_saas_user_type'); },
    setUserType: function(v) {
        if (v != null) {
            sessionStorage.setItem('tea_saas_user_type', v);
        }
    },
    clear: function() {
        var token = sessionStorage.getItem('tea_saas_token');
        sessionStorage.removeItem('tea_saas_token');
        sessionStorage.removeItem('tea_saas_user');
        sessionStorage.removeItem('tea_saas_count');
        sessionStorage.removeItem('tea_saas_shop');
        sessionStorage.removeItem('tea_saas_user_type');
        // Clean up only this account's legacy shared cache, never another tab's account.
        if (token && localStorage.getItem('tea_saas_token') === token) {
            ['tea_saas_token', 'tea_saas_user', 'tea_saas_count', 'tea_saas_shop', 'tea_saas_user_type'].forEach(function(key) {
                localStorage.removeItem(key);
            });
        }
    }
};
