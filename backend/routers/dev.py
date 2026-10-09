import re
import json
import datetime
import secrets

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import db_engine
from schemas import DevCreateUserRequest, DevUpdateUserRequest, DevInviteRequest
from dependencies import get_current_user, require_dev, require_db, can_manage_user
from security import (
    hash_password, verify_password, calculate_password_expiry,
    decode_password_schedule, valid_interval, add_interval,
    USERNAME_REGEX, PASSWORD_REGEX,
)
from email_service import issue_expired_password_reset, token_digest
from config import cprint
router = APIRouter()


@router.get("/api/dev/chat-sessions")
async def dev_list_chat_sessions(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    query = """
        SELECT s.id, s.user_id, s.title, s.created_at, s.updated_at
        FROM chat_sessions s
        JOIN users u ON u.id=s.user_id
    """
    if current_user["role"] == "admin":
        query += "WHERE u.role <> 'dev' "
    query += "ORDER BY s.id"
    with db_engine.connect() as conn:
        rows = conn.execute(text(query)).fetchall()
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "title": r[2],
            "created_at": str(r[3]),
            "updated_at": str(r[4]),
        }
        for r in rows
    ]


@router.get("/api/dev/chat-messages")
async def dev_list_chat_messages(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    query = """
        SELECT m.id, m.session_id, m.role, m.content, m.created_at
        FROM chat_messages m
        JOIN chat_sessions s ON s.id=m.session_id
        JOIN users u ON u.id=s.user_id
    """
    if current_user["role"] == "admin":
        query += "WHERE u.role <> 'dev' "
    query += "ORDER BY m.id"
    with db_engine.connect() as conn:
        rows = conn.execute(text(query)).fetchall()
    return [
        {
            "id": r[0],
            "session_id": r[1],
            "role": r[2],
            "content": r[3],
            "created_at": str(r[4]),
        }
        for r in rows
    ]


@router.get("/api/dev/users")
async def dev_list_users(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    query = """
        SELECT
            u.id,
            u.username,
            u.email,
            u.role,
            u.created_at,
            COALESCE(p.first_name, ''),
            COALESCE(p.last_name, ''),
            COALESCE(p.company_name, ''),
            COALESCE(p.department, ''),
            COALESCE(p.phone, ''),
            u.account_status,
            u.account_expires_at,
            u.password_policy_type,
            u.password_policy_repeat,
            u.password_policy_interval,
            u.password_policy_unit,
            u.password_policy_on,
            u.password_policy_month,
            u.password_policy_date,
            u.password_policy_anchor,
            u.password_policy_schedule,
            u.password_expires_at,
            u.account_expiry_mode,
            u.account_expiry_duration,
            u.account_expiry_unit,
            COALESCE(t.tokens, 0)
        FROM users u
        LEFT JOIN user_profiles p ON p.user_id = u.id
        LEFT JOIN user_tokens t ON t.user_id = u.id
    """
    if current_user["role"] == "admin":
        query += "WHERE u.role <> 'dev' "
    query += "ORDER BY u.id"
    with db_engine.connect() as conn:
        rows = conn.execute(text(query)).fetchall()
    return [
        {
            "id": r[0],
            "username": r[1],
            "email": r[2],
            "role": r[3],
            "created_at": str(r[4]),
            "first_name": r[5],
            "last_name": r[6],
            "company_name": r[7],
            "department": r[8],
            "phone": r[9],
            "account_status": r[10],
            "account_expires_at": str(r[11]) if r[11] else None,
            "password_policy_type": r[12],
            "password_policy_repeat": r[13],
            "password_policy_interval": r[14],
            "password_policy_unit": r[15],
            "password_policy_on": r[16],
            "password_policy_month": r[17],
            "password_policy_date": str(r[18]) if r[18] else None,
            "password_policy_anchor": str(r[19]) if r[19] else None,
            "password_policy_schedule": decode_password_schedule(r[20]),
            "password_expires_at": str(r[21]) if r[21] else None,
            "account_expiry_mode": r[22],
            "account_expiry_duration": r[23],
            "account_expiry_unit": r[24],
            "tokens": r[25],
        }
        for r in rows
    ]


@router.get("/api/dev/invitations")
async def dev_list_invitations(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    with db_engine.begin() as conn:
        rows = conn.execute(text("""
              SELECT i.id, i.email, i.company_name, i.department, i.status, i.created_at,
                   CASE WHEN :viewer_role='admin' AND u.role='dev' THEN ''
                        ELSE COALESCE(u.username, '') END
            FROM user_invitations i
            LEFT JOIN users u ON u.id=i.invited_by
            ORDER BY i.created_at DESC
            LIMIT 100
        """), {"viewer_role": current_user["role"]}).fetchall()
    return [{
        "id": r[0],
        "email": r[1],
        "company_name": r[2] or "",
        "department": r[3] or "",
        "status": r[4],
        "created_date": r[5].strftime("%Y-%m-%d") if hasattr(r[5], "strftime") else str(r[5])[:10],
        "invited_by": r[6],
    } for r in rows]


@router.post("/api/dev/invitations")
async def dev_create_invitation(
    req: DevInviteRequest,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    email = req.email.strip().lower()
    company_name = req.company_name.strip()[:150]
    department = req.department.strip()[:100]
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return JSONResponse(status_code=400, content={"error": "Enter a valid email address."})

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime(2099, 12, 31, 23, 59, 59, tzinfo=datetime.timezone.utc)
    invitation_id = None
    with db_engine.begin() as conn:
        account = conn.execute(
            text("SELECT id FROM users WHERE LOWER(email)=:email"), {"email": email}
        ).fetchone()
        if account:
            return JSONResponse(status_code=409, content={"error": "An account already uses this email."})

        existing = conn.execute(text("""
            SELECT id, status, expires_at FROM user_invitations
            WHERE LOWER(email)=:email
        """), {"email": email}).fetchone()
        if existing and existing[1] == "pending" and existing[2] > datetime.datetime.now(datetime.timezone.utc):
            return JSONResponse(status_code=409, content={"error": "An active invitation already exists for this email."})
        if existing:
            invitation_id = existing[0]
            conn.execute(text("""
                UPDATE user_invitations
                SET company_name=:company_name, department=:department, invited_by=:invited_by,
                    invitation_token=:token_hash, expires_at=:expires_at,
                    status='pending', created_at=NOW()
                WHERE id=:id
            """), {
                "company_name": company_name,
                "department": department,
                "invited_by": current_user["id"],
                "token_hash": token_digest(raw_token),
                "expires_at": expires_at,
                "id": existing[0],
            })
        else:
            result = conn.execute(text("""
                INSERT INTO user_invitations
                    (email, company_name, department, invited_by, invitation_token, expires_at)
                VALUES (:email, :company_name, :department, :invited_by, :token_hash, :expires_at)
            """), {
                "email": email,
                "company_name": company_name,
                "department": department,
                "invited_by": current_user["id"],
                "token_hash": token_digest(raw_token),
                "expires_at": expires_at,
            })
            invitation_id = result.lastrowid
    invite_url = f"/account-action?mode=invite&token={raw_token}"
    return {
        "message": "Invitation created. Share this link with the user.",
        "invitation_id": invitation_id,
        "url": invite_url,
        "expires_date": expires_at.strftime("%Y-%m-%d"),
    }


@router.post("/api/dev/invitations/{invitation_id}/link")
async def dev_create_invitation_link(
    invitation_id: int,
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    raw_token = secrets.token_urlsafe(32)
    with db_engine.begin() as conn:
        invitation = conn.execute(text("""
            SELECT id, email FROM user_invitations
            WHERE id=:id AND status='pending'
            FOR UPDATE
        """), {"id": invitation_id}).fetchone()
        if not invitation:
            return JSONResponse(status_code=404, content={"error": "Pending invitation not found."})
        conn.execute(text("""
            UPDATE user_invitations
            SET invitation_token=:token_hash
            WHERE id=:id
        """), {
            "token_hash": token_digest(raw_token),
            "id": invitation_id,
        })
    invite_url = f"/account-action?mode=invite&token={raw_token}"
    return {
        "message": "New invitation link generated. Share this link with the user.",
        "url": invite_url,
    }


@router.delete("/api/dev/invitations/history")
async def dev_clear_invitations_history(
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    with db_engine.begin() as conn:
        result = conn.execute(text("DELETE FROM user_invitations WHERE status != 'pending'"))
    return {"message": f"Cleared {result.rowcount} inactive invitations."}

@router.delete("/api/dev/invitations/{invitation_id}")
async def dev_revoke_invitation(
    invitation_id: int,
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    with db_engine.connect() as conn:
        result = conn.execute(text("""
            UPDATE user_invitations SET status='revoked'
            WHERE id=:id AND status='pending'
        """), {"id": invitation_id})
        conn.commit()
    if result.rowcount == 0:
        return JSONResponse(status_code=404, content={"error": "Pending invitation not found."})
    return {"message": "Invitation revoked."}


@router.get("/api/dev/password-reset-requests")
async def dev_list_password_reset_requests(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    with db_engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT r.id, u.username, u.email, r.status, r.requested_at,
                   COALESCE(p.first_name, ''), COALESCE(p.last_name, ''),
                   COALESCE(p.company_name, ''), u.id
            FROM password_reset_requests r
            JOIN users u ON u.id=r.user_id
            LEFT JOIN user_profiles p ON p.user_id=u.id
            WHERE (:viewer_role <> 'admin' OR u.role <> 'dev')
            ORDER BY r.requested_at DESC
            LIMIT 100
        """), {"viewer_role": current_user["role"]}).fetchall()
    return [{
        "id": r[0],
        "username": r[1],
        "email": r[2],
        "status": r[3],
        "requested_date": r[4].strftime("%Y-%m-%d") if hasattr(r[4], "strftime") else str(r[4])[:10],
        "first_name": r[5],
        "last_name": r[6],
        "company_name": r[7],
        "user_id": r[8],
    } for r in rows]


@router.post("/api/dev/password-reset-requests/{request_id}/issue")
async def dev_issue_password_reset(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    raw_token = secrets.token_urlsafe(32)
    with db_engine.begin() as conn:
        reset_request = conn.execute(text("""
            SELECT r.user_id, u.role, u.email FROM password_reset_requests r
            JOIN users u ON u.id=r.user_id
            WHERE r.id=:id AND r.status IN ('requested', 'issued')
            FOR UPDATE
        """), {"id": request_id}).fetchone()
        if not reset_request or (current_user["role"] == "admin" and reset_request[1] == "dev"):
            return JSONResponse(status_code=404, content={"error": "Pending reset request not found."})
        conn.execute(text("""
            UPDATE password_reset_tokens SET used_at=NOW()
            WHERE user_id=:uid AND used_at IS NULL
        """), {"uid": reset_request[0]})
        conn.execute(text("""
            INSERT INTO password_reset_tokens (user_id, token)
            VALUES (:uid, :token_hash)
        """), {
            "uid": reset_request[0],
            "token_hash": token_digest(raw_token),
        })
        conn.execute(text("""
            UPDATE password_reset_requests
            SET status='issued', handled_by=:admin_id
            WHERE id=:id
        """), {"admin_id": current_user["id"], "id": request_id})
    reset_url = f"/account-action?mode=reset&token={raw_token}"
    return {
        "message": "Reset link generated. Share this link with the user.",
        "url": reset_url,
    }

@router.delete("/api/dev/password-reset-requests/history")
async def dev_clear_password_reset_history(
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    with db_engine.begin() as conn:
        conn.execute(text("DELETE FROM password_reset_requests WHERE status NOT IN ('requested', 'issued')"))
    return {"message": "History cleared successfully."}



@router.delete("/api/dev/password-reset-requests/{request_id}")
async def dev_revoke_password_reset(
    request_id: int,
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_dev),
    _db: None = Depends(require_db),
):
    with db_engine.begin() as conn:
        reset_request = conn.execute(text("""
            SELECT r.user_id, u.role FROM password_reset_requests r
            JOIN users u ON u.id=r.user_id
            WHERE r.id=:id AND r.status IN ('requested', 'issued')
            FOR UPDATE
        """), {"id": request_id}).fetchone()
        if not reset_request or (current_user["role"] == "admin" and reset_request[1] == "dev"):
            return JSONResponse(status_code=404, content={"error": "Active reset request not found."})
        conn.execute(text("""
            UPDATE password_reset_tokens SET used_at=NOW()
            WHERE user_id=:uid AND used_at IS NULL
        """), {"uid": reset_request[0]})
        conn.execute(text("""
            UPDATE password_reset_requests
            SET status='cancelled', handled_by=:admin_id
            WHERE id=:id
        """), {"admin_id": current_user["id"], "id": request_id})
    return {"message": "Password reset request revoked."}


@router.post("/api/dev/users")
async def dev_create_user(req: DevCreateUserRequest, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    if current_user["role"] == "admin" and req.role == "dev":
        return JSONResponse(status_code=403, content={"error": "Admin cannot create dev accounts."})
    if not USERNAME_REGEX.match(req.username):
        return JSONResponse(status_code=400, content={"error": "Invalid username format."})
    try:
        with db_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT id FROM users WHERE username=:u OR email=:e"),
                {"u": req.username, "e": req.email},
            ).fetchone()
            if exists:
                return JSONResponse(status_code=400, content={"error": "Username or email already exists."})
            conn.execute(
                text("INSERT INTO users (username,email,password_hash,role) VALUES (:u,:e,:p,:r)"),
                {"u": req.username, "e": req.email, "p": hash_password(req.password), "r": req.role},
            )
            conn.commit()
        return {"message": f"Account '{req.username}' [{req.role}] created."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.put("/api/dev/users/{user_id}")
async def dev_update_user(user_id: int, req: DevUpdateUserRequest, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    profile_limits = {"first_name": 100, "last_name": 100, "company_name": 150, "department": 100, "phone": 50}
    profile_updates = {}
    for field, max_length in profile_limits.items():
        value = getattr(req, field)
        if value is not None:
            value = value.strip()
            if field == "phone" and value:
                p_clean = re.sub(r'[\s\-\(\)]', '', value)
                if p_clean.startswith("+62"): value = "0" + p_clean[3:]
                elif p_clean.startswith("62"): value = "0" + p_clean[2:]
                else:
                    value = re.sub(r'[\-\(\)]', '', value).strip()
                    value = re.sub(r'\s+', ' ', value)
                    if value.startswith('+') and ' ' not in value:
                        for cc in ['+65', '+60', '+673', '+61', '+1', '+44', '+91', '+971']:
                            if value.startswith(cc):
                                value = cc + " " + value[len(cc):]
                                break
                if not re.fullmatch(r"\+?[0-9\s]{5,20}", value):
                    return JSONResponse(status_code=400, content={"error": "Enter a valid phone number."})
            if len(value) > max_length:
                return JSONResponse(status_code=400, content={"error": f"{field.replace('_', ' ').title()} is too long."})
            profile_updates[field] = value

    with db_engine.begin() as conn:
        target = conn.execute(text("""
            SELECT role, password_hash, account_status, account_expires_at,
                   password_policy_type, password_policy_repeat, password_policy_interval,
                   password_policy_unit, password_policy_on, password_policy_month,
                   password_policy_date, password_policy_anchor, password_policy_schedule
            FROM users WHERE id=:id
        """), {"id": user_id}).fetchone()
        if not target:
            return JSONResponse(status_code=404, content={"error": "User not found."})
        if target[0] == "dev" and any(
            value is not None for value in (req.username, req.email, req.role)
        ):
            return JSONResponse(status_code=403, content={"error": "Developer username, email, and role are locked."})
        if not can_manage_user(current_user["role"], target[0]):
            return JSONResponse(status_code=403, content={"error": "You are not allowed to manage this account."})
        if user_id == current_user["id"] and req.account_status == "suspended":
            return JSONResponse(status_code=400, content={"error": "You cannot suspend your own account."})
        if current_user["role"] == "admin" and req.role == "dev":
            return JSONResponse(status_code=403, content={"error": "Admin cannot change a user to dev role."})

        updates, params = [], {"id": user_id}
        if req.username is not None:
            username = req.username.strip()
            if not USERNAME_REGEX.fullmatch(username):
                return JSONResponse(status_code=400, content={"error": "Invalid username format."})
            updates.append("username=:username")
            params["username"] = username
        if req.email is not None:
            email = req.email.strip().lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return JSONResponse(status_code=400, content={"error": "Enter a valid email address."})
            updates.append("email=:email")
            params["email"] = email
        if req.password:
            if not PASSWORD_REGEX.fullmatch(req.password):
                return JSONResponse(status_code=400, content={"error": "Password must include uppercase, lowercase, number, and symbol (8+ characters)."})
            if verify_password(req.password, target[1]):
                return JSONResponse(status_code=400, content={"error": "Choose a password different from the current password."})
            updates.append("password_hash=:ph")
            params["ph"] = hash_password(req.password)
        if req.role is not None:
            if req.role not in ("user", "admin", "dev"):
                return JSONResponse(status_code=400, content={"error": "Invalid role."})
            updates.append("role=:role")
            params["role"] = req.role

        if req.account_status is not None:
            if req.account_status not in ("active", "suspended", "deactivated"):
                return JSONResponse(status_code=400, content={"error": "Invalid account status."})
            updates.append("account_status=:account_status")
            params["account_status"] = req.account_status

        now = datetime.datetime.now()
        if req.account_expiry_mode is not None:
            if req.account_expiry_mode == "none":
                account_expires_at = None
                account_expiry_duration = None
                account_expiry_unit = None
            elif req.account_expiry_mode == "duration":
                if not valid_interval(req.account_expiry_duration, req.account_expiry_unit):
                    return JSONResponse(status_code=400, content={"error": "Choose a valid account expiry unit."})
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                now_gmt7 = now_utc + datetime.timedelta(hours=7)
                today_00_gmt7 = now_gmt7.replace(hour=0, minute=0, second=0, microsecond=0)
                duration = max(1, req.account_expiry_duration) if req.account_expiry_unit == 'day' else (req.account_expiry_duration or 1)
                target_gmt7 = add_interval(today_00_gmt7, duration, req.account_expiry_unit)
                account_expires_at = (target_gmt7 - datetime.timedelta(hours=7)).replace(tzinfo=None)
                account_expiry_duration = req.account_expiry_duration
                account_expiry_unit = req.account_expiry_unit
            elif req.account_expiry_mode == "date":
                try:
                    account_expires_at = datetime.datetime.strptime(
                        req.account_expiry_date or "", "%Y-%m-%d"
                    ) - datetime.timedelta(hours=7)
                except ValueError:
                    return JSONResponse(status_code=400, content={"error": "Choose a valid account expiry date."})
                if account_expires_at <= now:
                    return JSONResponse(status_code=400, content={"error": "Account expiry date must be in the future."})
                account_expiry_duration = None
                account_expiry_unit = None
            else:
                return JSONResponse(status_code=400, content={"error": "Invalid account expiry mode."})
            updates.extend([
                "account_expires_at=:account_expires_at",
                "account_expiry_mode=:account_expiry_mode",
                "account_expiry_duration=:account_expiry_duration",
                "account_expiry_unit=:account_expiry_unit",
            ])
            params.update({
                "account_expires_at": account_expires_at,
                "account_expiry_mode": req.account_expiry_mode,
                "account_expiry_duration": account_expiry_duration,
                "account_expiry_unit": account_expiry_unit,
            })

        if req.password_policy_type is not None:
            policy_type = req.password_policy_type
            policy_repeat = req.password_policy_repeat or "once"
            policy_interval = req.password_policy_interval
            policy_unit = req.password_policy_unit
            policy_on = req.password_policy_on
            policy_month = req.password_policy_month
            policy_date = None
            policy_schedule = req.password_policy_schedule or []
            policy_anchor = now.date() if policy_repeat == "repeat" else None
            if policy_type not in ("none", "duration", "date"):
                return JSONResponse(status_code=400, content={"error": "Invalid password expiry policy."})
            if policy_repeat not in ("once", "repeat"):
                return JSONResponse(status_code=400, content={"error": "Choose once or repeat for the password policy."})
            if policy_type == "duration":
                if not valid_interval(policy_interval, policy_unit):
                    return JSONResponse(status_code=400, content={"error": "Choose a valid password duration unit."})
                if policy_unit == 'day':
                    policy_interval = max(1, policy_interval or 1)
            elif policy_type == "date":
                if policy_repeat == "once":
                    try:
                        policy_date = datetime.datetime.strptime(
                            req.password_policy_date or "", "%Y-%m-%d"
                        ) - datetime.timedelta(hours=7)
                    except ValueError:
                        return JSONResponse(status_code=400, content={"error": "Choose a valid password expiry date."})
                    if policy_date <= now:
                        return JSONResponse(status_code=400, content={"error": "Password expiry date must be in the future."})
                else:
                    if not valid_interval(policy_interval, policy_unit):
                        return JSONResponse(status_code=400, content={"error": "Choose a valid repeat unit."})
                    if policy_unit == "week":
                        policy_schedule = sorted({value for value in policy_schedule if isinstance(value, int) and 1 <= value <= 7})
                        if not policy_schedule:
                            return JSONResponse(status_code=400, content={"error": "Select at least one weekday."})
                        policy_on = policy_schedule[0]
                    elif policy_unit == "month":
                        policy_schedule = sorted({value for value in policy_schedule if isinstance(value, int) and 1 <= value <= 31})
                        if not policy_schedule:
                            return JSONResponse(status_code=400, content={"error": "Select at least one date of the month."})
                        policy_on = policy_schedule[0]
                    elif policy_unit == "year":
                        policy_schedule = [
                            {"month": value.get("month"), "day": value.get("day")}
                            for value in policy_schedule
                            if isinstance(value, dict)
                            and isinstance(value.get("month"), int) and 1 <= value["month"] <= 12
                            and isinstance(value.get("day"), int) and 1 <= value["day"] <= 31
                        ]
                        if not policy_schedule:
                            return JSONResponse(status_code=400, content={"error": "Select at least one month and date."})
                        policy_month = policy_schedule[0]["month"]
                        policy_on = policy_schedule[0]["day"]
                    else:
                        policy_schedule = []
            elif policy_type == "none":
                policy_repeat = "once"
                policy_interval = policy_on = policy_month = policy_unit = policy_date = policy_anchor = None
                policy_schedule = []

            updates.extend([
                "password_policy_type=:password_policy_type",
                "password_policy_repeat=:password_policy_repeat",
                "password_policy_interval=:password_policy_interval",
                "password_policy_unit=:password_policy_unit",
                "password_policy_on=:password_policy_on",
                "password_policy_month=:password_policy_month",
                "password_policy_date=:password_policy_date",
                "password_policy_anchor=:password_policy_anchor",
                "password_policy_schedule=:password_policy_schedule",
                "password_policy_months=NULL",
                "password_policy_day=NULL",
                "password_expires_at=:password_expires_at",
            ])
            params.update({
                "password_policy_type": policy_type,
                "password_policy_repeat": policy_repeat,
                "password_policy_interval": policy_interval,
                "password_policy_unit": policy_unit,
                "password_policy_on": policy_on,
                "password_policy_month": policy_month,
                "password_policy_date": policy_date,
                "password_policy_anchor": policy_anchor,
                "password_policy_schedule": json.dumps(policy_schedule) if policy_schedule else None,
                "password_expires_at": calculate_password_expiry(
                    policy_type, policy_repeat, policy_interval, policy_unit,
                    policy_on, policy_month, policy_date, policy_anchor, policy_schedule, now,
                ),
            })
        elif req.password:
            params["password_expires_at"] = calculate_password_expiry(
                target[4], target[5], target[6], target[7], target[8],
                target[9], target[10], target[11], decode_password_schedule(target[12]), now,
            )
            updates.append("password_expires_at=:password_expires_at")

        if req.username is not None or req.email is not None:
            duplicate = conn.execute(text("""
                SELECT id FROM users
                WHERE id<>:id AND (
                    (:username IS NOT NULL AND username=:username)
                    OR (:email IS NOT NULL AND LOWER(email)=:email)
                )
                LIMIT 1
            """), {
                "id": user_id,
                "username": params.get("username"),
                "email": params.get("email"),
            }).fetchone()
            if duplicate:
                return JSONResponse(status_code=409, content={"error": "Username or email is already in use."})

        if not updates and not profile_updates and req.tokens is None:
            return JSONResponse(status_code=400, content={"error": "No fields to update."})
        if updates:
            conn.execute(text(f"UPDATE users SET {', '.join(updates)} WHERE id=:id"), params)
        if req.tokens is not None:
            conn.execute(text("""
                INSERT INTO user_tokens (user_id, tokens) VALUES (:id, :tokens)
                ON DUPLICATE KEY UPDATE tokens = :tokens
            """), {"id": user_id, "tokens": req.tokens})
        if profile_updates:
            profile = conn.execute(text("""
                SELECT first_name, last_name, company_name, department, phone
                FROM user_profiles WHERE user_id=:id
            """), {"id": user_id}).fetchone()
            profile_values = dict(zip(
                ("first_name", "last_name", "company_name", "department", "phone"),
                profile or ("", "", "", "", ""),
            ))
            profile_values.update(profile_updates)
            conn.execute(text("""
                INSERT INTO user_profiles
                    (user_id, first_name, last_name, company_name, department, phone)
                VALUES (:id, :first_name, :last_name, :company_name, :department, :phone)
                ON DUPLICATE KEY UPDATE
                    first_name=VALUES(first_name), last_name=VALUES(last_name),
                    company_name=VALUES(company_name), department=VALUES(department),
                    phone=VALUES(phone)
            """), {"id": user_id, **profile_values})
    return {"message": f"User id={user_id} updated."}

@router.post("/api/dev/users/{user_id}/send-reset")
async def dev_send_password_reset(user_id: int, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    try:
        with db_engine.connect() as conn:
            row = conn.execute(text("SELECT email, role FROM users WHERE id=:id"), {"id": user_id}).fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"error": "User not found."})
        if current_user["role"] == "admin" and row[1] == "dev":
            return JSONResponse(status_code=403, content={"error": "Cannot send reset link to a dev account."})
        with db_engine.begin() as conn:
            existing = conn.execute(text("""
                SELECT id FROM password_reset_requests 
                WHERE user_id=:id AND status IN ('requested', 'issued')
            """), {"id": user_id}).fetchone()
            
        if existing:
            return JSONResponse(status_code=400, content={"error": "An active reset link already exists. Revoke it in 'Password Resets' first."})
            
        sent, reset_url = await issue_expired_password_reset(user_id, row[0])
        if not sent:
            return JSONResponse(status_code=400, content={"error": "A reset link was sent recently. Please wait a minute."})
            
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO password_reset_requests (user_id, status, handled_by)
                VALUES (:user_id, 'issued', :admin_id)
            """), {"user_id": user_id, "admin_id": current_user["id"]})
            
        return {"message": f"Password reset link generated for {row[0]}.", "url": reset_url}
    except Exception as e:
        cprint("error", f"Reset error: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal Server Error. Please ensure the database schema is updated."})


@router.delete("/api/dev/users/{user_id}")
async def dev_delete_user(user_id: int, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    if user_id == current_user["id"]:
        return JSONResponse(status_code=400, content={"error": "You cannot delete your own account from user management."})
    with db_engine.connect() as conn:
        target = conn.execute(text("SELECT role FROM users WHERE id=:id"), {"id": user_id}).fetchone()
        if not target:
            return JSONResponse(status_code=404, content={"error": "User not found."})
        if not can_manage_user(current_user["role"], target[0]):
            return JSONResponse(status_code=403, content={"error": "You are not allowed to delete this account."})
        conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": user_id})
        conn.commit()
    return {"message": f"User id={user_id} deleted."}
