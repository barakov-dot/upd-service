import threading
import time

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

from upd_service import api, config, jobs, llm, pipeline


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "AUTH_USERS", {"ann": "pw1", "bob": "pw2"})
    monkeypatch.setattr(config, "MAX_CONCURRENT", 1)
    with TestClient(api.app) as c:
        yield c


def login(c, u, p):
    return c.post("/api/login", json={"username": u, "password": p})


def test_auth_required_and_login(client):
    assert client.get("/api/doc-types").status_code == 401
    assert client.get("/", follow_redirects=False).status_code in (302, 307)
    assert login(client, "ann", "bad").status_code == 401
    assert login(client, "ann", "pw1").status_code == 200
    assert client.get("/api/me").json()["user"] == "ann"
    client.post("/api/logout")
    assert client.get("/api/me").status_code == 401


def test_queue_positions(client, monkeypatch):
    gate = threading.Event()

    def fake(pdf_bytes):
        gate.wait(5)
        return {"meta": {"doc_type": "УПД", "rotation": 0}}
    monkeypatch.setattr(pipeline, "recognize", fake)
    monkeypatch.setattr(jobs.pdf, "preview_b64", lambda b, r: "pdf:x")
    login(client, "ann", "pw1")
    pdf = ("a.pdf", b"%PDF-1.4", "application/pdf")
    j1 = client.post("/api/recognize", files={"file": pdf}).json()
    time.sleep(0.3)
    j2 = client.post("/api/recognize", files={"file": pdf}).json()
    assert j2["status"] == "queued" and j2["position"] == 1 and j2["ahead"] == 0
    assert client.get(f"/api/jobs/{j1['id']}").json()["status"] == "running"
    gate.set()
    for _ in range(50):
        if client.get(f"/api/jobs/{j2['id']}").json()["status"] == "done":
            break
        time.sleep(0.1)
    assert client.get(f"/api/jobs/{j2['id']}").json()["status"] == "done"
    # чужую задачу видеть нельзя
    c2 = TestClient(api.app)
    login(c2, "bob", "pw2")
    assert c2.get(f"/api/jobs/{j1['id']}").status_code == 404


def _rate_limit():
    return groq.RateLimitError("x", response=httpx.Response(429, headers={"retry-after": "30"},
                                                          request=httpx.Request("POST", "http://x")), body=None)


def test_key_rotation_on_429(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEYS", ["gsk_aaaaaaaa1", "gsk_bbbbbbbb2"])
    monkeypatch.setattr(llm, "_cooldown", {})
    used = []

    class Fake:
        def __init__(self, key):
            self.key = key
            self.chat = self
            self.completions = self

        def create(self, **kw):
            used.append(self.key)
            if self.key.endswith("1"):
                raise _rate_limit()
            m = type("M", (), {"content": "ok"})
            return type("R", (), {"choices": [type("C", (), {"message": m})]})
    monkeypatch.setattr(llm, "_client", lambda k: Fake(k))
    assert llm.chat([], ["m"]) == ("ok", "m")
    assert used == ["gsk_aaaaaaaa1", "gsk_bbbbbbbb2"]
    used.clear()
    llm.chat([], ["m"])          # первый ключ на паузе — сразу второй
    assert used == ["gsk_bbbbbbbb2"]


def test_all_keys_limited_message(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEYS", ["gsk_aaaaaaaa1"])
    monkeypatch.setattr(llm, "_cooldown", {})

    class Fake:
        chat = completions = None
        def __init__(self):
            self.chat = self.completions = self
        def create(self, **kw):
            raise _rate_limit()
    monkeypatch.setattr(llm, "_client", lambda k: Fake())
    with pytest.raises(llm.LLMError, match="Лимиты всех ключей"):
        llm.chat([], ["m"])
