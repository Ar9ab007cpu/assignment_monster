from django.db import migrations


def seed_more_forms(apps, schema_editor):
    FormDefinition = apps.get_model("formbuilder", "FormDefinition")
    FormField = apps.get_model("formbuilder", "FormField")

    def ensure_def(slug, name, description, allowed_roles):
        return FormDefinition.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "allowed_roles": allowed_roles,
            },
        )[0]

    def ensure_field(defn, name, label, ftype, order, required_roles, visible_roles, target, is_system=False):
        FormField.objects.get_or_create(
            definition=defn,
            name=name,
            defaults={
                "label": label,
                "field_type": ftype,
                "order": order,
                "required_roles": required_roles,
                "visible_roles": visible_roles,
                "read_only_roles": [],
                "target_field": target,
                "is_system": is_system,
            },
        )

    # Signup form
    signup = ensure_def(
        "signup",
        "Signup Form",
        "User signup configuration.",
        [],
    )
    signup_fields = [
        ("first_name", "First Name", "text", 1, [], [], "first_name"),
        ("last_name", "Last Name", "text", 2, [], [], "last_name"),
        ("email", "Email", "text", 3, [], [], "email"),
        ("whatsapp_country_code", "Country Code", "text", 4, [], [], "whatsapp_country_code"),
        ("whatsapp_number", "WhatsApp Number", "text", 5, [], [], "whatsapp_number"),
        ("last_qualification", "Last Qualification", "text", 6, [], [], "last_qualification"),
        ("password1", "Create Password", "text", 7, [], [], "password1"),
        ("password2", "Confirm Password", "text", 8, [], [], "password2"),
    ]
    for name, label, ftype, order, req, vis, target in signup_fields:
        ensure_field(signup, name, label, ftype, order, req, vis, target)

    # Login form
    login = ensure_def(
        "login",
        "Login Form",
        "Login form configuration.",
        [],
    )
    login_fields = [
        ("username", "Email ID", "text", 1, [], [], "username"),
        ("password", "Password", "text", 2, [], [], "password"),
    ]
    for name, label, ftype, order, req, vis, target in login_fields:
        ensure_field(login, name, label, ftype, order, req, vis, target, is_system=True)

    # Job delete form
    job_delete = ensure_def(
        "job_delete",
        "Job Delete Form",
        "Reason capture for job deletion.",
        ["marketing", "super_admin", "co_super_admin"],
    )
    ensure_field(job_delete, "notes", "Deletion Notes", "textarea", 1, [], [], "notes")


class Migration(migrations.Migration):

    dependencies = [
        ("formbuilder", "0002_seed_forms"),
    ]

    operations = [
        migrations.RunPython(seed_more_forms, migrations.RunPython.noop),
    ]
