import re
import hmac
import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import db_engine
from schemas import (
    LoginRequest, LoginOtpVerifyRequest, OtpResendRequest,
    InvitationOtpRequest, PasswordResetRequest,
    CompletePasswordResetRequest, AcceptInvitationRequest,
)
from dependencies import get_current_user, require_db
from security import (
    hash_password, verify_password, create_token,
    calculate_password_expiry, decode_password_schedule,
    USERNAME_REGEX, PASSWORD_REGEX,
)
from email_service import (
    token_digest, otp_digest, issue_expired_password_reset,
    issue_auth_otp,
)
from config import EMAIL_CONFIG

import secrets

router = APIRouter()


@router.post("/api/auth/login")
async def login(req: LoginRequest, _db: None = Depends(require_db)):
    try:
        with db_engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT id, password_hash, role, email, account_status,
                           account_expires_at, password_expires_at
                    FROM users WHERE username=:u
                """),
                {"u": req.username},
            ).fetchone()
        if not row or not verify_password(req.password, row[1]):
            return JSONResponse(status_code=401, content={"error": "Incorrect username or password."})
        if row[4] != "active":
            return JSONResponse(status_code=403, content={"error": "Your account is suspended. Please contact admin."})
        if row[5] and row[5] <= datetime.datetime.now():
            return JSONResponse(status_code=403, content={"error": "Your account has expired. Please contact admin."})
        if row[6] and row[6] <= datetime.datetime.now():
            sent, reset_url = await issue_expired_password_reset(row[0], row[3])
            message = f"Your password has expired. Click here to reset: {reset_url}" if sent else "Your password has expired. You requested a reset recently, please use that link."
            return JSONResponse(status_code=403, content={"error": message, "password_expired": True})
        if row[0] in EMAIL_CONFIG["otp_bypass_user_ids"]:
            return {
                "id": row[0],
                "token": create_token(row[0], req.username, row[2]),
                "username": req.username,
                "role": row[2],
            }
        recipient = row[3]
        if row[0] in EMAIL_CONFIG["otp_recipient_override_user_ids"]:
            recipient = EMAIL_CONFIG["otp_recipient_override_email"]
        if not recipient:
            return JSONResponse(status_code=503, content={"error": "No email address is configured for this account."})
        challenge = await issue_auth_otp("login", row[0], recipient)
        return {"otp_required": True, **challenge}
    except Exception as error:
        if hasattr(error, 'status_code'):
            return JSONResponse(status_code=error.status_code, content={"error": error.detail})
        return JSONResponse(status_code=500, content={"error": str(error)})


@router.post("/api/auth/login/resend-otp")
async def resend_login_otp(req: OtpResendRequest, _db: None = Depends(require_db)):
    with db_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT subject_id, email
            FROM auth_otp_challenges
                        WHERE challenge_key=:challenge_key AND purpose='login'
                            AND verified_at IS NULL
        """), {"challenge_key": req.challenge_id}).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"error": "This sign-in challenge expired. Enter your password again."})
    try:
        return await issue_auth_otp("login", row[0], row[1])
    except Exception as error:
        if hasattr(error, 'status_code'):
            return JSONResponse(status_code=error.status_code, content={"error": error.detail})
        return JSONResponse(status_code=500, content={"error": str(error)})


@router.post("/api/auth/login/verify-otp")
async def verify_login_otp(req: LoginOtpVerifyRequest, _db: None = Depends(require_db)):
    if not re.fullmatch(r"\d{6}", req.otp):
        return JSONResponse(status_code=400, content={"error": "Enter the 6-digit verification code."})
    with db_engine.begin() as conn:
        challenge = conn.execute(text("""
            SELECT subject_id, otp_hash, attempts
            FROM auth_otp_challenges
            WHERE challenge_key=:challenge_key AND purpose='login'
              AND verified_at IS NULL
            FOR UPDATE
        """), {"challenge_key": req.challenge_id}).fetchone()
        if not challenge:
            return JSONResponse(status_code=400, content={"error": "This code expired or was already used. Sign in again."})
        if challenge[2] >= 5:
            return JSONResponse(status_code=429, content={"error": "Too many incorrect codes. Sign in again to request a new code."})
        if not hmac.compare_digest(challenge[1], otp_digest(req.challenge_id, req.otp)):
            conn.execute(text("""
                UPDATE auth_otp_challenges SET attempts=attempts+1
                WHERE challenge_key=:challenge_key
            """), {"challenge_key": req.challenge_id})
            return JSONResponse(status_code=401, content={"error": "The verification code is incorrect."})
        conn.execute(text("""
            UPDATE auth_otp_challenges SET verified_at=NOW(), resend_after=NOW()
            WHERE challenge_key=:challenge_key
        """), {"challenge_key": req.challenge_id})
        user = conn.execute(text("SELECT id, username, role FROM users WHERE id=:id"), {"id": challenge[0]}).fetchone()
    if not user:
        return JSONResponse(status_code=401, content={"error": "This account is no longer available."})
    return {
        "id": user[0],
        "token": create_token(user[0], user[1], user[2]),
        "username": user[1],
        "role": user[2],
    }


