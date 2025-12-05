from django.db import migrations


def seed_nav(apps, schema_editor):
    NavigationItem = apps.get_model("navbuilder", "NavigationItem")
    marketing_items = [
        ("Home", "marketing:welcome", 1, ""),
        ("Dashboard", "marketing:dashboard", 2, "marketing.new_jobs"),
        ("All Projects", "marketing:all_projects", 3, ""),
        ("History", "marketing:history", 4, ""),
        ("Deleted Jobs", "marketing:deleted_jobs", 5, "marketing.deleted_jobs"),
        ("Create Job", "marketing:create_job", 6, ""),
        ("Profile", "accounts:profile", 7, ""),
        ("My Tickets", "tickets:my_tickets", 8, ""),
        ("Ticket Center", "tickets:admin_history", 9, ""),
        ("Logout", "accounts:logout", 10, ""),
    ]
    for order, (label, url_name, position, badge) in enumerate(marketing_items, start=1):
        NavigationItem.objects.get_or_create(
            role="marketing",
            label=label,
            url_name=url_name,
            defaults={
                "order": order,
                "badge_key": badge,
                "is_active": True,
            },
        )

    super_items = [
        ("Home", "superadmin:welcome", 1, ""),
        ("Dashboard", "superadmin:dashboard", 2, ""),
        ("All Jobs", "superadmin:all_jobs", 3, ""),
        ("Deleted Jobs", "superadmin:deleted_jobs", 4, ""),
        ("New Job", "superadmin:new_jobs", 5, "superadmin.new_jobs"),
        ("User Approval", "superadmin:user_approval", 6, "superadmin.user_approvals"),
        ("Profile Update Request", "superadmin:profile_update_requests", 7, "superadmin.profile_requests"),
        ("Profile", "accounts:profile", 8, ""),
        ("My Tickets", "tickets:my_tickets", 9, ""),
        ("Ticket Center", "tickets:admin_history", 10, ""),
        ("Holiday Management", "superadmin:holiday_management", 11, ""),
        ("Form Management", "superadmin:form_management_list", 12, ""),
        ("Logout", "accounts:logout", 13, ""),
    ]
    for order, (label, url_name, position, badge) in enumerate(super_items, start=1):
        NavigationItem.objects.get_or_create(
            role="super_admin",
            label=label,
            url_name=url_name,
            defaults={
                "order": order,
                "badge_key": badge,
                "is_active": True,
            },
        )
        NavigationItem.objects.get_or_create(
            role="co_super_admin",
            label=label,
            url_name=url_name,
            defaults={
                "order": order,
                "badge_key": badge,
                "is_active": True,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("navbuilder", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_nav, migrations.RunPython.noop),
    ]
