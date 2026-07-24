from __future__ import annotations

from email.message import EmailMessage
import mimetypes
import os
from pathlib import Path
import smtplib


def send_report(report_path: Path, html_path: Path) -> bool:
    sender = os.getenv("EMAIL_FROM", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    recipient = os.getenv("EMAIL_TO", "zrxzrx1227@163.com")
    if not sender or not password or not recipient:
        return False
    host = os.getenv("EMAIL_SMTP_SERVER") or ("smtp.163.com" if sender.endswith("@163.com") else "")
    port = int(os.getenv("EMAIL_SMTP_PORT") or "465")
    if not host:
        raise RuntimeError("EMAIL_SMTP_SERVER is required for this sender domain")
    message = EmailMessage()
    message["Subject"] = f"Research Radar 科研周报 · {report_path.stem}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(report_path.read_text(encoding="utf-8"))
    message.add_alternative(html_path.read_text(encoding="utf-8"), subtype="html")
    with smtplib.SMTP_SSL(host, port, timeout=30) as client:
        client.login(sender, password)
        client.send_message(message)
    return True

