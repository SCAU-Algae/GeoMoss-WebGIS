"""
Email registration with SMTP sending + email-verifier pre-check + CAPTCHA.
"""

import asyncio
import io
import logging
import os
import random
import re
import secrets
import smtplib
import string
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.auth import _normalize_username, _validate_register_payload, _create_user_sync, init_auth_storage
from api.database import get_auth_db_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/email", tags=["email-auth"])

# SMTP config — defaults to QQ Mail. Set env vars to override.
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")       # QQ邮箱地址
SMTP_PASS = os.getenv("SMTP_PASS", "")       # QQ邮箱授权码（非登录密码）
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@geomoss.top")

# email-verifier API (free, no auth required)
EMAIL_VERIFIER_URL = "https://rapid-email-verifier.fly.dev/api/validate"

CODE_EXPIRE_MINUTES = 10

_email_codes: Dict[str, dict] = {}
_captcha_store: Dict[str, str] = {}

CAPTCHA_W = 160
CAPTCHA_H = 56


def _gen_captcha() -> str:
    chars = string.ascii_uppercase + string.digits
    chars = chars.translate(str.maketrans('', '', '0O1IL'))
    return ''.join(random.choice(chars) for _ in range(4))


def _captcha_image(text: str) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGB', (CAPTCHA_W, CAPTCHA_H), '#0d1520')
    draw = ImageDraw.Draw(img)
    for _ in range(6):
        x1, y1 = random.randint(0, CAPTCHA_W), random.randint(0, CAPTCHA_H)
        x2, y2 = random.randint(0, CAPTCHA_W), random.randint(0, CAPTCHA_H)
        draw.line([(x1, y1), (x2, y2)], fill='#1a3040', width=1)
    for _ in range(50):
        draw.point((random.randint(0, CAPTCHA_W), random.randint(0, CAPTCHA_H)), fill='#47d7c6')
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 28)
    except Exception:
        font = ImageFont.load_default()
    for i, ch in enumerate(text):
        x = 18 + i * 34 + random.randint(-3, 3)
        y = random.randint(6, 14)
        draw.text((x, y), ch, fill=(71, 215, 198), font=font)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _init_email_tables():
    try:
        with get_auth_db_connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS email_verified ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  email TEXT NOT NULL UNIQUE,"
                "  username TEXT NOT NULL,"
                "  verified_at TEXT NOT NULL DEFAULT (datetime('now'))"
                ")"
            )
            db.commit()
    except Exception:
        pass


def _verify_email_address(email: str):
    """Pre-validate email using free email-verifier API. Returns (ok, message)."""
    try:
        import httpx
        resp = httpx.get(f"{EMAIL_VERIFIER_URL}?email={email}", timeout=8.0)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "VALID":
                return True, ""
            return False, data.get("message", "邮箱地址无效")
    except Exception as e:
        logger.warning(f"email-verifier unavailable: {e}")
    return True, ""  # verifier down → allow through


def _send_email(email: str, code: str, username: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        logger.error("SMTP not configured — set SMTP_USER and SMTP_PASS env vars")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_FROM
        msg["To"] = email
        msg["Subject"] = f"[GeoMoss] 邮箱验证码: {code}"
        html = f"""<div style="max-width:480px;margin:0 auto;padding:32px;font-family:system-ui,sans-serif;background:#0d1520;color:#e8edf2;border-radius:10px;border:1px solid rgba(71,215,198,0.2)">
<h2 style="color:#47d7c6;margin-top:0">GeoMoss 邮箱验证</h2>
<p>你好 <strong>{username}</strong>，验证码：</p>
<div style="font-family:monospace;font-size:32px;font-weight:700;letter-spacing:8px;text-align:center;padding:20px;margin:16px 0;background:rgba(71,215,198,0.1);border-radius:6px;color:#47d7c6">{code}</div>
<p style="color:#8fa4b8;font-size:13px">{CODE_EXPIRE_MINUTES} 分钟内有效。如非本人操作请忽略。</p>
</div>"""
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, email, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        return False


def _gen_code() -> str:
    return ''.join(str(secrets.randbelow(10)) for _ in range(6))


# ── Pydantic models ──

class EmailRegisterRequest(BaseModel):
    """Step 1: only email + CAPTCHA needed to send code."""
    email: str = Field(..., min_length=5, max_length=120)
    captcha_id: str = Field(...)
    captcha_text: str = Field(...)


class EmailVerifyRequest(BaseModel):
    """Step 2: verify code, then create account with provided credentials."""
    email: str = Field(..., min_length=5, max_length=120)
    code: str = Field(...)
    username: str = Field(..., min_length=3, max_length=24)
    password: str = Field(..., min_length=6, max_length=64)
    avatar_index: int = Field(default=0, ge=0, le=11)


# ── Endpoints ──

@router.get("/captcha")
async def get_captcha():
    text = _gen_captcha()
    cid = secrets.token_hex(12)
    _captcha_store[cid] = text
    if len(_captcha_store) > 50:
        for k in list(_captcha_store)[:10]:
            _captcha_store.pop(k, None)
    return Response(content=_captcha_image(text), media_type="image/png", headers={"X-Captcha-Id": cid})


@router.post("/send-code")
async def send_code(payload: EmailRegisterRequest):
    """Step 1: validate CAPTCHA + email, send verification code. No credentials needed yet."""
    # Validate CAPTCHA (don't consume yet — only consume on success)
    expected = _captcha_store.get(payload.captcha_id)
    if expected is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码已过期，请刷新重试")
    if payload.captcha_text.upper().strip() != expected.upper().strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图形验证码错误")

    await init_auth_storage()
    _init_email_tables()

    email = payload.email.strip().lower()

    # Check if email already bound to an existing user
    try:
        with get_auth_db_connection() as db:
            row = db.execute("SELECT username FROM users WHERE email = ?", [email]).fetchone()
            if row:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已被注册，请直接登录或使用忘记密码")
    except HTTPException:
        raise
    except Exception:
        pass

    # Pre-validate email address
    ok, verify_msg = await asyncio.to_thread(_verify_email_address, email)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"邮箱无效：{verify_msg}")

    code = _gen_code()
    _email_codes[email] = {
        "code": code, "username": "", "password": "",
        "avatar_index": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRE_MINUTES),
    }

    sent = await asyncio.to_thread(_send_email, email, code, email.split("@")[0])
    if not sent:
        err = "邮件发送失败。请确认已配置 SMTP（QQ邮箱 → 设置 → 账户 → POP3/SMTP → 开启并获取授权码）"
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=err)

    # Consume CAPTCHA only on success
    _captcha_store.pop(payload.captcha_id, None)
    return {"status": "success", "message": f"验证码已发送至 {email}"}


