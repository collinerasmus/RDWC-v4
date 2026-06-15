#!/usr/bin/env python3
"""Generate and send RDWC daily report from local Pi context."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from generate_daily_report import generate_report


def _normalize_app_password(raw: str) -> str:
    return "".join((raw or "").replace("\r", "").replace("\n", "").split())


def _secret_file_path() -> str:
    return os.getenv("RDWC_REPORTS_SECRET_FILE", "/home/pi/.config/rdwc/daily-report.secret")


def _mail_env_file_path() -> str:
    return os.getenv("RDWC_REPORTS_MAIL_ENV_FILE", "/home/pi/.config/rdwc/daily-report.env")


def _load_env_file(path: str) -> dict:
    out = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        return out
    return out


def _effective_mail_provider(provider: str, server: str, user: str) -> str:
    p = str(provider or "").strip().lower()
    if p in ("gmail", "outlook", "custom"):
        return p
    s = str(server or "").lower()
    u = str(user or "").lower()
    if "gmail" in s or u.endswith("@gmail.com"):
        return "gmail"
    if "office365" in s or "outlook" in s or u.endswith("@outlook.com") or u.endswith("@hotmail.com"):
        return "outlook"
    return "custom"


def _password_valid_for_provider(password: str, provider: str) -> bool:
    if not password:
        return False
    if provider == "gmail":
        return len(password) == 16 and password.isalnum()
    return len(password) >= 8


def _merged_mail_env() -> dict:
    out = {}
    out.update(_load_env_file("/etc/rdwc-daily-report.env"))
    for k in ("RDWC_API_URL", "REPORT_OUTPUT", "EMAIL_SERVER", "EMAIL_PORT", "EMAIL_USER", "EMAIL_FROM", "EMAIL_TO", "REPORTS_SMTP_PROVIDER"):
        v = os.getenv(k)
        if v is not None and str(v).strip() != "":
            out[k] = str(v).strip()
    out.update(_load_env_file(_mail_env_file_path()))
    pw = _load_password()
    if pw:
        out["EMAIL_PASSWORD"] = pw
    return out


def _load_password() -> str:
    pw = _normalize_app_password(os.getenv("EMAIL_PASSWORD") or "")
    if pw:
        return pw
    path = _secret_file_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _normalize_app_password(f.read().strip())
    except Exception:
        return ""


def require(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    mail_env = _merged_mail_env()

    api_url = str(mail_env.get("RDWC_API_URL") or "http://127.0.0.1:8080")
    report_file = str(mail_env.get("REPORT_OUTPUT") or "grow-report.html")

    server = require("EMAIL_SERVER", str(mail_env.get("EMAIL_SERVER") or "").strip())
    port = int(str(mail_env.get("EMAIL_PORT") or "587").strip())
    user = require("EMAIL_USER", str(mail_env.get("EMAIL_USER") or "").strip())
    password = require("EMAIL_PASSWORD", _normalize_app_password(str(mail_env.get("EMAIL_PASSWORD") or "")))
    provider = _effective_mail_provider(str(mail_env.get("REPORTS_SMTP_PROVIDER") or ""), server, user)
    if not _password_valid_for_provider(password, provider):
        if provider == "gmail":
            raise RuntimeError("EMAIL_PASSWORD must be 16 letters/numbers (spaces allowed in UI input)")
        raise RuntimeError("EMAIL_PASSWORD must be at least 8 characters")
    to_addr = str(mail_env.get("EMAIL_TO") or "").strip() or user
    from_addr = str(mail_env.get("EMAIL_FROM") or user).strip()

    generate_report(api_url, report_file)

    with open(report_file, "r", encoding="utf-8") as f:
        html_body = f.read()

    subject = "RDWC Daily Grow Report"
    text_body = "Your RDWC daily report is attached as HTML in the message body."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP(server, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(user, password)
        smtp.sendmail(from_addr, [to_addr], msg.as_string())

    print("Daily report email sent successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