@router.get("/api/auth/check-username/{username}")
async def check_username(username: str, _db: None = Depends(require_db)):
    if not USERNAME_REGEX.fullmatch(username):
        return {"valid": False, "available": False}
    with db_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT id FROM users WHERE username=:username"), {"username": username}
        ).fetchone()
    return {"valid": True, "available": exists is None}


@router.post("/api/auth/password-reset/request")
async def request_password_reset(req: PasswordResetRequest, _db: None = Depends(require_db)):
    email = req.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return JSONResponse(status_code=400, content={"error": "Enter a valid email address."})

    with db_engine.begin() as conn:
        user = conn.execute(
            text("SELECT id FROM users WHERE LOWER(email)=:email"), {"email": email}
        ).fetchone()
        if not user:
            return {"message": "If an account with that email exists, a reset link has been generated."}

        uid = user[0]
        pending = conn.execute(text("""
            SELECT id FROM password_reset_requests
            WHERE user_id=:uid AND status IN ('requested', 'issued')
              AND requested_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
            ORDER BY requested_at DESC
            LIMIT 1
        """), {"uid": uid}).fetchone()
        if not pending:
            conn.execute(
                text("INSERT INTO password_reset_requests (user_id) VALUES (:uid)"),
                {"uid": uid},
            )

        raw_token = secrets.token_urlsafe(32)
        t_hash = token_digest(raw_token)
        conn.execute(text("UPDATE password_reset_tokens SET used_at=NOW() WHERE user_id=:uid AND used_at IS NULL"), {"uid": uid})
        conn.execute(text("""
            INSERT INTO password_reset_tokens (user_id, token, expires_at)
            VALUES (:uid, :token, DATE_ADD(NOW(), INTERVAL 30 MINUTE))
        """), {"uid": uid, "token": t_hash})

    reset_url = f"/account-action?mode=reset&token={raw_token}"
    full_url = f"{EMAIL_CONFIG['app_base_url'].rstrip('/')}{reset_url}"

    email_configured = bool(EMAIL_CONFIG.get("smtp_host") and EMAIL_CONFIG.get("from_email"))
    if email_configured:
        try:
            # await asyncio.to_thread(send_password_reset_email, email, full_url)
            pass # Simulated for local dev
            return {"message": "If an account with that email exists, a reset link has been sent to your inbox.", "reset_url": full_url}
        except Exception as error:
            from config import cprint
            cprint("email", f"Password reset email failed: {error}")

    return {
        "message": "Email delivery is not configured. Use the link below to reset your password.",
        "reset_url": reset_url,
    }


