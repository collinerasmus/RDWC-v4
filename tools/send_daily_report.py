#!/usr/bin/env python3
"""Generate and send RDWC daily report from local Pi context."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from generate_daily_report import generate_report


def require(name: str, value: str) -> str:
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    api_url = os.getenv("RDWC_API_URL", "http://127.0.0.1:8080")
    report_file = os.getenv("REPORT_OUTPUT", "grow-report.html")

    server = require("EMAIL_SERVER", (os.getenv("EMAIL_SERVER") or "").strip())
    port = int((os.getenv("EMAIL_PORT") or "587").strip())
    user = require("EMAIL_USER", (os.getenv("EMAIL_USER") or "").strip())
    password = require("EMAIL_PASSWORD", "".join((os.getenv("EMAIL_PASSWORD") or "").split()))
    to_addr = (os.getenv("EMAIL_TO") or "").strip() or user
    from_addr = (os.getenv("EMAIL_FROM") or user).strip()

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
