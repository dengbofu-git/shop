/**
 * 认证存储层 - 身份只属于当前标签页。
 * 同源 iframe 使用所属标签页的 sessionStorage；刷新保留会话。
 * 新开且不继承会话的标签页须登录，不从全浏览器共享存储猜测身份。
 */
var AuthStorage = {
    getToken: function() { return sessionStorage.getItem('dashop_token'); },
    setToken: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_token', v);
        }
    },
    getUser: function() { return sessionStorage.getItem('dashop_user'); },
    setUser: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_user', v);
        }
    },
    getCount: function() { return sessionStorage.getItem('dashop_count'); },
    setCount: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_count', v);
        }
    },
    getShop: function() { return sessionStorage.getItem('dashop_shop'); },
    setShop: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_shop', v);
        }
    },
    getUserType: function() { return sessionStorage.getItem('dashop_user_type'); },
    setUserType: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_user_type', v);
        }
    },
    clear: function() {
        var token = sessionStorage.getItem('dashop_token');
        sessionStorage.removeItem('dashop_token');
        sessionStorage.removeItem('dashop_user');
        sessionStorage.removeItem('dashop_count');
        sessionStorage.removeItem('dashop_shop');
        sessionStorage.removeItem('dashop_user_type');
        // Clean up only this account's legacy shared cache, never another tab's account.
        if (token && localStorage.getItem('dashop_token') === token) {
            ['dashop_token', 'dashop_user', 'dashop_count', 'dashop_shop', 'dashop_user_type'].forEach(function(key) {
                localStorage.removeItem(key);
            });
        }
    }
};
