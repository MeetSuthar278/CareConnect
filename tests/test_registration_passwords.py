"""Registration password checks run without Firebase or database connections."""
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import Mock
import urllib.error

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    ("Abc@123", "Abc@123", False),
    ("password123", "password123", False),
    ("Password123", "Password123", False),
    ("password@123", "password@123", False),
    ("Password@123", "Password@123", True),
    ("Password@", "Password@", True),
    ("PASSWORD@", "PASSWORD@", True),
    ("PASSWORD-", "PASSWORD-", True),
    ("PASSWORD`", "PASSWORD`", True),
    ("", "", False),
    ("Password@123", "Different@123", False),
    ("Password@123", "", False),
    ("Password ", "Password ", False),
    ("Àbcdefg@", "Àbcdefg@", False),
]


@pytest.fixture
def utility(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "careconnect-bfb9e")
    monkeypatch.setenv("FIREBASE_WEB_API_KEY", "test-only-placeholder")
    spec = importlib.util.spec_from_file_location("firebase_test_user", ROOT / "tools/create_firebase_test_user.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("password,confirmation,accepted", SCENARIOS)
def test_utility_blocks_invalid_passwords_before_network(utility, monkeypatch, password, confirmation, accepted):
    monkeypatch.setattr(utility.sys.stdin, "isatty", lambda: True)
    answers = iter(["person@example.test", "CREATE"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    passwords = iter([password, confirmation])
    monkeypatch.setattr(utility.getpass, "getpass", lambda _: next(passwords))
    post = Mock(return_value={"idToken": "test-only-token"})
    monkeypatch.setattr(utility, "post", post)

    assert utility.main([]) == (0 if accepted else 1)
    assert post.call_count == (2 if accepted else 0)
    if accepted:
        assert post.call_args_list[0].args[0] == "signUp"
        assert post.call_args_list[0].args[1]["password"] == password


def test_resend_accepts_existing_password_without_new_policy(utility, monkeypatch):
    monkeypatch.setattr(utility.sys.stdin, "isatty", lambda: True)
    answers = iter(["person@example.test", "RESEND"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setattr(utility.getpass, "getpass", lambda _: "old123")
    post = Mock(return_value={"idToken": "test-only-token"})
    monkeypatch.setattr(utility, "post", post)

    assert utility.main(["--resend-verification"]) == 0
    assert post.call_args_list[0].args[0] == "signInWithPassword"


@pytest.mark.parametrize("code", ["WEAK_PASSWORD", "PASSWORD_DOES_NOT_MEET_REQUIREMENTS"])
def test_firebase_policy_errors_are_sanitized(utility, monkeypatch, code):
    response = io.BytesIO(json.dumps({"error": {"message": code + " : private-server-detail"}}).encode())
    failure = urllib.error.HTTPError("https://example.test", 400, "Bad request", {}, response)
    monkeypatch.setattr(utility.urllib.request, "urlopen", Mock(side_effect=failure))

    with pytest.raises(utility.SetupError) as caught:
        utility.post("signUp", {"password": "not-sent"})
    assert "8 characters" in str(caught.value)
    assert "private-server-detail" not in str(caught.value)
    assert code not in str(caught.value)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "registration-tests-only")
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("HOSTED_MODE", "0")
    for key in ("FIREBASE_WEB_API_KEY", "FIREBASE_AUTH_DOMAIN", "FIREBASE_STORAGE_BUCKET",
                "FIREBASE_MESSAGING_SENDER_ID", "FIREBASE_APP_ID", "FIREBASE_MEASUREMENT_ID"):
        monkeypatch.setenv(key, "test-only-placeholder")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "careconnect-bfb9e")
    from app import create_app
    return create_app({"TESTING": True}).test_client()


@pytest.mark.parametrize("kind,script", [("individual", "register.js"), ("organization", "register-organization.js")])
def test_flask_serves_registration_checklist_and_shared_assets(client, kind, script):
    response = client.get(f"/register/{kind}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert html.count('data-password-requirement="') == 3
    assert 'minlength="8"' in html
    assert f'/team-static/js/{script}' in html
    assert '/team-static/css/style.css' in html
    javascript = client.get(f"/team-static/js/{script}")
    assert javascript.status_code == 200
    assert "./registration-password.js" in javascript.get_data(as_text=True)
    assert client.get("/team-static/js/registration-password.js").status_code == 200


def test_login_has_no_new_password_requirements(client):
    response = client.get("/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "password-requirements" not in html
    assert "data-registration-password" not in html
    assert 'minlength="8"' not in html
    assert "/team-static/js/login.js" in html
