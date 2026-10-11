"""Shared fixtures. `web` replaces the network: tests register canned responses by URL pattern, and any
request that matches none fails the test, so nothing ever reaches a real server."""
import io
import json
import re
import shutil
import urllib.request
from pathlib import Path

import pytest

from job_radar.home import Home

FIXTURE = Path(__file__).parent / "fixtures" / "home"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeWeb:
    def __init__(self):
        self.routes = []      # (pattern, method or None, response)
        self.requests = []    # (method, url, body as dict or None, headers)

    def add(self, pattern, response, method=None):
        """response: dict/list (sent as JSON), str/bytes (sent as is), an Exception (raised), or a
        function of (url, body) returning one of those."""
        self.routes.insert(0, (re.compile(pattern), method, response))

    def open(self, req, timeout=None, data=None):
        url = req.full_url if isinstance(req, urllib.request.Request) else req
        method = req.get_method() if isinstance(req, urllib.request.Request) else "GET"
        raw = req.data if isinstance(req, urllib.request.Request) else data
        body = json.loads(raw) if raw else None
        headers = dict(req.header_items()) if isinstance(req, urllib.request.Request) else {}
        self.requests.append((method, url, body, headers))
        for pattern, want, response in self.routes:
            if pattern.search(url) and (want is None or want == method):
                if callable(response):
                    response = response(url, body)
                if isinstance(response, Exception):
                    raise response
                if isinstance(response, (dict, list)):
                    response = json.dumps(response)
                if isinstance(response, str):
                    response = response.encode()
                return FakeResponse(response)
        raise AssertionError(f"unexpected request: {method} {url}")

    def urls(self):
        return [u for _, u, _, _ in self.requests]


@pytest.fixture
def web(monkeypatch):
    fake = FakeWeb()
    monkeypatch.setattr(urllib.request, "urlopen", fake.open)

    class Opener:
        def open(self, req, timeout=None):
            return fake.open(req, timeout)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    return fake


@pytest.fixture
def home(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "home")
    return Home(tmp_path / "home")


@pytest.fixture(autouse=True)
def no_github(monkeypatch):
    """Tests never see the developer's own GitHub or email settings."""
    for k in ("GH_TOKEN", "GITHUB_REPOSITORY", "GITHUB_REPOSITORY_OWNER", "SMTP_USER", "SMTP_PASSWORD",
              "EMAIL_TO", "SMTP_HOST", "SMTP_PORT", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
              "REVIEW_MODEL", "REVIEW_EFFORT", "JOB_RADAR_HOME"):
        monkeypatch.delenv(k, raising=False)
