"""tea_saas URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf.urls.static import static
from django.conf import settings

def index(request):
    """首页视图，重定向到登录页"""
    return redirect('login_page')

def login_page(request):
    """登录页面"""
    return render(request, 'login.html')

def index_page(request):
    """原商城首页已下线，跳转买家工作台"""
    return redirect('/buyer_dashboard.html')

def template_view(template_name):
    """返回渲染指定模板的视图函数"""
    return lambda r: render(r, template_name)


def platform_workspace_page(template_name, section):
    """Keep direct workspace links inside the platform shell."""
    def view(request):
        if request.GET.get('embedded') == '1':
            return render(request, template_name, {'embedded': True})
        return redirect('/admin_panel.html#' + section)
    return view

def chrome_devtools_json(request):
    """Chrome DevTools 自动请求，返回空 JSON 避免 404 日志"""
    return JsonResponse({})

urlpatterns = [
                  re_path(r'^\.?well-known/appspecific/com\.chrome\.devtools\.json$', chrome_devtools_json),
                  path('', index, name='home'),
                  path('index.html', index_page, name='index_page'),
                  path('login.html', login_page, name='login_page'),
                  path('terminal_login.html', lambda r: redirect('/login.html')),
                  path('header.html', template_view('header.html')),
                  path('footer.html', template_view('footer.html')),
                  path('product_list.html', lambda r: redirect('/buyer_products.html' + ('?' + r.META.get('QUERY_STRING', '') if r.META.get('QUERY_STRING') else ''))),
                  path('product_details.html', template_view('product_details.html')),
                  path('search_list.html', template_view('search_list.html')),
                  path('search.html', lambda r: redirect('/search_list.html')),
                  path('cart.html', template_view('cart.html')),
                  path('addressAdmin.html', lambda r: redirect('/buyer_profile.html#addresses')),
                  path('buyer_profile.html', template_view('buyer_profile.html')),
                  path('buyer_password.html', template_view('buyer_password.html')),
                  path('myOrder.html', lambda r: redirect('/buyer_orders.html')),
                  path('register.html', lambda r: redirect('/register_sms.html')),
                  path('register_sms.html', template_view('register_sms.html')),
                  path('orderConfirm.html', template_view('orderConfirm.html')),
                  path('payment.html', template_view('payment.html')),
                  path('pay_success.html', template_view('pay_success.html')),
                  path('gopay.html', template_view('gopay.html')),
                  path('personal_password.html', lambda r: redirect('/buyer_password.html')),
                  path('lookforward.html', lambda r: redirect('/buyer_dashboard.html')),
                  path('myCollect.html', template_view('buyer_activity.html')),
                  path('recent.html', template_view('buyer_activity.html')),
                  path('supplier_profile.html', template_view('supplier_profile.html')),
                  path('supplier_password.html', template_view('supplier_password.html')),
                  path('merchant_dashboard.html', template_view('merchant_dashboard.html')),
                  path('merchant_assistant.html', template_view('merchant_assistant.html')),
                  path('merchant_products.html', template_view('merchant_products.html')),
                  path('merchant_orders.html', template_view('merchant_orders.html')),
                  path('merchant_inventory.html', template_view('merchant_inventory.html')),
                  path('merchant_settlement.html', template_view('merchant_settlement.html')),
                  path('super_terminal.html', lambda r: redirect('/admin_panel.html')),
                  path('operations_dashboard.html', template_view('operations_dashboard.html')),
                  path('admin_panel.html', template_view('admin_panel.html')),
                  path('admin_users.html', platform_workspace_page('admin_users.html', 'users')),
                  path('admin_agents.html', platform_workspace_page('admin_agents.html', 'agents')),
                  path('buyer_dashboard.html', template_view('buyer_dashboard.html')),
                  path('buyer_products.html', template_view('buyer_products.html')),
                  path('buyer_orders.html', template_view('buyer_orders.html')),
                  path('buyer_support.html', template_view('buyer_support.html')),
                  path('logistics_track.html', template_view('logistics_track.html')),
                  path('admin/', admin.site.urls),
                  path('v1/users/', include('users.urls')),
                  path('v1/goods/', include('goods.urls')),
                  path('v1/carts/', include('carts.urls')),
                  path('v1/orders/', include('orders.urls')),
                  path('v1/pays/', include('pays.urls')),
                  path('v1/news/', include('news.urls')),
                  path('v1/inventory/', include('inventory.urls')),
                  path('v1/logistics/', include('logistics.urls')),
                  path('v1/supplier/', include('supplier.urls')),
                  path('v1/admin-panel/', include('admin_panel.urls')),
                  path('v1/support/', include('support_ai.urls')),
                  path('v1/merchant-ai/', include('merchant_ai.urls')),
              ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None)
