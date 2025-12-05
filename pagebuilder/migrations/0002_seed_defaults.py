from django.db import migrations


def seed_pagebuilder(apps, schema_editor):
    Theme = apps.get_model("pagebuilder", "Theme")
    AnimationPreset = apps.get_model("pagebuilder", "AnimationPreset")
    PageTemplate = apps.get_model("pagebuilder", "PageTemplate")
    PageBlock = apps.get_model("pagebuilder", "PageBlock")

    fade, _ = AnimationPreset.objects.get_or_create(
        name="Fade Up",
        defaults={"css_class": "pb-anim-fade", "duration_ms": 600, "easing": "ease", "delay_ms": 0},
    )

    theme, _ = Theme.objects.get_or_create(
        name="Marketing Default",
        defaults={
            "primary_color": "#0d6efd",
            "secondary_color": "#6c757d",
            "accent_color": "#20c997",
            "background": "linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)",
            "font_family": "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif'",
            "base_font_size": "16px",
            "spacing_scale": [4, 8, 12, 16, 24, 32],
            "radius": "12px",
            "shadow": "0 10px 30px rgba(0,0,0,0.08)",
            "animation": fade,
            "is_active": True,
        },
    )

    def ensure_page(slug, name, desc):
        page, _ = PageTemplate.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": desc,
                "theme": theme,
                "allowed_roles": ["marketing"],
                "managed_by_roles": ["super_admin", "co_super_admin"],
            },
        )
        return page

    def add_block(page, block_type, order, title="", data=None, area="main"):
        PageBlock.objects.update_or_create(
            template=page,
            order=order,
            block_type=block_type,
            defaults={
                "title": title,
                "data": data or {},
                "style": {},
                "area": area,
                "animation": fade,
                "is_active": True,
            },
        )

    welcome = ensure_page(
        "marketing_welcome",
        "Marketing Welcome",
        "Landing view for marketing users.",
    )
    add_block(
        welcome,
        "hero",
        1,
        data={
            "headline": "Welcome, {{user}}",
            "subhead": "Plan your jobs, track approvals, and manage tickets.",
            "buttons": [
                {"label": "Dashboard", "href": "/marketing/dashboard/", "variant": "primary"},
                {"label": "Create Job", "href": "/marketing/create-job/", "variant": "outline-primary"},
            ],
        },
    )
    add_block(
        welcome,
        "card_list",
        2,
        data={"source": "job_cards"},
    )

    dashboard = ensure_page(
        "marketing_dashboard",
        "Marketing Dashboard",
        "Recap of recent jobs and KPIs.",
    )
    add_block(dashboard, "card_list", 1, data={"source": "job_cards"})
    add_block(
        dashboard,
        "text",
        2,
        title="Recent Jobs",
        data={
            "body": "<p>Use the All Projects view to browse every job, or filter by pending.</p>"
        },
    )

    all_projects = ensure_page(
        "marketing_all_projects",
        "All Projects",
        "Tabular view of all marketing jobs.",
    )
    add_block(
        all_projects,
        "table",
        1,
        data={
            "source": "context",
            "key": "table.rows",
            "columns_key": "table.headers",
            "columns": [],
            "empty_message": "No projects matching filter.",
        },
    )

    history = ensure_page(
        "marketing_history",
        "History",
        "Historical jobs list.",
    )
    add_block(
        history,
        "table",
        1,
        data={
            "source": "context",
            "key": "jobs",
            "columns": [
                {"label": "Job ID", "key": "job_id_customer"},
                {"label": "System ID", "key": "system_id"},
                {"label": "Status", "key": "status"},
            ],
        },
    )

    deleted = ensure_page(
        "marketing_deleted_jobs",
        "Deleted Jobs",
        "Soft-deleted jobs list.",
    )
    add_block(
        deleted,
        "table",
        1,
        data={
            "source": "context",
            "key": "jobs",
            "columns": [
                {"label": "Job ID", "key": "job_id_customer"},
                {"label": "System ID", "key": "system_id"},
                {"label": "Deleted At", "key": "deleted_at"},
            ],
            "empty_message": "No deleted jobs.",
        },
    )

    job_detail = ensure_page(
        "marketing_job_detail",
        "Job Detail",
        "Instructions, deadlines, attachments, and content.",
    )
    add_block(
        job_detail,
        "hero",
        1,
        data={
            "headline": "Job Detail",
            "subhead": "Review instructions and generated content.",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("pagebuilder", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_pagebuilder, migrations.RunPython.noop),
    ]
