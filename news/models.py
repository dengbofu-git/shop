from django.db import models
from users.models import UserProfile


class News(models.Model):
    """
    资讯表
    店家可以发布资讯
    """
    STATUS_CHOICES = (
        ('draft', '草稿'),
        ('published', '已发布'),
        ('deleted', '已删除'),
    )
    
    title = models.CharField(max_length=200, verbose_name="标题")
    content = models.TextField(verbose_name="内容")
    summary = models.CharField(max_length=500, verbose_name="摘要", blank=True, null=True)
    cover_image = models.ImageField(verbose_name="封面图片", upload_to='news', blank=True, null=True)
    author = models.ForeignKey(UserProfile, on_delete=models.CASCADE, verbose_name="作者", related_name='news')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', verbose_name="状态")
    view_count = models.IntegerField(default=0, verbose_name="浏览次数")
    is_top = models.BooleanField(default=False, verbose_name="是否置顶")
    
    created_time = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_time = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    published_time = models.DateTimeField(verbose_name="发布时间", blank=True, null=True)
    
    class Meta:
        db_table = "news_news"
        verbose_name = '资讯'
        verbose_name_plural = verbose_name
        ordering = ['-is_top', '-published_time', '-created_time']
    
    def __str__(self):
        return self.title
