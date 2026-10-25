import smtplib

import pytest

import complaint_log
import emailer


def test_compose_body_layout():
    body = emailer.compose_body("Dear Sir,\nFix it.", "──────── Location details ────────\nLandmark: X",
                                "प्रिय महोदय", "Hindi", "pothole_20261025_1042.jpg", "PH-20261025-1042")
    assert body == (
        "Dear Sir,\nFix it.\n\n"
        "──────── Location details ────────\nLandmark: X\n\n"
        "──────── Hindi version ────────\nप्रिय महोदय\n\n"
        "Photo attached: pothole_20261025_1042.jpg\nReference: PH-20261025-1042\n"
    )
    assert "version" not in emailer.compose_body("L", "B", "", "English only", "p.jpg", "R")


def test_build_email(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    msg = emailer.build_email("dept@up.gov.in", "me@gmail.com", "Pothole complaint – Lanka", "Body ±",
                              b"\xff\xd8jpeg", "pothole_20261025_1042.jpg")
    assert (msg["From"], msg["To"], msg["Cc"]) == ("me@gmail.com", "dept@up.gov.in", "me@gmail.com")
    assert msg["Subject"] == "Pothole complaint – Lanka"
    [attachment] = list(msg.iter_attachments())
    assert attachment.get_filename() == "pothole_20261025_1042.jpg"
    assert attachment.get_content_type() == "image/jpeg"
    assert attachment.get_content() == b"\xff\xd8jpeg"
    assert msg.get_body().get_content().strip() == "Body ±"


def test_build_email_without_cc(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    assert emailer.build_email("me@gmail.com", None, "[TEST] S", "B", b"x", "p.jpg")["Cc"] is None


def test_gmail_configured(monkeypatch):
    monkeypatch.setenv("GMAIL_ADDRESS", "you@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    assert not emailer.gmail_configured()
    monkeypatch.setenv("GMAIL_ADDRESS", "me@gmail.com")
    assert emailer.gmail_configured()
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "xxxx xxxx xxxx xxxx")
    assert not emailer.gmail_configured()


def test_send_email_login_failure(monkeypatch):
    class FakeSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def login(self, user, password):
            assert " " not in password
            raise smtplib.SMTPAuthenticationError(535, b"Bad credentials")

    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")
    with pytest.raises(emailer.EmailError, match="GMAIL_APP_PASSWORD"):
        emailer.send_email(emailer.build_email("a@b.c", None, "S", "B", b"x", "p.jpg"))


def test_log_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(complaint_log, "LOG_PATH", tmp_path / "data" / "complaints.csv")
    assert complaint_log.read_all() == []
    complaint_log.append({"ref_id": "PH-20261025-1042", "status": "sent", "latitude": 25.307111})
    complaint_log.append({"ref_id": "PH-20261025-1050", "status": "failed", "error": "Gmail login failed, retry"})
    rows = complaint_log.read_all()
    assert [r["ref_id"] for r in rows] == ["PH-20261025-1042", "PH-20261025-1050"]
    assert rows[0]["latitude"] == "25.307111" and rows[1]["error"] == "Gmail login failed, retry"
    assert list(rows[0]) == complaint_log.COLUMNS
