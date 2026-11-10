"""Mergington High School activities API."""

from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import logging
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


current_dir = Path(__file__).parent
DATABASE_PATH = Path(os.getenv("USER_DB_PATH", current_dir / "users.sqlite3"))
SESSION_SECRET = os.getenv("APP_SECRET_KEY") or secrets.token_urlsafe(32)
if not os.getenv("APP_SECRET_KEY"):
    logging.warning("APP_SECRET_KEY is unset; sessions will expire when the app restarts")

SESSION_COOKIE = "mergington_session"
SESSION_DURATION = 12 * 60 * 60
PASSWORD_ITERATIONS = 310_000

activities = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"],
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"],
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"],
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"],
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"],
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"],
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"],
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"],
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"],
    },
}


@contextmanager
def database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split(":", maxsplit=1)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            PASSWORD_ITERATIONS,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def public_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "grade": row["grade"],
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def initialize_user_store() -> None:
    with database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                grade TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('student', 'activity_manager', 'admin')),
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'deactivated')),
                created_at TEXT NOT NULL
            )
            """
        )
        user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0:
            email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip().lower()
            password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
            if not email or not password:
                raise RuntimeError(
                    "Set INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD to bootstrap "
                    "the first administrator."
                )
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                raise RuntimeError("INITIAL_ADMIN_EMAIL must be a valid email address.")
            if len(password) < 12:
                raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 12 characters.")
            connection.execute(
                """
                INSERT INTO users (email, name, password_hash, role, status, created_at)
                VALUES (?, 'Administrator', ?, 'admin', 'approved', ?)
                """,
                (email, hash_password(password), datetime.now(timezone.utc).isoformat()),
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_user_store()
    yield


app = FastAPI(
    title="Mergington High School API",
    description="API for viewing and signing up for extracurricular activities",
    lifespan=lifespan,
)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(current_dir, "static")),
    name="static",
)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=100)
    grade: str = Field(default="", max_length=30)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("name", "grade")
    @classmethod
    def trim_text(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if not value and info.field_name == "name":
            raise ValueError("Name cannot be blank.")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    grade: str | None = Field(default=None, max_length=30)

    @field_validator("name", "grade")
    @classmethod
    def trim_optional_text(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value and info.field_name == "name":
            raise ValueError("Name cannot be blank.")
        return value


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "approved", "rejected", "deactivated"] | None = None
    role: Literal["student", "activity_manager", "admin"] | None = None


def make_session(user_id: int) -> str:
    expires_at = int(time.time()) + SESSION_DURATION
    message = f"{user_id}:{expires_at}"
    signature = hmac.new(
        SESSION_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return f"{message}:{signature}"


def authenticated_user(token: str | None) -> sqlite3.Row | None:
    if not token:
        return None
    try:
        user_id_text, expires_text, signature = token.split(":", maxsplit=2)
        user_id = int(user_id_text)
        expires_at = int(expires_text)
    except (ValueError, TypeError):
        return None
    if expires_at <= int(time.time()):
        return None
    message = f"{user_id}:{expires_at}"
    expected = hmac.new(
        SESSION_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    with database() as connection:
        return connection.execute(
            "SELECT * FROM users WHERE id = ? AND status = 'approved'",
            (user_id,),
        ).fetchone()


def optional_user(request: Request) -> dict | None:
    row = authenticated_user(request.cookies.get(SESSION_COOKIE))
    return public_user(row) if row else None


def require_user(request: Request) -> dict:
    user = optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in with an approved account.")
    return user


def require_roles(*roles: str):
    def check(user: Annotated[dict, Depends(require_user)]) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="You are not authorized to do this.")
        return user

    return check


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.post("/auth/register", status_code=201)
def register(payload: RegisterRequest):
    with database() as connection:
        try:
            connection.execute(
                """
                INSERT INTO users (email, name, grade, password_hash, role, status, created_at)
                VALUES (?, ?, ?, ?, 'student', 'pending', ?)
                """,
                (
                    payload.email,
                    payload.name,
                    payload.grade,
                    hash_password(payload.password),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    return {"message": "Account request submitted. Staff will verify your identity before approval."}


@app.post("/auth/login")
def login(payload: LoginRequest, response: Response):
    email = payload.email.strip().lower()
    with database() as connection:
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if user["status"] != "approved":
        raise HTTPException(status_code=403, detail="Account is pending approval or inactive.")
    response.set_cookie(
        SESSION_COOKIE,
        make_session(user["id"]),
        max_age=SESSION_DURATION,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="strict",
        path="/",
    )
    return {"user": public_user(user)}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="strict",
        path="/",
    )
    return {"message": "Signed out."}


@app.get("/me")
def get_profile(user: Annotated[dict, Depends(require_user)]):
    return user


@app.patch("/me")
def update_profile(
    payload: ProfileUpdate,
    user: Annotated[dict, Depends(require_user)],
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Provide profile fields to update.")
    assignments = ", ".join(f"{field} = ?" for field in changes)
    with database() as connection:
        connection.execute(
            f"UPDATE users SET {assignments} WHERE id = ?",
            (*changes.values(), user["id"]),
        )
        updated = connection.execute(
            "SELECT * FROM users WHERE id = ?", (user["id"],)
        ).fetchone()
    return public_user(updated)


@app.get("/admin/users")
def list_users(_: Annotated[dict, Depends(require_roles("admin"))]):
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM users ORDER BY created_at, id"
        ).fetchall()
    return [public_user(row) for row in rows]


@app.patch("/admin/users/{user_id}")
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    admin: Annotated[dict, Depends(require_roles("admin"))],
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="Provide a status or role to update.")
    with database() as connection:
        target = connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            raise HTTPException(status_code=404, detail="User not found.")
        next_role = changes.get("role", target["role"])
        next_status = changes.get("status", target["status"])
        if target["id"] == admin["id"] and (
            next_role != "admin" or next_status != "approved"
        ):
            raise HTTPException(
                status_code=400, detail="You cannot remove your own administrator access."
            )
        if target["role"] == "admin" and target["status"] == "approved" and (
            next_role != "admin" or next_status != "approved"
        ):
            remaining = connection.execute(
                """
                SELECT COUNT(*) FROM users
                WHERE role = 'admin' AND status = 'approved' AND id != ?
                """,
                (target["id"],),
            ).fetchone()[0]
            if remaining == 0:
                raise HTTPException(
                    status_code=400,
                    detail="At least one approved administrator must remain.",
                )
        assignments = ", ".join(f"{field} = ?" for field in changes)
        connection.execute(
            f"UPDATE users SET {assignments} WHERE id = ?",
            (*changes.values(), user_id),
        )
        updated = connection.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return public_user(updated)


@app.get("/activities")
def get_activities(user: Annotated[dict | None, Depends(optional_user)]):
    can_view_roster = bool(user and user["role"] in ("activity_manager", "admin"))
    visible = {}
    for name, details in activities.items():
        participants = details["participants"]
        visible[name] = {
            **details,
            "participant_count": len(participants),
            "participants": (
                list(participants)
                if can_view_roster
                else ([user["email"]] if user and user["email"] in participants else [])
            ),
        }
    return visible


@app.post("/activities/{activity_name}/signup")
def signup(
    activity_name: str,
    user: Annotated[dict, Depends(require_roles("student"))],
):
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")
    participants = activities[activity_name]["participants"]
    if user["email"] in participants:
        raise HTTPException(status_code=400, detail="Student is already signed up")
    participants.append(user["email"])
    return {"message": f"Signed up {user['email']} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister(
    activity_name: str,
    user: Annotated[dict, Depends(require_user)],
    email: str | None = None,
):
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")
    target_email = email.strip().lower() if email else user["email"]
    if target_email != user["email"] and user["role"] not in (
        "activity_manager",
        "admin",
    ):
        raise HTTPException(status_code=403, detail="You can only unregister yourself.")
    participants = activities[activity_name]["participants"]
    if target_email not in participants:
        raise HTTPException(
            status_code=400, detail="Student is not signed up for this activity"
        )
    participants.remove(target_email)
    return {"message": f"Unregistered {target_email} from {activity_name}"}