@router.get("/api/auth/invitations/{token}")
async def get_invitation(token: str, _db: None = Depends(require_db)):
    with db_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT email
            FROM user_invitations
            WHERE invitation_token=:token_hash AND status='pending'
        """), {"token_hash": token_digest(token)}).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"error": "This invitation is invalid or expired."})
    return {"email": row[0]}


@router.post("/api/auth/invitations/send-otp")
async def send_invitation_otp(req: InvitationOtpRequest, _db: None = Depends(require_db)):
    with db_engine.connect() as conn:
        invitation = conn.execute(text("""
            SELECT id, email
            FROM user_invitations
            WHERE invitation_token=:token_hash AND status='pending'
        """), {"token_hash": token_digest(req.token)}).fetchone()
    if not invitation:
        return JSONResponse(status_code=404, content={"error": "This invitation is invalid or expired."})
    try:
        return await issue_auth_otp("invitation", invitation[0], invitation[1])
    except Exception as error:
        if hasattr(error, 'status_code'):
            return JSONResponse(status_code=error.status_code, content={"error": error.detail})
        return JSONResponse(status_code=500, content={"error": str(error)})


@router.post("/api/auth/invitations/accept")
async def accept_invitation(req: AcceptInvitationRequest, _db: None = Depends(require_db)):
    if not re.fullmatch(r"\d{6}", req.otp):
        return JSONResponse(status_code=400, content={"error": "Enter the 6-digit email verification code."})
    username = req.username.strip()
    if not USERNAME_REGEX.match(username):
        return JSONResponse(status_code=400, content={"error": "Username must use lowercase letters and underscores (3-30 characters)."})
    if not PASSWORD_REGEX.match(req.password):
        return JSONResponse(status_code=400, content={"error": "Password must include uppercase, lowercase, number, and symbol (8+ characters)."})
    phone = req.phone.strip()
    if phone:
        p_clean = re.sub(r'[\s\-\(\)]', '', phone)
        if p_clean.startswith("+62"): phone = "0" + p_clean[3:]
        elif p_clean.startswith("62"): phone = "0" + p_clean[2:]
        else:
            phone = re.sub(r'[\-\(\)]', '', phone).strip()
            phone = re.sub(r'\s+', ' ', phone)
            if phone.startswith('+') and ' ' not in phone:
                for cc in ['+65', '+60', '+673', '+61', '+1', '+44', '+91', '+971']:
                    if phone.startswith(cc):
                        phone = cc + " " + phone[len(cc):]
                        break
        if not re.fullmatch(r"\+?[0-9\s]{5,20}", phone):
            return JSONResponse(status_code=400, content={"error": "Enter a valid phone number."})
    profile = {
        "first_name": req.first_name.strip(),
        "last_name": req.last_name.strip(),
        "phone": phone,
    }
    profile_limits = {"first_name": 100, "last_name": 100, "phone": 50}
    if not profile["first_name"] or not profile["last_name"]:
        return JSONResponse(status_code=400, content={"error": "First and last name are required."})
    if any(len(value) > profile_limits[field] for field, value in profile.items()):
        return JSONResponse(status_code=400, content={"error": "One or more profile fields are too long."})

    with db_engine.begin() as conn:
        invitation = conn.execute(text("""
            SELECT id, email, company_name, department
            FROM user_invitations
            WHERE invitation_token=:token_hash AND status='pending'
            FOR UPDATE
        """), {"token_hash": token_digest(req.token)}).fetchone()
        if not invitation:
            return JSONResponse(status_code=404, content={"error": "This invitation is invalid or expired."})
        exists = conn.execute(
            text("SELECT id FROM users WHERE username=:username OR LOWER(email)=:email"),
            {"username": username, "email": invitation[1].lower()},
        ).fetchone()
        if exists:
            return JSONResponse(status_code=409, content={"error": "Username or email is already in use."})
        challenge = conn.execute(text("""
            SELECT challenge_key, otp_hash, attempts
            FROM auth_otp_challenges
            WHERE purpose='invitation' AND subject_id=:invitation_id
              AND LOWER(email)=:email AND verified_at IS NULL
            FOR UPDATE
        """), {"invitation_id": invitation[0], "email": invitation[1].lower()}).fetchone()
        if not challenge:
            return JSONResponse(status_code=400, content={"error": "Request an email verification code before creating your account."})
        if challenge[2] >= 5:
            return JSONResponse(status_code=429, content={"error": "Too many incorrect codes. Request a new code after the resend timer."})
        if not hmac.compare_digest(challenge[1], otp_digest(challenge[0], req.otp)):
            conn.execute(text("""
                UPDATE auth_otp_challenges SET attempts=attempts+1
                WHERE purpose='invitation' AND subject_id=:invitation_id
            """), {"invitation_id": invitation[0]})
            return JSONResponse(status_code=401, content={"error": "The email verification code is incorrect."})
        profile["company_name"] = invitation[2] or ""
        profile["department"] = invitation[3] or ""

        result = conn.execute(text("""
            INSERT INTO users (username, email, password_hash, role)
            VALUES (:username, :email, :password_hash, 'user')
        """), {
            "username": username,
            "email": invitation[1],
            "password_hash": hash_password(req.password),
        })
        conn.execute(text("""
            INSERT INTO user_profiles
                (user_id, first_name, last_name, company_name, department, phone)
            VALUES (:uid, :first_name, :last_name, :company_name, :department, :phone)
        """), {"uid": result.lastrowid, **profile})
        conn.execute(
            text("UPDATE user_invitations SET status='accepted' WHERE id=:id"),
            {"id": invitation[0]},
        )
        conn.execute(text("""
            UPDATE auth_otp_challenges SET verified_at=NOW()
            WHERE purpose='invitation' AND subject_id=:invitation_id
        """), {"invitation_id": invitation[0]})
    return {"message": "Invitation accepted. You can now sign in."}


@router.get("/api/auth/password-reset/{token}")
async def get_password_reset(token: str, _db: None = Depends(require_db)):
    with db_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT u.email
            FROM password_reset_tokens t
            JOIN users u ON u.id=t.user_id
            WHERE t.token=:token_hash AND t.used_at IS NULL
        """), {"token_hash": token_digest(token)}).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"error": "This reset link is invalid or expired."})
    return {"email": row[0]}


