from django.conf import settings
from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("common", "0009_merge_gemcost_notice"),
    ]

    operations = [
        migrations.CreateModel(
            name="Coupon",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=64, unique=True)),
                ("description", models.TextField(blank=True)),
                ("discount_type", models.CharField(choices=[("fixed", "Fixed gems off"), ("percent", "Percent off")], default="fixed", max_length=16)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("max_uses_per_user", models.PositiveIntegerField(default=1)),
                ("valid_from", models.DateTimeField()),
                ("valid_to", models.DateTimeField()),
                ("is_active", models.BooleanField(default=True)),
                ("applies_to_all", models.BooleanField(default=True)),
                ("applicable_tasks", models.JSONField(blank=True, default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assigned_users", models.ManyToManyField(blank=True, related_name="assigned_coupons", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="coupons_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-valid_to", "code")},
        ),
        migrations.CreateModel(
            name="CouponRedemption",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("task_type", models.CharField(max_length=32)),
                ("gems_discounted", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("coupon", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="redemptions", to="common.coupon")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="coupon_redemptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
