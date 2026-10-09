from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    role: Optional[str] = "guest"
    session_id: Optional[int] = None
    parent_id: Optional[int] = None
    edit_message_id: Optional[int] = None
    is_regenerate: Optional[bool] = False
    lock_edit_id: Optional[int] = None
    staged_user: Optional[str] = None
    staged_ai: Optional[str] = None
    files: Optional[list[dict]] = []


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginOtpVerifyRequest(BaseModel):
    challenge_id: str
    otp: str


class OtpResendRequest(BaseModel):
    challenge_id: str


class InvitationOtpRequest(BaseModel):
    token: str


class PasswordResetRequest(BaseModel):
    email: str


class CompletePasswordResetRequest(BaseModel):
    token: str
    password: str


class AcceptInvitationRequest(BaseModel):
    token: str
    otp: str
    username: str
    password: str
    first_name: str = ""
    last_name: str = ""
    phone: str = ""


class RenameSessionRequest(BaseModel):
    title: str


class DevCreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: str = "user"


class DevUpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    tokens: Optional[int] = None
    password: Optional[str] = None
    role: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    account_status: Optional[str] = None
    account_expiry_mode: Optional[str] = None
    account_expiry_duration: Optional[int] = None
    account_expiry_unit: Optional[str] = None
    account_expiry_date: Optional[str] = None
    password_policy_type: Optional[str] = None
    password_policy_repeat: Optional[str] = None
    password_policy_interval: Optional[int] = None
    password_policy_unit: Optional[str] = None
    password_policy_on: Optional[int] = None
    password_policy_month: Optional[int] = None
    password_policy_date: Optional[str] = None
    password_policy_schedule: Optional[list] = None


class DevInviteRequest(BaseModel):
    email: str
    company_name: str = ""
    department: str = ""