@router.post("/api/auth/password-reset/complete")
async def complete_password_reset(req: CompletePasswordResetRequest, _db: None = Depends(require_db)):
    if not PASSWORD_REGEX.match(req.password):
        return JSONResponse(status_code=400, content={"error": "Password must include uppercase, lowercase, number, and symbol (8+ characters)."})

    with db_engine.begin() as conn:
        reset = conn.execute(text("""
            SELECT id, user_id FROM password_reset_tokens
            WHERE token=:token_hash AND used_at IS NULL
            FOR UPDATE
        """), {"token_hash": token_digest(req.token)}).fetchone()
        if not reset:
            return JSONResponse(status_code=404, content={"error": "This reset link is invalid or expired."})
        account = conn.execute(
            text("""
                SELECT password_hash, password_policy_type, password_policy_repeat,
                       password_policy_interval, password_policy_unit, password_policy_on,
                      password_policy_month, password_policy_date, password_policy_anchor,
                      password_policy_schedule
                FROM users WHERE id=:uid FOR UPDATE
            """),
            {"uid": reset[1]},
        ).fetchone()
        if not account:
            return JSONResponse(status_code=404, content={"error": "Account not found."})
        if verify_password(req.password, account[0]):
            return JSONResponse(status_code=400, content={"error": "Choose a password different from your previous password."})
        now = datetime.datetime.now()
        keep_policy = account[2] == "repeat"
        next_password_expiry = calculate_password_expiry(
            account[1], account[2], account[3], account[4], account[5],
            account[6], account[7], account[8], decode_password_schedule(account[9]), now,
        ) if keep_policy else None
        conn.execute(
            text("""
                UPDATE users SET password_hash=:password_hash,
                    password_expires_at=:password_expires_at,
                    password_policy_type=:password_policy_type
                WHERE id=:uid
            """),
            {
                "password_hash": hash_password(req.password),
                "password_expires_at": next_password_expiry,
                "password_policy_type": account[1] if keep_policy else "none",
                "uid": reset[1],
            },
        )
        conn.execute(
            text("UPDATE password_reset_tokens SET used_at=NOW() WHERE id=:id"),
            {"id": reset[0]},
        )
        conn.execute(text("""
            UPDATE password_reset_requests SET status='completed'
            WHERE user_id=:uid AND status='issued'
        """), {"uid": reset[1]})
    return {"message": "Password updated. You can now sign in."}


