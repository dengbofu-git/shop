/**
 * 前端路由管理
 * 支持SPA模式或传统多页面模式
 */

// API基础URL
const API_BASE_URL = 'http://127.0.0.1:8000/v1';

// 统一API调用封装
class ApiClient {
    constructor(baseUrl = API_BASE_URL) {
        this.baseUrl = baseUrl;
    }

    /**
     * 获取认证Token
     */
    getToken() {
        return (typeof AuthStorage !== 'undefined' && AuthStorage.getToken) ? AuthStorage.getToken() : '';
    }

    /**
     * 统一请求方法
     */
    async request(url, options = {}) {
        const token = this.getToken();
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        if (token) {
            headers['Authorization'] = token;
        }

        const config = {
            ...options,
            headers,
        };

        try {
            const response = await fetch(`${this.baseUrl}${url}`, config);
            const data = await response.json();
            
            if (response.ok) {
                return data;
            } else {
                throw new Error(data.error || '请求失败');
            }
        } catch (error) {
            console.error('API请求错误:', error);
            throw error;
        }
    }

    /**
     * GET请求
     */
    async get(url, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;
        return this.request(fullUrl, { method: 'GET' });
    }

    /**
     * POST请求
     */
    async post(url, data = {}) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    /**
     * PUT请求
     */
    async put(url, data = {}) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    /**
     * DELETE请求
     */
    async delete(url) {
        return this.request(url, { method: 'DELETE' });
    }
}

// 创建全局API客户端实例
const apiClient = new ApiClient();

// 路由管理类
class Router {
    constructor() {
        this.routes = {};
        this.currentRoute = null;
    }

    /**
     * 注册路由
     */
    register(path, handler) {
        this.routes[path] = handler;
    }

    /**
     * 导航到指定路径
     */
    navigate(path) {
        if (this.routes[path]) {
            this.currentRoute = path;
            this.routes[path]();
        } else {
            // 传统页面跳转
            window.location.href = path;
        }
    }

    /**
     * 获取当前路由
     */
    getCurrentRoute() {
        return this.currentRoute || window.location.pathname;
    }
}

// 创建全局路由实例
const router = new Router();

// 导出供其他脚本使用
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { apiClient, router };
}
