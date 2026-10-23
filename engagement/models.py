from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Conversation(models.Model):
    buyer = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT, related_name='purchase_conversations')
    merchant = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT, related_name='shop_conversations')
    buyer_read_id = models.PositiveBigIntegerField(default=0)
    merchant_read_id = models.PositiveBigIntegerField(default=0)
    buyer_hidden = models.BooleanField(default=False)
    merchant_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['buyer', 'merchant'], name='eng_conversation_pair')]
        ordering = ['-updated_at', '-id']


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.PROTECT, related_name='messages')
    sender = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT)
    text = models.TextField(max_length=2000)
    context = models.JSONField(default=dict)
    request_id = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['sender', 'request_id'], name='eng_message_request')]
        indexes = [models.Index(fields=['conversation', 'id'], name='eng_message_cursor')]
        ordering = ['id']


class Review(models.Model):
    order_item = models.OneToOneField('orders.OrderGoods', on_delete=models.PROTECT, related_name='review')
    buyer = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT, related_name='purchase_reviews')
    merchant = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT, related_name='shop_reviews')
    sku = models.ForeignKey('goods.SKU', on_delete=models.PROTECT)
    spu = models.ForeignKey('goods.SPU', on_delete=models.PROTECT)
    purchase_snapshot = models.JSONField(default=dict)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField(max_length=1000)
    is_visible = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.CheckConstraint(check=models.Q(rating__gte=1, rating__lte=5), name='eng_review_stars')]
        indexes = [models.Index(fields=['spu', 'merchant', 'is_visible'], name='eng_review_public')]
        ordering = ['-created_at', '-id']


class ReviewReply(models.Model):
    review = models.OneToOneField(Review, on_delete=models.PROTECT, related_name='reply')
    author = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT)
    text = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)


class ReviewReport(models.Model):
    review = models.ForeignKey(Review, on_delete=models.PROTECT, related_name='reports')
    reporter = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT)
    reason = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['review', 'reporter'], name='eng_review_report_once')]


class ReviewModeration(models.Model):
    review = models.ForeignKey(Review, on_delete=models.PROTECT, related_name='moderations')
    actor = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT)
    was_visible = models.BooleanField()
    is_visible = models.BooleanField()
    reason = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