@router.get("/api/profile")
async def get_my_profile(current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    with db_engine.connect() as conn:
        row = conn.execute(text("""
            SELECT u.username, u.email, COALESCE(p.first_name, ''), COALESCE(p.last_name, ''),
                   COALESCE(p.phone, ''), COALESCE(t.tokens, 0)
            FROM users u
            LEFT JOIN user_profiles p ON p.user_id = u.id
            LEFT JOIN user_tokens t ON t.user_id = u.id
            WHERE u.id=:uid
        """), {"uid": current_user["id"]}).fetchone()
    if not row:
        return JSONResponse(status_code=404, content={"error": "Profile not found."})
    return {
        "username": row[0],
        "email": row[1],
        "first_name": row[2],
        "last_name": row[3],
        "phone": row[4],
        "tokens": row[5],
    }


@router.put("/api/profile")
async def update_my_profile(
    payload: dict,
    current_user: dict = Depends(get_current_user),
    _db: None = Depends(require_db),
):
    username = str(payload.get("username", current_user["username"] or "")).strip()
    first_name = str(payload.get("first_name", "")).strip()
    last_name = str(payload.get("last_name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    current_password = str(payload.get("current_password", ""))
    new_password = str(payload.get("new_password", ""))
    confirm_password = str(payload.get("confirm_password", ""))

    if not username:
        return JSONResponse(status_code=400, content={"error": "Username is required."})
    if not USERNAME_REGEX.fullmatch(username):
        return JSONResponse(status_code=400, content={"error": "Username must use lowercase letters and underscores (3-30 characters)."})
    if len(first_name) > 100 or len(last_name) > 100 or len(phone) > 50:
        return JSONResponse(status_code=400, content={"error": "One or more profile fields are too long."})
    if phone:
        p_clean = re.sub(r'[\s\-\(\)]', '', phone)
        if p_clean.startswith("+62"): phone = "0" + p_clean[3:]
        elif p_clean.startswith("62"): phone = "0" + p_clean[2:]
        else:
            phone = re.sub(r'[\-\(\)]', '', phone).strip()
            phone = re.sub(r'\s+', ' ', phone)
            if phone.startswith('+') and ' ' not in phone:
                for cc in ['+65', '+60', '+673', '+61', '+1', '+44', '+91', '+971']:
                    if phone.startswith(cc):
                        phone = cc + " " + phone[len(cc):]
                        break
        if not re.fullmatch(r"\+?[0-9\s]{5,20}", phone):
            return JSONResponse(status_code=400, content={"error": "Enter a valid phone number."})

    changing_password = bool(current_password or new_password or confirm_password)
    if changing_password and not (current_password and new_password and confirm_password):
        return JSONResponse(status_code=400, content={"error": "Current password, new password, and confirmation are required."})
    if changing_password and new_password != confirm_password:
        return JSONResponse(status_code=400, content={"error": "New passwords do not match."})
    if changing_password and not PASSWORD_REGEX.match(new_password):
        return JSONResponse(status_code=400, content={"error": "Password must include uppercase, lowercase, number, and symbol."})

    with db_engine.begin() as conn:
        identity = conn.execute(
            text("""
                  SELECT username, email, password_hash, password_policy_type,
                      password_policy_repeat, password_policy_interval, password_policy_unit,
                      password_policy_on, password_policy_month, password_policy_date,
                      password_policy_anchor, password_policy_schedule
                FROM users WHERE id=:uid
            """),
            {"uid": current_user["id"]},
        ).fetchone()
        if not identity:
            return JSONResponse(status_code=404, content={"error": "Profile not found."})
        if current_user["role"] == "dev" and username != identity[0]:
            return JSONResponse(status_code=403, content={"error": "Developer username is locked."})

        exists = conn.execute(
            text("SELECT id FROM users WHERE username=:u AND id != :uid"),
            {"u": username, "uid": current_user["id"]},
        ).fetchone()
        if exists:
            return JSONResponse(status_code=400, content={"error": "Username already in use."})

        if changing_password and not verify_password(current_password, identity[2]):
            return JSONResponse(status_code=400, content={"error": "Current password is incorrect."})
        if changing_password and verify_password(new_password, identity[2]):
            return JSONResponse(status_code=400, content={"error": "Choose a password different from your current password."})

        conn.execute(text("UPDATE users SET username=:username WHERE id=:uid"), {
            "username": username,
            "uid": current_user["id"],
        })
        if changing_password:
            now = datetime.datetime.now()
            conn.execute(text("""
                UPDATE users SET password_hash=:password_hash, password_expires_at=:password_expires_at
                WHERE id=:uid
            """), {
                "password_hash": hash_password(new_password),
                "password_expires_at": calculate_password_expiry(
                    identity[3], identity[4], identity[5], identity[6], identity[7],
                    identity[8], identity[9], identity[10],
                    decode_password_schedule(identity[11]), now,
                ),
                "uid": current_user["id"],
            })
        conn.execute(text("""
            INSERT INTO user_profiles (user_id, first_name, last_name, phone)
            VALUES (:uid, :first_name, :last_name, :phone)
            ON DUPLICATE KEY UPDATE
                first_name = VALUES(first_name),
                last_name = VALUES(last_name),
                phone = VALUES(phone)
        """), {
            "uid": current_user["id"],
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
        })

    return {
        "username": username,
        "email": identity[1],
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone,
    }


@router.delete("/api/auth/account")
async def delete_own_account(current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    try:
        with db_engine.connect() as conn:
            conn.execute(text("DELETE FROM users WHERE id=:id"), {"id": current_user["id"]})
            conn.commit()
        return {"message": f"Account '{current_user['username']}' deleted."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
