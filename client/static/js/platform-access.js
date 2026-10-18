/** Check current server grants before initializing a platform page. */
window.PlatformAccess = {
    requirePermission: async function (permission) {
        var token = AuthStorage.getToken();
        try {
            if (!token) throw new Error('login-required');
            var response = await fetch('/v1/users/session', {
                headers: { Authorization: 'Bearer ' + token }, cache: 'no-store'
            });
            if (response.status === 401 || response.status === 403) AuthStorage.clear();
            if (!response.ok) throw new Error('access-unavailable');
            var access = await response.json();
            var platform = access.roles.some(function (role) {
                return ['super_admin', 'admin', 'customer_service', 'finance'].indexOf(role) !== -1;
            });
            var required = Array.isArray(permission) ? permission : [permission];
            if (!platform || !required.some(function (code) { return access.permissions.indexOf(code) !== -1; })) {
                (window.top === window.self ? location : window.top.location).replace(access.redirect_url || '/login.html');
                return false;
            }
            this.currentAccess = access;
            document.querySelectorAll('[data-platform-permission]').forEach(function (el) {
                el.hidden = access.permissions.indexOf(el.dataset.platformPermission) === -1;
                if (el.hidden) el.style.display = 'none';
            });
            document.body.style.visibility = 'visible';
            return true;
        } catch (error) {
            (window.top === window.self ? location : window.top.location).replace('/login.html');
            return false;
        }
    }
};
