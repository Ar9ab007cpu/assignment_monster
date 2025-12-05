from django.db import models

from accounts.models import User


class NavigationItemQuerySet(models.QuerySet):
    def _filter_or_exclude(self, negate, *args, **kwargs):
        if "is_active" in kwargs:
            val = kwargs.pop("is_active")
            kwargs["is_active__in"] = [val]
        return super()._filter_or_exclude(negate, *args, **kwargs)


class NavigationItem(models.Model):
    """Configurable navigation entries per role."""

    role = models.CharField(
        max_length=32, choices=User.Role.choices, db_index=True
    )
    label = models.CharField(max_length=128)
    url_name = models.CharField(max_length=128)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    badge_key = models.CharField(
        max_length=64,
        blank=True,
        help_text="Nav count key like 'marketing.new_jobs' or 'superadmin.user_approvals'.",
    )

    objects = NavigationItemQuerySet.as_manager()

    class Meta:
        ordering = ("role", "order", "id")

    def __str__(self):
        return f"{self.role} - {self.label}"
