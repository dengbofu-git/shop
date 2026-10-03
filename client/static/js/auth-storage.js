/**
 * 认证存储层 - 混合策略
 * - sessionStorage：当前标签页会话，支持同浏览器多标签页不同账号
 * - localStorage：新标签页/刷新时从 localStorage 同步，避免新开页 username 为 null
 */
function _syncFromLocal() {
    if (!sessionStorage.getItem('dashop_token') && localStorage.getItem('dashop_token')) {
        sessionStorage.setItem('dashop_token', localStorage.getItem('dashop_token'));
        var u = localStorage.getItem('dashop_user');
        if (u) sessionStorage.setItem('dashop_user', u);
        var c = localStorage.getItem('dashop_count');
        if (c) sessionStorage.setItem('dashop_count', c);
        var s = localStorage.getItem('dashop_shop');
        if (s) sessionStorage.setItem('dashop_shop', s);
        var ut = localStorage.getItem('dashop_user_type');
        if (ut) sessionStorage.setItem('dashop_user_type', ut);
    }
}
var AuthStorage = {
    getToken: function() { _syncFromLocal(); return sessionStorage.getItem('dashop_token'); },
    setToken: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_token', v);
            localStorage.setItem('dashop_token', v);
        }
    },
    getUser: function() { _syncFromLocal(); return sessionStorage.getItem('dashop_user'); },
    setUser: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_user', v);
            localStorage.setItem('dashop_user', v);
        }
    },
    getCount: function() { _syncFromLocal(); return sessionStorage.getItem('dashop_count'); },
    setCount: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_count', v);
            localStorage.setItem('dashop_count', v);
        }
    },
    getShop: function() { _syncFromLocal(); return sessionStorage.getItem('dashop_shop'); },
    setShop: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_shop', v);
            localStorage.setItem('dashop_shop', v);
        }
    },
    getUserType: function() { _syncFromLocal(); return sessionStorage.getItem('dashop_user_type'); },
    setUserType: function(v) {
        if (v != null) {
            sessionStorage.setItem('dashop_user_type', v);
            localStorage.setItem('dashop_user_type', v);
        }
    },
    clear: function() {
        sessionStorage.removeItem('dashop_token');
        sessionStorage.removeItem('dashop_user');
        sessionStorage.removeItem('dashop_count');
        sessionStorage.removeItem('dashop_shop');
        sessionStorage.removeItem('dashop_user_type');
        localStorage.removeItem('dashop_token');
        localStorage.removeItem('dashop_user');
        localStorage.removeItem('dashop_count');
        localStorage.removeItem('dashop_shop');
        localStorage.removeItem('dashop_user_type');
    }
};
