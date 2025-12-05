# Assignment Monster Portal

A Django + Djongo (MongoDB) powered portal for the Marketing Team and Super Admin to collaborate on custom job drops, approvals, and profile management.

## Apps

- `accounts`: Custom user model, signup/login flows, profile ownership, and profile update request workflow.
- `marketing`: Role-specific dashboards, job drop form, and all-projects view with filters and attachment handling.
- `superadmin`: Moderation experience for jobs, user approvals, and profile update requests.
- `jobs`: Shared data models, services, statuses, and helpers to generate system IDs and stats.
- `common`: Base layout, components, navbar/sidebar, context processors, and template tags.

## Getting Started

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # optional helper
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

The project expects a MongoDB connection (via Djongo). You can override it temporarily by exporting `USE_SQLITE_FOR_TESTS=1` before running migrations if you only need a lightweight local database while wiring up Mongo.

## Roles At A Glance

- **Marketing Team**: Create jobs, upload instructions/attachments, monitor cards (Total Jobs, Pending Jobs, Total Amount), and request profile updates.
- **Super Admin**: Approve jobs, regenerate content, moderate attachments/sections, approve/reject users, respond to profile update requests, and manage their own profile.

Each primary screen is represented by dedicated templates with reusable components, mirroring the UX spec shared in the brief.