@router.post("/verify")
async def verify_and_register(payload: EmailVerifyRequest):
    await init_auth_storage()
    _init_email_tables()

    email = payload.email.strip().lower()
    code = payload.code.strip()

    record = _email_codes.get(email)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到验证请求")
    if datetime.now(timezone.utc) > record["expires_at"]:
        del _email_codes[email]
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="验证码已过期")
    if not secrets.compare_digest(record["code"], code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    # Use credentials from the user in step 2 (NOT from the stored record)
    username = _normalize_username(payload.username)
    password = str(payload.password or "")
    _validate_register_payload(username, password)

    created = await asyncio.to_thread(_create_user_sync, username, password, payload.avatar_index, email)
    if not created:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    try:
        with get_auth_db_connection() as db:
            db.execute("INSERT OR IGNORE INTO email_verified (email, username) VALUES (?, ?)", [email, username])
            db.commit()
    except Exception:
        pass

    del _email_codes[email]
    return {"status": "success", "message": f"注册完成，请使用 {username} 登录", "username": username}


# ── Password Reset ──

class ForgotPasswordRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=24)


class ResetPasswordRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=24)
    code: str = Field(...)
    new_password: str = Field(..., min_length=6, max_length=64)


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    """Send a password-reset code to the user's bound email."""
    await init_auth_storage()

    username = _normalize_username(payload.username)

    # Look up user's email from the users table
    try:
        with get_auth_db_connection() as db:
            row = db.execute("SELECT email FROM users WHERE username = ?", [username]).fetchone()
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="数据库查询失败")

    if not row or not row[0]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该账号未绑定邮箱，无法找回密码")

    email = str(row[0]).strip()
    code = _gen_code()
    _email_codes[email] = {
        "code": code, "username": username, "password": "",
        "avatar_index": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=CODE_EXPIRE_MINUTES),
    }

    sent = await asyncio.to_thread(_send_email, email, code, username)
    if not sent:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="邮件发送失败，请确认 SMTP 已配置")

    return {"status": "success", "message": f"重置密码验证码已发送至绑定邮箱"}


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    """Verify reset code and set a new password."""
    await init_auth_storage()

    username = _normalize_username(payload.username)
    code = payload.code.strip()
    new_password = str(payload.new_password or "")

    # Validate new password
    from api.auth import PASSWORD_REGEX
    if not re.match(PASSWORD_REGEX, new_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密码需 6-64 位且包含字母和数字")

    # Find the code by username (stored against email)
    reset_record = None
    reset_email = None
    for email, record in _email_codes.items():
        if record["username"] == username:
            reset_record = record
            reset_email = email
            break

    if not reset_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到重置请求，请先点击忘记密码")

    if datetime.now(timezone.utc) > reset_record["expires_at"]:
        del _email_codes[reset_email]
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="验证码已过期")

    if not secrets.compare_digest(reset_record["code"], code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    # Update password
    try:
        from api.auth import _hash_password, _iso, _utc_now
        new_hash = _hash_password(new_password)
        with get_auth_db_connection() as db:
            db.execute("UPDATE users SET password_hash = ? WHERE username = ?", [new_hash, username])
            db.commit()
        del _email_codes[reset_email]
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="密码更新失败")

    return {"status": "success", "message": "密码已重置，请使用新密码登录"}
