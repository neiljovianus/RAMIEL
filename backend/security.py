import re
import json
import datetime
import calendar
from typing import Optional

import bcrypt
from jose import jwt

from config import AUTH_CONFIG

USERNAME_REGEX = re.compile(r'^[a-z_]{3,30}$')
PASSWORD_REGEX = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$')


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def add_months(value: datetime.datetime, months: int) -> datetime.datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def add_interval(value: datetime.datetime, interval: int, unit: str) -> datetime.datetime:
    if unit == "day":
        return value + datetime.timedelta(days=interval)
    if unit == "week":
        return value + datetime.timedelta(weeks=interval)
    if unit == "month":
        return add_months(value, interval)
    if unit == "year":
        return add_months(value, interval * 12)
    return None


def valid_interval(interval: Optional[int], unit: Optional[str]) -> bool:
    limits = {"day": 3650, "week": 520, "month": 120, "year": 100}
    return bool(interval and unit in limits and 1 <= interval <= limits[unit])


def calculate_password_expiry(
    policy_type: str,
    repeat: str,
    interval: Optional[int],
    unit: Optional[str],
    repeat_on: Optional[int],
    repeat_month: Optional[int],
    policy_date: Optional[datetime.datetime],
    anchor: Optional[datetime.date],
    schedule: Optional[list],
    start: datetime.datetime,
):
    if policy_type == "none":
        return None
    if policy_type == "duration":
        return add_interval(start, interval or 0, unit or "month")
    if repeat != "repeat":
        return policy_date
    if not valid_interval(interval, unit):
        return None

    anchor = anchor or start.date()
    schedule = schedule or []
    if unit == "day":
        elapsed_days = (start.date() - anchor).days
        periods = max(0, elapsed_days // interval + 1)
        result = anchor + datetime.timedelta(days=periods * interval)
    elif unit == "week":
        weekdays = sorted({int(value) for value in schedule if isinstance(value, int) and 1 <= value <= 7})
        if not weekdays:
            return None
        week_anchor = anchor - datetime.timedelta(days=anchor.weekday())
        elapsed_weeks = max(0, (start.date() - week_anchor).days // 7)
        period = (elapsed_weeks // interval) * interval
        for _ in range(520):
            candidates = [
                week_anchor + datetime.timedelta(weeks=period, days=weekday - 1)
                for weekday in weekdays
            ]
            future = [candidate for candidate in candidates if datetime.datetime.combine(candidate, datetime.time.max) > start]
            if future:
                result = min(future)
                break
            period += interval
    elif unit == "month":
        month_days = sorted({int(value) for value in schedule if isinstance(value, int) and 1 <= value <= 31})
        if not month_days:
            return None
        anchor_start = datetime.datetime.combine(anchor.replace(day=1), datetime.time())
        month_offset = max(0, (start.year - anchor.year) * 12 + start.month - anchor.month)
        month_offset = (month_offset // interval) * interval
        for _ in range(2400):
            candidate = add_months(anchor_start, month_offset)
            last_day = calendar.monthrange(candidate.year, candidate.month)[1]
            candidates = sorted({candidate.replace(day=min(day, last_day)).date() for day in month_days})
            future = [day for day in candidates if datetime.datetime.combine(day, datetime.time.max) > start]
            if future:
                result = min(future)
                break
            month_offset += interval
    else:
        annual_dates = [
            (int(value["month"]), int(value["day"]))
            for value in schedule
            if isinstance(value, dict)
            and str(value.get("month", "")).isdigit()
            and str(value.get("day", "")).isdigit()
            and 1 <= int(value["month"]) <= 12
            and 1 <= int(value["day"]) <= 31
        ]
        if not annual_dates:
            return None
        year_offset = max(0, start.year - anchor.year)
        year_offset = (year_offset // interval) * interval
        for _ in range(500):
            year = anchor.year + year_offset
            candidates = sorted({
                datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))
                for month, day in annual_dates
            })
            future = [day for day in candidates if datetime.datetime.combine(day, datetime.time.max) > start]
            if future:
                result = min(future)
                break
            year_offset += interval
    return datetime.datetime.combine(result, datetime.time(23, 59, 59))


def decode_password_schedule(value: Optional[str]) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def create_token(user_id: int, username: str, role: str) -> str:
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=AUTH_CONFIG["jwt_expire_hours"])
    return jwt.encode(
        {"sub": str(user_id), "username": username, "role": role, "exp": expire},
        AUTH_CONFIG["jwt_secret"], algorithm="HS256",
    )
