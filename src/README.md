# Mergington High School Activities API

The FastAPI application provides public activity browsing, student account
requests, account approval, and role-protected enrollment management.

## Setup

Install dependencies and configure the first administrator before starting:

```sh
pip install -r requirements.txt
export INITIAL_ADMIN_EMAIL=admin@mergington.edu
export INITIAL_ADMIN_PASSWORD='use-a-unique-password-of-at-least-12-characters'
export APP_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
uvicorn app:app --app-dir src --reload
```

The first startup creates the initial administrator in the SQLite user database.
The password is stored as a salted PBKDF2 hash. The initial-admin variables are
only used when the database contains no users. By default, the database is
`src/users.sqlite3`; set `USER_DB_PATH` to store it elsewhere and include the
database in your backup plan.

Set a stable, random `APP_SECRET_KEY` in the deployment environment. If it is
omitted, a random development key is generated and sessions expire when the app
restarts. In production, serve the app over HTTPS and set `COOKIE_SECURE=true`.

Students request an account with their name, email, optional grade, and a
password. Requests remain pending until an administrator verifies the person's
identity through the school's trusted process and approves the account. The
email entered in the form is not treated as proof of identity. Administrators
can also reject requests, assign `student`, `activity_manager`, or `admin`
roles, and deactivate users without deleting their history. At least one
approved administrator must remain active.

Activity names, schedules, and participant counts remain public. Participant
email rosters are visible only to activity managers and administrators;
students see only their own enrollment. Enrollment requires an approved
student account, and a student can only change their own enrollment. The user
database persists accounts; the existing activity catalog and enrollments
remain in memory and reset when the application restarts.

Sessions use signed, HTTP-only, same-site cookies and expire after 12 hours.

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/activities` | Browse activities and public participant counts |
| `POST` | `/auth/register` | Submit a pending student account request |
| `POST` | `/auth/login` | Sign in and set a session cookie |
| `POST` | `/auth/logout` | Clear the session cookie |
| `GET`, `PATCH` | `/me` | View or update the signed-in user's profile |
| `GET` | `/admin/users` | List accounts (admin only) |
| `PATCH` | `/admin/users/{user_id}` | Approve/reject/deactivate and assign a role (admin only) |
| `POST` | `/activities/{activity_name}/signup` | Sign up the authenticated student |
| `DELETE` | `/activities/{activity_name}/unregister` | Unregister self; staff may manage other enrollments |

Interactive API documentation is available at `/docs`.
