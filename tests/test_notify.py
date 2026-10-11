import email
import subprocess

import pytest

from job_radar import notify


@pytest.fixture
def digest_files(home):
    (home.root / "digest.md").write_text("2 new matching jobs")
    (home.root / "digest.html").write_text("<p>2 new matching jobs</p>")
    (home.root / "digest_subject.txt").write_text("Job matches 2026-10-11: 2 new\n")
    return home


class FakeSMTP:
    sent = []

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def login(self, user, password):
        self.login_as = (user, password)

    def sendmail(self, sender, to, msg):
        FakeSMTP.sent.append((self.host, self.port, self.login_as, sender, to, email.message_from_string(msg)))


def test_sends_by_smtp(digest_files, monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("SMTP_USER", "me@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_TO", "a@example.com, b@example.com")
    notify.run(digest_files)
    host, port, login, sender, to, msg = FakeSMTP.sent[0]
    assert (host, port, login, sender) == ("smtp.gmail.com", 465, ("me@example.com", "app-password"), "me@example.com")
    assert to == ["a@example.com", "b@example.com"]
    assert msg["Subject"] == "Job matches 2026-10-11: 2 new"
    assert [p.get_content_type() for p in msg.get_payload()] == ["text/plain", "text/html"]


def test_other_smtp_server(digest_files, monkeypatch):
    FakeSMTP.sent = []
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    for k, v in {"SMTP_USER": "u", "SMTP_PASSWORD": "p", "EMAIL_TO": "t", "SMTP_HOST": "mail.example.com",
                 "SMTP_PORT": "2465"}.items():
        monkeypatch.setenv(k, v)
    notify.run(digest_files)
    assert FakeSMTP.sent[0][:2] == ("mail.example.com", 2465)


def test_falls_back_to_a_github_issue(digest_files, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, check: calls.append(args))
    monkeypatch.setenv("GH_TOKEN", "x")
    notify.run(digest_files)
    assert calls[0][:5] == ["gh", "issue", "create", "--title", "Job matches 2026-10-11: 2 new"]


def test_prints_without_email_or_github(digest_files, capsys):
    notify.run(digest_files)
    assert "2 new matching jobs" in capsys.readouterr().out


def test_nothing_to_send(home, capsys):
    notify.run(home)
    assert "no digest to send" in capsys.readouterr().out
