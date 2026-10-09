import hashlib
import hmac
import secrets
import smtplib
import ssl
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import text

from config import AUTH_CONFIG, EMAIL_CONFIG, cprint
from database import db_engine


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def otp_digest(challenge_key: str, otp: str) -> str:
    return hmac.new(
        AUTH_CONFIG["jwt_secret"].encode("utf-8"),
        f"{challenge_key}:{otp}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def send_otp_email(recipient: str, otp: str, purpose: str) -> None:
    if not EMAIL_CONFIG["smtp_host"] or not EMAIL_CONFIG["from_email"]:
        raise ValueError("SMTP host and sender email must be configured.")
    message = EmailMessage()
    message["Subject"] = "Your RAMIEL verification code"
    message["From"] = EMAIL_CONFIG["from_email"]
    message["To"] = recipient
    action = "sign in" if purpose == "login" else "create your account"
    message.set_content(
        f"Your RAMIEL verification code to {action} is {otp}. "
        "It expires in 10 minutes. If you did not request this code, ignore this email."
    )

    if EMAIL_CONFIG["use_ssl"]:
        with smtplib.SMTP_SSL(
            EMAIL_CONFIG["smtp_host"], EMAIL_CONFIG["smtp_port"],
            timeout=10, context=ssl.create_default_context(),
        ) as server:
            if EMAIL_CONFIG["smtp_user"]:
                server.login(EMAIL_CONFIG["smtp_user"], EMAIL_CONFIG["smtp_password"])
            server.send_message(message)
        return

    with smtplib.SMTP(EMAIL_CONFIG["smtp_host"], EMAIL_CONFIG["smtp_port"], timeout=10) as server:
        if EMAIL_CONFIG["use_starttls"]:
            server.starttls(context=ssl.create_default_context())
        if EMAIL_CONFIG["smtp_user"]:
            server.login(EMAIL_CONFIG["smtp_user"], EMAIL_CONFIG["smtp_password"])
        server.send_message(message)


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Reset your RAMIEL password"
    message["From"] = EMAIL_CONFIG["from_email"]
    message["To"] = recipient
    message.set_content(
        "Your RAMIEL password has expired. Use the link below to set a new password. "
        "The link expires in 30 minutes and the new password must be different from your old one.\n\n"
        f"{reset_url}"
    )
    if EMAIL_CONFIG["use_ssl"]:
        with smtplib.SMTP_SSL(
            EMAIL_CONFIG["smtp_host"], EMAIL_CONFIG["smtp_port"], timeout=10,
            context=ssl.create_default_context(),
        ) as server:
            if EMAIL_CONFIG["smtp_user"]:
                server.login(EMAIL_CONFIG["smtp_user"], EMAIL_CONFIG["smtp_password"])
            server.send_message(message)
        return
    with smtplib.SMTP(EMAIL_CONFIG["smtp_host"], EMAIL_CONFIG["smtp_port"], timeout=10) as server:
        if EMAIL_CONFIG["use_starttls"]:
            server.starttls(context=ssl.create_default_context())
        if EMAIL_CONFIG["smtp_user"]:
            server.login(EMAIL_CONFIG["smtp_user"], EMAIL_CONFIG["smtp_password"])
        server.send_message(message)


async def issue_expired_password_reset(user_id: int, email: str) -> tuple[bool, str]:
    raw_token = secrets.token_urlsafe(32)
    t_hash = token_digest(raw_token)
    with db_engine.begin() as conn:
        recent = conn.execute(text("""
            SELECT id FROM password_reset_tokens
            WHERE user_id=:user_id AND created_at > DATE_SUB(NOW(), INTERVAL 1 MINUTE)
              AND used_at IS NULL
            LIMIT 1
        """), {"user_id": user_id}).fetchone()
        if recent:
            return False, ""
        conn.execute(text("""
            UPDATE password_reset_tokens SET used_at=NOW()
            WHERE user_id=:user_id AND used_at IS NULL
        """), {"user_id": user_id})
        conn.execute(text("""
            INSERT INTO password_reset_tokens (user_id, token)
            VALUES (:user_id, :token)
        """), {"user_id": user_id, "token": t_hash})

    reset_url = (
        f"{EMAIL_CONFIG['app_base_url'].rstrip('/')}/account-action"
        f"?mode=reset&token={raw_token}"
    )
    return True, reset_url


async def issue_auth_otp(purpose: str, subject_id: int, email: str):
    with db_engine.begin() as conn:
        existing = conn.execute(text("""
            SELECT challenge_key, GREATEST(0, TIMESTAMPDIFF(SECOND, NOW(), resend_after))
            FROM auth_otp_challenges
            WHERE purpose=:purpose AND subject_id=:subject_id
            FOR UPDATE
        """), {"purpose": purpose, "subject_id": subject_id}).fetchone()
        if existing and existing[1] > 0:
            return {"challenge_id": existing[0], "cooldown_seconds": existing[1], "sent": False}

        challenge_key = existing[0] if existing else secrets.token_urlsafe(32)
        otp = f"{secrets.randbelow(1_000_000):06d}"
        params = {
            "purpose": purpose,
            "subject_id": subject_id,
            "challenge_key": challenge_key,
            "email": email,
            "otp_hash": otp_digest(challenge_key, otp),
        }
        if existing:
            conn.execute(text("""
                UPDATE auth_otp_challenges
                SET email=:email, otp_hash=:otp_hash, attempts=0,
                    expires_at=DATE_ADD(NOW(), INTERVAL 10 MINUTE),
                    resend_after=DATE_ADD(NOW(), INTERVAL 60 SECOND),
                    verified_at=NULL, created_at=NOW()
                WHERE purpose=:purpose AND subject_id=:subject_id
            """), params)
        else:
            conn.execute(text("""
                INSERT INTO auth_otp_challenges
                    (purpose, subject_id, challenge_key, email, otp_hash, expires_at, resend_after)
                VALUES (:purpose, :subject_id, :challenge_key, :email, :otp_hash,
                    DATE_ADD(NOW(), INTERVAL 10 MINUTE), DATE_ADD(NOW(), INTERVAL 60 SECOND))
            """), params)

    try:
        # await asyncio.to_thread(send_otp_email, email, otp, purpose)
        pass # Simulated email sending for local dev
    except Exception as error:
        with db_engine.begin() as conn:
            conn.execute(text("""
                UPDATE auth_otp_challenges SET resend_after=NOW()
                WHERE purpose=:purpose AND subject_id=:subject_id
            """), {"purpose": purpose, "subject_id": subject_id})
        cprint("email", f"OTP delivery failed: {error}")
        return {"challenge_id": challenge_key, "cooldown_seconds": 60, "sent": False, "otp_plain": otp}
    return {"challenge_id": challenge_key, "cooldown_seconds": 60, "sent": True, "otp_plain": otp}
