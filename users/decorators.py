"""
权限验证装饰器
"""
from functools import wraps
from django.http import JsonResponse
from .models import UserProfile
from dadashop.utils import jwt_decode


def get_user_from_request(request):
    """从请求中获取用户对象"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header:
        return None, JsonResponse({
            'code': 401,
            'error': '未提供认证令牌'
        }, status=401)
    
    try:
        token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
        payload = jwt_decode(token)
        user_id = payload.get('id')
        user = UserProfile.objects.get(id=user_id)
        return user, None
    except Exception as e:
        return None, JsonResponse({
            'code': 401,
            'error': f'认证失败: {str(e)}'
        }, status=401)


def merchant_required(view_func):
    """
    店家权限验证装饰器
    只有店家可以访问
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # 获取token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            return JsonResponse({
                'code': 401,
                'error': '未提供认证令牌'
            }, status=401)
        
        try:
            token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
            payload = jwt_decode(token)
            user_id = payload.get('id')
            
            # 获取用户
            user = UserProfile.objects.get(id=user_id)
            
            # 验证是否为店家（user_type=merchant 或 拥有supplier角色）
            if not user.is_merchant() and not user.has_role('supplier'):
                return JsonResponse({
                    'code': 403,
                    'error': '只有店家/供应商可以访问此功能，请使用商家账号登录'
                }, status=403)
            
            # 将用户对象添加到request中
            request.user_profile = user
            return view_func(request, *args, **kwargs)
            
        except Exception as e:
            return JsonResponse({
                'code': 401,
                'error': f'认证失败: {str(e)}'
            }, status=401)
    
    return wrapper


def customer_required(view_func):
    """
    客户权限验证装饰器
    只有客户可以访问
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # 获取token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            return JsonResponse({
                'code': 401,
                'error': '未提供认证令牌'
            }, status=401)
        
        try:
            token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
            payload = jwt_decode(token)
            user_id = payload.get('id')
            
            # 获取用户
            user = UserProfile.objects.get(id=user_id)
            
            # 验证是否为客户
            if not user.is_customer():
                return JsonResponse({
                    'code': 403,
                    'error': '只有客户可以访问此功能'
                }, status=403)
            
            # 将用户对象添加到request中
            request.user_profile = user
            return view_func(request, *args, **kwargs)
            
        except Exception as e:
            return JsonResponse({
                'code': 401,
                'error': f'认证失败: {str(e)}'
            }, status=401)
    
    return wrapper


def login_required(view_func):
    """
    登录验证装饰器
    任何已登录用户都可以访问
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # 获取token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header:
            return JsonResponse({
                'code': 401,
                'error': '未提供认证令牌'
            }, status=401)
        
        try:
            token = auth_header.split(' ')[-1] if ' ' in auth_header else auth_header
            payload = jwt_decode(token)
            user_id = payload.get('id')
            
            # 获取用户
            user = UserProfile.objects.get(id=user_id)
            
            # 将用户对象添加到request中
            request.user_profile = user
            return view_func(request, *args, **kwargs)
            
        except Exception as e:
            return JsonResponse({
                'code': 401,
                'error': f'认证失败: {str(e)}'
            }, status=401)
    
    return wrapper


def permission_required(permission_code):
    """
    权限验证装饰器（基于权限代码）
    使用示例: @permission_required('goods_manage')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user, error_response = get_user_from_request(request)
            if error_response:
                return error_response
            
            # 验证权限
            if not user.has_permission(permission_code):
                return JsonResponse({
                    'code': 403,
                    'error': f'没有权限访问此功能，需要权限: {permission_code}'
                }, status=403)
            
            request.user_profile = user
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def role_required(role_code):
    """
    角色验证装饰器（基于角色代码）
    使用示例: @role_required('supplier')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user, error_response = get_user_from_request(request)
            if error_response:
                return error_response
            
            # 验证角色（supplier 角色时，merchant 类型用户也可访问）
            if not user.has_role(role_code):
                if role_code == 'supplier' and user.is_merchant():
                    pass  # 商家类型等同供应商
                else:
                    return JsonResponse({
                        'code': 403,
                        'error': f'没有权限访问此功能，需要角色: {role_code}，请使用商家账号登录'
                    }, status=403)
            
            request.user_profile = user
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def permissions_required(permission_codes, require_all=True):
    """
    多权限验证装饰器
    使用示例: 
        @permissions_required(['goods_manage', 'order_manage'], require_all=True)  # 需要所有权限
        @permissions_required(['goods_manage', 'order_manage'], require_all=False)  # 需要任一权限
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user, error_response = get_user_from_request(request)
            if error_response:
                return error_response
            
            # 验证权限
            has_permissions = [user.has_permission(code) for code in permission_codes]
            
            if require_all:
                # 需要所有权限
                if not all(has_permissions):
                    return JsonResponse({
                        'code': 403,
                        'error': f'没有权限访问此功能，需要所有权限: {", ".join(permission_codes)}'
                    }, status=403)
            else:
                # 需要任一权限
                if not any(has_permissions):
                    return JsonResponse({
                        'code': 403,
                        'error': f'没有权限访问此功能，需要任一权限: {", ".join(permission_codes)}'
                    }, status=403)
            
            request.user_profile = user
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
