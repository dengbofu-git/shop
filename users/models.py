from django.db import models


class Role(models.Model):
    """角色表"""
    ROLE_CHOICES = (
        ('super_admin', '超级管理员'),
        ('admin', '运营管理员'),
        ('customer_service', '客服'),
        ('finance', '财务'),
        ('supplier', '供应商'),
        ('buyer', '买家'),
    )
    
    name = models.CharField(max_length=50, verbose_name="角色名称", unique=True)
    code = models.CharField(max_length=30, verbose_name="角色代码", choices=ROLE_CHOICES, unique=True)
    description = models.TextField(verbose_name="角色描述", blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "users_role"
        verbose_name = "角色"
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return self.name


class Permission(models.Model):
    """权限表"""
    PERMISSION_CHOICES = (
        ('goods_manage', '商品管理'),
        ('order_manage', '订单管理'),
        ('user_manage', '用户管理'),
        ('data_view', '数据查看'),
        ('supplier_manage', '供应商管理'),
        ('inventory_manage', '库存管理'),
        ('logistics_manage', '物流管理'),
        ('finance_manage', '财务管理'),
        ('system_config', '系统配置'),
    )
    
    name = models.CharField(max_length=50, verbose_name="权限名称", unique=True)
    code = models.CharField(max_length=30, verbose_name="权限代码", choices=PERMISSION_CHOICES, unique=True)
    description = models.TextField(verbose_name="权限描述", blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "users_permission"
        verbose_name = "权限"
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return self.name


class RolePermission(models.Model):
    """角色权限关联表"""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, verbose_name="角色")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, verbose_name="权限")
    
    created_time = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "users_role_permission"
        verbose_name = "角色权限"
        verbose_name_plural = verbose_name
        unique_together = ('role', 'permission')
    
    def __str__(self):
        return f"{self.role.name} - {self.permission.name}"


class UserRole(models.Model):
    """用户角色关联表"""
    user_profile = models.ForeignKey('UserProfile', on_delete=models.CASCADE, verbose_name="用户")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, verbose_name="角色")
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "users_user_role"
        verbose_name = "用户角色"
        verbose_name_plural = verbose_name
        unique_together = ('user_profile', 'role')
    
    def __str__(self):
        return f"{self.user_profile.username} - {self.role.name}"


class UserProfile(models.Model):
    """用户表"""
    # 用户类型选择
    USER_TYPE_CHOICES = (
        ('customer', '客户'),
        ('merchant', '店家'),
    )
    
    # 用户名、密码、邮箱、手机号、是否激活、创建时间、更新时间
    username = models.CharField(max_length=11, verbose_name="用户名", unique=True)
    password = models.CharField(max_length=32)
    email = models.EmailField()
    phone = models.CharField(max_length=11)
    is_active = models.BooleanField(default=False, verbose_name="是否激活")
    user_type = models.CharField(
        max_length=10, 
        choices=USER_TYPE_CHOICES, 
        default='customer',
        verbose_name="用户类型"
    )
    # 店家信息（仅店家账号使用）
    shop_name = models.CharField(max_length=50, verbose_name="店铺名称", blank=True, null=True)
    shop_description = models.TextField(verbose_name="店铺描述", blank=True, null=True)

    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    # 修改表名
    class Meta:
        # 表名: 应用名_类名非驼峰
        db_table = "users_user_profile"
    
    def is_merchant(self):
        """判断是否为店家"""
        return self.user_type == 'merchant'
    
    def is_customer(self):
        """判断是否为客户"""
        return self.user_type == 'customer'
    
    def get_roles(self):
        """获取用户的所有角色"""
        return Role.objects.filter(userrole__user_profile=self)
    
    def has_role(self, role_code):
        """检查用户是否拥有指定角色"""
        return self.userrole_set.filter(role__code=role_code).exists()
    
    def has_permission(self, permission_code):
        """检查用户是否拥有指定权限"""
        # 获取用户的所有角色
        roles = self.get_roles()
        # 检查这些角色是否拥有指定权限
        return RolePermission.objects.filter(
            role__in=roles,
            permission__code=permission_code
        ).exists()
    
    def get_permissions(self):
        """获取用户的所有权限"""
        roles = self.get_roles()
        permissions = Permission.objects.filter(
            rolepermission__role__in=roles
        ).distinct()
        return permissions


class Address(models.Model):
    """
        收货地址表
        用户表:地址表 ---> 1:n
    """
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    # 收件人 地址 邮编 手机号
    receiver = models.CharField(verbose_name="收件人", max_length=10)
    address = models.CharField(verbose_name="收件地址", max_length=100)
    postcode = models.CharField(verbose_name="邮编", max_length=6)
    receiver_mobile = models.CharField(verbose_name="手机号", max_length=11)
    # 标签 默认地址
    tag = models.CharField(verbose_name="标签", max_length=10)
    is_default = models.BooleanField(verbose_name="默认地址", default=False)
    # 伪删除
    is_delete = models.BooleanField(verbose_name="伪删除", default=False)

    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    # 修改表名
    class Meta:
        # 表名: 应用名_类名非驼峰
        db_table = "users_address"

class WeiboProfile(models.Model):
    """
        微博表
        微博表:用户表 ---> 1:1
    """
    # 微博扫码登录时,暂且不知道和哪个用户绑定
    # 用户输入完成用户信息后,再更新外键的值即可
    user_profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, null=True)
    wuid = models.CharField(verbose_name="微博uid", max_length=10, db_index=True, unique=True)
    access_token = models.CharField(verbose_name="授权令牌", max_length=32)
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users_weibo_profile"