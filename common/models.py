from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator


class ManagementSystem(models.Model):
    """Configurable management systems controlled by Super Admins."""

    class Keys(models.TextChoices):
        SIGNUP_LOGIN = "signup_login", "Signup & Login Management"
        PROFILE = "profile_management", "Profile Management"
        USER = "user_management", "User Management"
        WEBSITE_CONTENT = "website_content", "Website Content Management"
        TICKETS = "ticket_management", "Ticket Management"
        FORM = "form_management", "Form Management"
        HOLIDAY = "holiday_management", "Holiday Management"

    key = models.CharField(max_length=64, choices=Keys.choices, unique=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True)
    enabled_for_accounts = models.BooleanField(default=True)
    enabled_for_marketing = models.BooleanField(default=True)
    enabled_for_superadmins = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Notice(models.Model):
    """System-wide notice banner."""

    title = models.CharField(max_length=255)
    message = models.TextField()
    start_at = models.DateTimeField(blank=True, null=True)
    end_at = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    show_on_marketing = models.BooleanField(default=True)
    show_on_global = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notices_created",
        on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="notices_updated",
        on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title


class Coupon(models.Model):
    """Coupons that reduce gem costs for global user tasks."""

    class DiscountType(models.TextChoices):
        FIXED = "fixed", "Fixed gems off"
        PERCENT = "percent", "Percent off"

    TASK_CHOICES = [
        ("summary", "Analyze / Summary"),
        ("structure", "Structure"),
        ("content", "Content"),
        ("monster", "Monster"),
    ]

    code = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=16, choices=DiscountType.choices, default=DiscountType.FIXED)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    max_uses_per_user = models.PositiveIntegerField(default=1)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    applies_to_all = models.BooleanField(default=True)
    assigned_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="assigned_coupons")
    applicable_tasks = models.JSONField(default=list, blank=True)  # list of task keys
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="coupons_created",
        on_delete=models.SET_NULL,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-valid_to", "code")

    def __str__(self):
        return self.code

    def is_valid_for_user(self, user):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if self.applies_to_all:
            return True
        return self.assigned_users.filter(pk=getattr(user, "pk", None)).exists()


class CouponRedemption(models.Model):
    """Track coupon usage."""

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coupon_redemptions")
    task_type = models.CharField(max_length=32)
    gems_discounted = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @classmethod
    def _audience_filter(cls, user):
        """Build an audience filter based on the current user's role."""
        try:
            role = getattr(user, "role", None)
            Role = getattr(user, "Role", None)
            if Role and role == Role.MARKETING:
                return models.Q(show_on_marketing=True)
            if Role and role == Role.GLOBAL:
                return models.Q(show_on_global=True)
            if Role and role in {Role.SUPER_ADMIN, Role.CO_SUPER_ADMIN}:
                return models.Q()
        except Exception:
            pass
        return models.Q(show_on_marketing=True)

    @classmethod
    def active_for_user(cls, user):
        """Return active notices filtered for the user's audience."""
        now = timezone.now()
        audience_filter = cls._audience_filter(user)
        return (
            cls.objects.filter(is_active=True)
            .filter(audience_filter)
            .filter(
                models.Q(start_at__lte=now) | models.Q(start_at__isnull=True),
                models.Q(end_at__gte=now) | models.Q(end_at__isnull=True),
            )
            .order_by("-created_at")
        )

    @property
    def is_current(self):
        from django.utils import timezone

        now = timezone.now()
        if not self.is_active:
            return False
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True


class ActivityLog(models.Model):
    """Audit log of user actions and requests."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="activity_logs",
        on_delete=models.SET_NULL,
    )
    path = models.CharField(max_length=512)
    method = models.CharField(max_length=10)
    status_code = models.PositiveIntegerField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True)
    referrer = models.CharField(max_length=512, blank=True)
    duration_ms = models.FloatField(default=0)
    action_type = models.CharField(max_length=64, blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    session_key = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.user} {self.method} {self.path} [{self.status_code}]"


class ErrorLog(models.Model):
    """Captured server-side exceptions for review."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="error_logs",
        on_delete=models.SET_NULL,
    )
    path = models.CharField(max_length=512)
    method = models.CharField(max_length=10)
    status_code = models.PositiveIntegerField(default=500)
    message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True)
    referrer = models.CharField(max_length=512, blank=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="resolved_error_logs",
        on_delete=models.SET_NULL,
    )
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.status_code} {self.path}"


class ActivityLogArchive(models.Model):
    """Archived activity logs (deleted or aged out)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="activity_logs_archived",
        on_delete=models.SET_NULL,
    )
    path = models.CharField(max_length=512)
    method = models.CharField(max_length=10)
    status_code = models.PositiveIntegerField()
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True)
    referrer = models.CharField(max_length=512, blank=True)
    duration_ms = models.FloatField(default=0)
    action_type = models.CharField(max_length=64, blank=True)
    extra_meta = models.JSONField(default=dict, blank=True)
    session_key = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-archived_at",)


class ErrorLogArchive(models.Model):
    """Archived error logs (deleted or aged out)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="error_logs_archived",
        on_delete=models.SET_NULL,
    )
    path = models.CharField(max_length=512)
    method = models.CharField(max_length=10)
    status_code = models.PositiveIntegerField(default=500)
    message = models.TextField(blank=True)
    traceback = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True)
    referrer = models.CharField(max_length=512, blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField()
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-archived_at",)


class GemCostRule(models.Model):
    """Overrides for per-task gem costs, editable by Super Admins."""

    class Keys(models.TextChoices):
        SUMMARY = "summary", "Summary generation"
        STRUCTURE = "structure", "Structure generation"
        CONTENT = "content", "Content generation (per 200 words)"
        MONSTER = "monster", "Monster generation"

    key = models.CharField(max_length=32, choices=Keys.choices, unique=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("key",)

    def __str__(self):
        return f"{self.get_key_display()}: {self.cost}"
