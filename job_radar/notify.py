"""Email the daily digest (digest.md / digest.html) through SMTP; without SMTP settings, open a GitHub
issue instead, or print it.

Settings (repo secrets): SMTP_USER (the address that sends, e.g. a Gmail address), SMTP_PASSWORD (for
Gmail, an app password), EMAIL_TO (where it goes; several addresses separated by commas).
SMTP_HOST / SMTP_PORT default to Gmail (smtp.gmail.com, 465).
"""
from __future__ import annotations

import os
import smtplib
import subprocess
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .home import Home


def smtp_settings():
    user, password, to = (os.environ.get(k) for k in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"))
    return (user, password, to) if user and password and to else None


def send(subject: str, md: str, html: str) -> None:
    user, password, to = smtp_settings()
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText(md, "plain"))
    msg.attach(MIMEText(html, "html"))
    host, port = os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465"))
    with smtplib.SMTP_SSL(host, port) as s:
        s.login(user, password)
        s.sendmail(user, [a.strip() for a in to.split(",")], msg.as_string())


def run(home: Home) -> None:
    md_path, html_path = home.root / "digest.md", home.root / "digest.html"
    if not md_path.exists():
        print("no digest to send")
        return
    subject_file = home.root / "digest_subject.txt"
    title = subject_file.read_text().strip() if subject_file.exists() else f"Job matches {date.today().isoformat()}"
    if smtp_settings():
        send(title, md_path.read_text(), html_path.read_text())
        print(f"emailed digest to {os.environ['EMAIL_TO']}")
    elif os.environ.get("GH_TOKEN"):
        subprocess.run(["gh", "issue", "create", "--title", title, "--body-file", str(md_path)], check=True)
        print("no SMTP settings; opened a GitHub issue instead")
    else:
        print(md_path.read_text())
