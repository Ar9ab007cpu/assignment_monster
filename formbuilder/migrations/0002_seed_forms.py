from django.db import migrations


def seed_forms(apps, schema_editor):
    FormDefinition = apps.get_model("formbuilder", "FormDefinition")
    FormField = apps.get_model("formbuilder", "FormField")

    jobs_def, _ = FormDefinition.objects.get_or_create(
        slug="job_drop",
        defaults={
            "name": "Job Drop Form",
            "description": "Config for marketing job submissions.",
            "allowed_roles": ["marketing"],
        },
    )
    job_fields = [
        ("job_id_customer", "Job ID (From Customer)", "text", 1, True, True, False),
        ("instruction", "Instruction", "textarea", 2, True, True, False),
        ("amount_inr", "Amount", "number", 3, True, True, False),
        ("expected_deadline", "Expected Deadline", "datetime", 4, True, True, False),
        ("strict_deadline", "Strict Deadline", "datetime", 5, True, True, False),
        ("attachments", "Attachments", "file", 6, True, False, False),
    ]
    for name, label, ftype, order, required, visible, read_only in job_fields:
        FormField.objects.get_or_create(
            definition=jobs_def,
            name=name,
            defaults={
                "label": label,
                "field_type": ftype,
                "order": order,
                "required_roles": ["marketing"] if required else [],
                "visible_roles": ["marketing"] if visible else [],
                "read_only_roles": [],
                "target_field": name,
                "is_system": name in ("attachments",),
            },
        )

    ticket_def, _ = FormDefinition.objects.get_or_create(
        slug="ticket_create",
        defaults={
            "name": "Ticket Form",
            "description": "Config for ticket submissions.",
            "allowed_roles": ["marketing", "super_admin", "co_super_admin"],
        },
    )
    ticket_fields = [
        ("subject", "Subject", "text", 1, True, True, False),
        ("description", "Description", "textarea", 2, True, True, False),
        ("category", "Category", "select", 3, True, True, False),
        ("job", "Related Job", "select", 4, False, True, False),
        ("requested_expected_deadline", "Requested Expected", "datetime", 5, False, True, False),
        ("requested_strict_deadline", "Requested Strict", "datetime", 6, False, True, False),
    ]
    for name, label, ftype, order, required, visible, read_only in ticket_fields:
        FormField.objects.get_or_create(
            definition=ticket_def,
            name=name,
            defaults={
                "label": label,
                "field_type": ftype,
                "order": order,
                "required_roles": ["marketing"] if required else [],
                "visible_roles": [],
                "read_only_roles": [],
                "target_field": name,
                "is_system": False,
            },
        )

    profile_def, _ = FormDefinition.objects.get_or_create(
        slug="profile_request",
        defaults={
            "name": "Profile Update Request",
            "description": "Config for marketing profile update requests.",
            "allowed_roles": ["marketing"],
        },
    )
    profile_fields = [
        ("request_type", "Request Type", "select", 1, True, True, False),
        ("updated_value", "Updated Value", "text", 2, False, True, False),
        ("file_upload", "File Upload", "file", 3, False, True, False),
        ("notes", "Notes", "textarea", 4, False, True, False),
    ]
    for name, label, ftype, order, required, visible, read_only in profile_fields:
        FormField.objects.get_or_create(
            definition=profile_def,
            name=name,
            defaults={
                "label": label,
                "field_type": ftype,
                "order": order,
                "required_roles": ["marketing"] if required else [],
                "visible_roles": [],
                "read_only_roles": [],
                "target_field": name,
                "is_system": False,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("formbuilder", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_forms, migrations.RunPython.noop),
    ]
