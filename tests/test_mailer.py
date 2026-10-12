from pathlib import Path

import pytest

from research_radar.mailer import send_report


def _report_files(tmp_path: Path) -> tuple[Path, Path]:
    report = tmp_path / "2026-W32.md"
    html = tmp_path / "index.html"
    report.write_text("weekly report", encoding="utf-8")
    html.write_text("<p>weekly report</p>", encoding="utf-8")
    return report, html


def test_requested_email_fails_when_configuration_is_missing(monkeypatch, tmp_path, capsys):
    for name in ("EMAIL_FROM", "EMAIL_PASSWORD", "EMAIL_TO"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO"):
        send_report(*_report_files(tmp_path))

    assert capsys.readouterr().out == ""


def test_email_success_is_visible_in_logs(monkeypatch, tmp_path, capsys):
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            events.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def login(self, sender, password):
            events.append(("login", sender, password))

        def send_message(self, message):
            events.append(("send", message["To"], message["Subject"]))

    monkeypatch.setenv("EMAIL_FROM", "sender@163.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "recipient@example.com")
    monkeypatch.delenv("EMAIL_SMTP_SERVER", raising=False)
    monkeypatch.delenv("EMAIL_SMTP_PORT", raising=False)
    monkeypatch.setattr("research_radar.mailer.smtplib.SMTP_SSL", FakeSMTP)

    assert send_report(*_report_files(tmp_path)) is True

    assert events[0] == ("connect", "smtp.163.com", 465, 30)
    assert events[1] == ("login", "sender@163.com", "secret")
    assert events[2][0:2] == ("send", "recipient@example.com")
    assert "SMTP server accepted report delivery" in capsys.readouterr().out
