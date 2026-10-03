"""
资讯管理视图
只有店家可以发布资讯
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from users.decorators import merchant_required, login_required
from .models import News
from django.conf import settings
from datetime import datetime
import json


@merchant_required
@require_http_methods(["POST"])
def create_news(request):
    """
    创建资讯（店家发布资讯）
    """
    try:
        data = json.loads(request.body)
        merchant = request.user_profile
        
        # 验证必填字段
        if 'title' not in data or 'content' not in data:
            return JsonResponse({
                'code': 400,
                'error': '标题和内容为必填项'
            })
        
        # 创建资讯
        news = News.objects.create(
            title=data['title'],
            content=data['content'],
            summary=data.get('summary', ''),
            author=merchant,
            status=data.get('status', 'draft'),
            is_top=data.get('is_top', False)
        )
        
        # 如果状态为已发布，设置发布时间
        if news.status == 'published':
            news.published_time = datetime.now()
            news.save()
        
        return JsonResponse({
            'code': 200,
            'msg': '资讯创建成功',
            'data': {
                'news_id': news.id,
                'title': news.title,
                'status': news.status
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'创建失败: {str(e)}'
        })


@merchant_required
@require_http_methods(["GET"])
def my_news(request):
    """
    获取店家的资讯列表
    """
    try:
        merchant = request.user_profile
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        
        # 获取店家的所有资讯
        news_list = News.objects.filter(author=merchant, status__in=['draft', 'published']).order_by('-created_time')
        
        # 分页
        paginator = Paginator(news_list, page_size)
        page_obj = paginator.get_page(page)
        
        news_data = []
        for news in page_obj:
            news_data.append({
                'news_id': news.id,
                'title': news.title,
                'summary': news.summary,
                'status': news.status,
                'view_count': news.view_count,
                'is_top': news.is_top,
                'created_time': news.created_time.strftime('%Y-%m-%d %H:%M:%S'),
                'published_time': news.published_time.strftime('%Y-%m-%d %H:%M:%S') if news.published_time else None
            })
        
        return JsonResponse({
            'code': 200,
            'data': news_data,
            'paginator': {
                'page': page,
                'page_size': page_size,
                'total': paginator.count,
                'pages': paginator.num_pages
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'获取失败: {str(e)}'
        })


@merchant_required
@require_http_methods(["PUT"])
def update_news(request, news_id):
    """
    更新资讯
    """
    try:
        merchant = request.user_profile
        data = json.loads(request.body)
        
        # 获取资讯并验证所有权
        try:
            news = News.objects.get(id=news_id, author=merchant)
        except News.DoesNotExist:
            return JsonResponse({
                'code': 404,
                'error': '资讯不存在或无权操作'
            })
        
        # 更新字段
        if 'title' in data:
            news.title = data['title']
        if 'content' in data:
            news.content = data['content']
        if 'summary' in data:
            news.summary = data['summary']
        if 'status' in data:
            news.status = data['status']
            if data['status'] == 'published' and not news.published_time:
                news.published_time = datetime.now()
        if 'is_top' in data:
            news.is_top = data['is_top']
        
        news.save()
        
        return JsonResponse({
            'code': 200,
            'msg': '更新成功',
            'data': {
                'news_id': news.id,
                'title': news.title,
                'status': news.status
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'更新失败: {str(e)}'
        })


@merchant_required
@require_http_methods(["DELETE"])
def delete_news(request, news_id):
    """
    删除资讯（软删除）
    """
    try:
        merchant = request.user_profile
        
        # 获取资讯并验证所有权
        try:
            news = News.objects.get(id=news_id, author=merchant)
        except News.DoesNotExist:
            return JsonResponse({
                'code': 404,
                'error': '资讯不存在或无权操作'
            })
        
        # 软删除
        news.status = 'deleted'
        news.save()
        
        return JsonResponse({
            'code': 200,
            'msg': '删除成功'
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'删除失败: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def news_list(request):
    """
    获取已发布的资讯列表（所有用户都可以查看）
    """
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        
        # 只获取已发布的资讯
        news_list = News.objects.filter(status='published').order_by('-is_top', '-published_time')
        
        # 分页
        paginator = Paginator(news_list, page_size)
        page_obj = paginator.get_page(page)
        
        news_data = []
        for news in page_obj:
            news_data.append({
                'news_id': news.id,
                'title': news.title,
                'summary': news.summary,
                'author': news.author.shop_name or news.author.username,
                'view_count': news.view_count,
                'is_top': news.is_top,
                'published_time': news.published_time.strftime('%Y-%m-%d %H:%M:%S') if news.published_time else None,
                'cover_image': settings.DADASHOP_MEDIA + str(news.cover_image) if news.cover_image else None
            })
        
        return JsonResponse({
            'code': 200,
            'data': news_data,
            'paginator': {
                'page': page,
                'page_size': page_size,
                'total': paginator.count,
                'pages': paginator.num_pages
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'获取失败: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def news_detail(request, news_id):
    """
    获取资讯详情（所有用户都可以查看）
    """
    try:
        # 获取已发布的资讯
        try:
            news = News.objects.get(id=news_id, status='published')
        except News.DoesNotExist:
            return JsonResponse({
                'code': 404,
                'error': '资讯不存在'
            })
        
        # 增加浏览次数
        news.view_count += 1
        news.save()
        
        return JsonResponse({
            'code': 200,
            'data': {
                'news_id': news.id,
                'title': news.title,
                'content': news.content,
                'summary': news.summary,
                'author': news.author.shop_name or news.author.username,
                'view_count': news.view_count,
                'is_top': news.is_top,
                'published_time': news.published_time.strftime('%Y-%m-%d %H:%M:%S') if news.published_time else None,
                'cover_image': settings.DADASHOP_MEDIA + str(news.cover_image) if news.cover_image else None
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'获取失败: {str(e)}'
        })
