"""Accounts models covering users and profile update requests."""

from decimal import Decimal, InvalidOperation

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinLengthValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
try:
    from djongo import models as djongo_models
    from bson import ObjectId
except Exception:
    djongo_models = None
    ObjectId = None


class UserManager(BaseUserManager):
    """Custom manager using email as username."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The email address must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.SUPER_ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user storing marketing-specific data."""

    class Role(models.TextChoices):
        MARKETING = "marketing", "Marketing Team"
        SUPER_ADMIN = "super_admin", "Super Admin"
        CO_SUPER_ADMIN = "co_super_admin", "Co Super Admin"
        GLOBAL = "global", "Global User"
        FLOOR = "floor", "Floor User"

    username = None
    email = models.EmailField(unique=True)
    floor_username = models.CharField(
        max_length=32, null=True, blank=True, db_index=True
    )
    role = models.CharField(
        max_length=32, choices=Role.choices, default=Role.MARKETING
    )
    first_name = models.CharField(
        max_length=150,
        help_text="First Name",
    )
    last_name = models.CharField(
        max_length=150,
        help_text="Last Name",
    )
    whatsapp_country_code = models.CharField(max_length=5, default="+91")
    whatsapp_number = models.CharField(
        max_length=10,
        validators=[RegexValidator(r"^\d{10}$", "Enter 10 digit number.")],
    )
    last_qualification = models.CharField(max_length=100)
    employee_id = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    profile_picture = models.ImageField(
        upload_to="profile_pics/", blank=True, null=True
    )
    is_account_approved = models.BooleanField(default=False)
    is_profile_verified = models.BooleanField(default=False)
    last_login_ip = models.CharField(max_length=64, null=True, blank=True)
    last_login_country = models.CharField(max_length=128, null=True, blank=True)
    last_login_timezone = models.CharField(max_length=128, null=True, blank=True)
    # Gems wallet for global users (managed via GemsAccount)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def generate_employee_id(self):
        """
        Employee ID format: FirstInitial + Month(MM) + LastInitial + Year(YY) + serial.
        Example: AM0424010
        """

        join_date = self.date_joined or timezone.now()
        first_initial = (self.first_name or "X")[0].upper()
        last_initial = (self.last_name or "X")[0].upper()
        month = join_date.strftime("%m")
        year = join_date.strftime("%y")
        existing_ids = {
            user.employee_id
            for user in User.objects.all()
            if user.employee_id and user.role == self.role and user.is_account_approved
        }
        serial = len(existing_ids) + 1
        employee_id = f"{first_initial}{month}{last_initial}{year}{serial:03d}"
        while employee_id in existing_ids:
            serial += 1
            employee_id = f"{first_initial}{month}{last_initial}{year}{serial:03d}"
        self.employee_id = employee_id
        return self.employee_id

    def save(self, *args, **kwargs):
        if self.role in {self.Role.SUPER_ADMIN, self.Role.CO_SUPER_ADMIN}:
            self.is_staff = True
        if self.is_account_approved and not self.employee_id:
            self.generate_employee_id()
        # ensure floor usernames don't hold staff flags
        if self.role == self.Role.FLOOR:
            self.is_staff = False
        super().save(*args, **kwargs)

    def generate_floor_username(self):
        import random
        import string

        for _ in range(5):
            candidate = "FLR-" + "".join(
                random.choices(string.ascii_uppercase + string.digits, k=6)
            )
            if not User.objects.filter(floor_username=candidate).exists():
                return candidate
        raise ValueError("Could not generate floor username")


class GemsAccount(models.Model):
    """Tracks gem balance for a user."""

    if djongo_models and hasattr(djongo_models, "ObjectIdField") and ObjectId:
        id = djongo_models.ObjectIdField(primary_key=True, default=ObjectId)
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="gems_account"
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Gems({self.user.email}): {self.balance}"

    @property
    def balance_decimal(self):
        """Return the balance as a Decimal usable in templates."""
        value = self.balance
        if hasattr(value, "to_decimal"):
            value = value.to_decimal()
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError):
            return Decimal("0")


class GemTransaction(models.Model):
    """History of gem credits/debits."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="gem_transactions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gem_transactions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.user.email}: {self.amount} ({self.reason})"


class ProfileUpdateRequest(models.Model):
    """Tracks user profile update requests requiring approval."""

    class RequestType(models.TextChoices):
        PROFILE_PICTURE = "profile_picture", "Profile Picture"
        FIRST_NAME = "first_name", "First Name"
        LAST_NAME = "last_name", "Last Name"
        WHATSAPP = "whatsapp", "WhatsApp No"
        LAST_QUALIFICATION = "last_qualification", "Last Qualification"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    request_type = models.CharField(max_length=32, choices=RequestType.choices)
    current_value = models.TextField(blank=True, null=True)
    updated_value = models.TextField(blank=True, null=True)
    file_upload = models.FileField(upload_to="profile_requests/", blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="processed_requests",
        null=True,
        blank=True,
    )
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.get_request_type_display()}"

    def get_target_field(self):
        mapping = {
            self.RequestType.PROFILE_PICTURE: "profile_picture",
            self.RequestType.FIRST_NAME: "first_name",
            self.RequestType.LAST_NAME: "last_name",
            self.RequestType.WHATSAPP: "whatsapp_number",
            self.RequestType.LAST_QUALIFICATION: "last_qualification",
        }
        return mapping.get(self.request_type)

    def approve(self, admin_user, notes=""):
        self.status = self.Status.APPROVED
        self.processed_by = admin_user
        self.processed_at = timezone.now()
        self.notes = notes
        self.save()
        self.apply_update()

    def reject(self, admin_user, notes=""):
        self.status = self.Status.REJECTED
        self.processed_by = admin_user
        self.processed_at = timezone.now()
        self.notes = notes
        self.save()

    def apply_update(self):
        field_name = self.get_target_field()
        if not field_name:
            return
        if field_name == "profile_picture" and self.file_upload:
            setattr(self.user, field_name, self.file_upload)
        else:
            setattr(self.user, field_name, self.updated_value)
        self.user.save()


class InviteCode(models.Model):
    """Invite codes used to gate floor user signups."""

    code = models.CharField(max_length=16, unique=True)
    max_uses = models.PositiveIntegerField(default=1)
    uses = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        if self.uses >= self.max_uses:
            return False
        return True

    def mark_used(self):
        self.uses += 1
        self.save(update_fields=["uses"])

    def __str__(self):
        return self.code


class FloorSignupRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField()
    whatsapp_country_code = models.CharField(max_length=5, default="+91")
    whatsapp_number = models.CharField(max_length=10, validators=[RegexValidator(r"^\d{10}$", "Enter 10 digit number.")])
    last_qualification = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    generated_username = models.CharField(max_length=32, blank=True)
    generated_password = models.CharField(max_length=64, blank=True)
    request_token = models.CharField(max_length=64, unique=True, default=get_random_string)
    decision_notes = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        related_name="floor_requests_processed",
        on_delete=models.SET_NULL,
    )
    decided_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    creds_viewed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.email} ({self.get_status_display()})"

    def generate_credentials(self):
        """Generate unique username/password for floor login."""
        import random
        import string
        from accounts.models import User  # local import to avoid circular

        chars = string.ascii_uppercase + string.digits
        for _ in range(10):
            username = "FLR-" + "".join(random.choices(chars, k=6))
            if not User.objects.filter(floor_username=username).exists():
                password = get_random_string(12)
                return username, password
        # last resort fallback
        username = "FLR-" + get_random_string(8, allowed_chars=chars)
        password = get_random_string(12)
        return username, password
