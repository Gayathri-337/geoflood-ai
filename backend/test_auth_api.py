"""
GeoFlood AI - Phase 17c test: accounts, login, tokens and roles.

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_auth_api
"""

import base64
import json
import os
import time
from datetime import timedelta

import jwt
import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.config import get_settings
from backend.database import get_db
from backend.main import app
from backend.security import create_access_token, decode_access_token
from backend.services import passwords
from backend.services import users as user_service

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")
ADMIN_PW, ANALYST_PW, VIEWER_PW = "admin-test-password-1", "analyst-pass-1234", "viewer-pass-12345"


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def login(client, username, password):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def token_for(client, username, password):
    r = login(client, username, password)
    assert r.status_code == 200, f"login of {username} failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def b64url(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def is_rejected(token, settings):
    try:
        decode_access_token(token, settings)
    except (jwt.InvalidTokenError, ValueError):
        return True
    return False


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 17c Accounts and Login Test")
    print(SEP)

    load_dotenv(config.ROOT / ".env")
    test_url, main_url = os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL")
    if not test_url:
        raise SystemExit("TEST_DATABASE_URL is missing from .env.")
    if test_url == main_url:
        raise SystemExit("TEST_DATABASE_URL must differ from DATABASE_URL: this test DROPS all tables.")
    try:
        conn = psycopg2.connect(test_url, connect_timeout=5)
    except psycopg2.OperationalError as err:
        raise SystemExit(f"Could not connect:\n{err}")
    conn.autocommit = True
    cur = conn.cursor()
    db_name = scalar(cur, "SELECT current_database()")
    if "test" not in db_name:
        raise SystemExit(f"Refusing to run: database '{db_name}' does not look like a test database.")
    print(f"\nTest database: {db_name}")
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())

    settings = get_settings()
    engine = create_engine(test_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False)

    def use_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = use_test_db
    client = TestClient(app)

    # ------------------------------------------------------------ 1
    print("\n--- 1. Password hashing and rules ---")
    pw = "correct horse battery"
    t0 = time.perf_counter()
    h1 = passwords.hash_password(pw)
    hash_ms = 1000 * (time.perf_counter() - t0)
    h2 = passwords.hash_password(pw)
    assert h1 != h2 and h1.startswith("scrypt$16384$8$1$") and pw not in h1
    ok(f"two hashes of the same password differ (random salt); format scrypt$N$r$p$salt$key; "
       f"one hash takes {hash_ms:.0f} ms on this machine")
    assert passwords.verify_password(pw, h1) and passwords.verify_password(pw, h2)
    assert not passwords.verify_password(pw + "x", h1) and not passwords.verify_password("", h1)
    unicode_pw = "pässwörd-日本語-123"
    assert passwords.verify_password(unicode_pw, passwords.hash_password(unicode_pw))
    ok("correct password accepted; wrong or empty password refused; non-ASCII passwords work")
    for broken in ("PLACEHOLDER-NOT-A-REAL-HASH", "", "scrypt$x$y$z$a$b", "md5$1$2$3$4$5", "scrypt$16384$8$1$!!!$!!!"):
        assert passwords.verify_password("anything", broken) is False
    ok("malformed stored hashes (including the sample users' placeholder) give False, not an exception")
    rules = [("short-pw", "someone", "at least 10"), ("x" * 129, "someone", "at most 128"),
             (" " * 12, "someone", "only spaces"), ("Gayathri-123", "gayathri-123", "same as the username"),
             ("\ud800" * 12, "someone", "cannot be stored")]
    for candidate, user, fragment in rules:
        try:
            passwords.check_password_rules(candidate, user)
        except ValueError as err:
            assert fragment in str(err), (candidate, str(err))
        else:
            raise AssertionError(f"password {candidate!r} should have been refused")
    ok("rules refuse: too short, too long, only spaces, same as the username, unstorable characters")

    # ------------------------------------------------------------ 2
    print("\n--- 2. Tokens ---")
    token, expires_in = create_access_token(42, settings)
    assert decode_access_token(token, settings) == 42 and expires_in == settings.access_token_minutes * 60
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["sub"] == "42" and set(payload) == {"sub", "iat", "exp"}
    ok(f"a valid token decodes to its user id; it holds only sub, iat and exp; lifetime {expires_in // 60} minutes")
    soon = int(time.time()) + 3600
    forged = {
        "expired token": create_access_token(42, settings, timedelta(seconds=-5))[0],
        "signed with another key": jwt.encode({"sub": "1", "exp": soon}, "x" * 40, algorithm="HS256"),
        "signature altered": token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1],
        "algorithm 'none'": f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{b64url({'sub': '1', 'exp': soon})}.",
        "no expiry": jwt.encode({"sub": "1"}, settings.secret_key, algorithm="HS256"),
        "user id not a number": jwt.encode({"sub": "abc", "exp": soon}, settings.secret_key, algorithm="HS256"),
        "user id out of range": jwt.encode({"sub": "99999999999999999999", "exp": soon},
                                           settings.secret_key, algorithm="HS256"),
        "not a token at all": "garbage",
    }
    for label, bad in forged.items():
        assert is_rejected(bad, settings), f"{label} was accepted!"
    ok(f"{len(forged)} bad tokens all rejected: " + ", ".join(forged))

    # ------------------------------------------------------------ 3
    print("\n--- 3. Creating the first admin (the service the command-line tool uses) ---")
    db = Session()
    admin = user_service.create_user(db, username="  Admin_Test ", email="Admin.Test@Example.com",
                                     password=ADMIN_PW, role="admin", full_name="Test Admin")
    db.commit()
    db.close()
    assert admin["username"] == "admin_test" and admin["email"] == "admin.test@example.com"
    assert admin["role"] == "admin" and "password_hash" not in admin
    stored = scalar(cur, "SELECT password_hash FROM users WHERE username = 'admin_test'")
    assert stored.startswith("scrypt$") and ADMIN_PW not in stored
    ok(f"admin created (id {admin['user_id']}); username and email were lower-cased; "
       "only a hash is stored in the database")

    # ------------------------------------------------------------ 4
    print("\n--- 4. Login and 'who am I' ---")
    r = login(client, "admin_test", ADMIN_PW)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == settings.access_token_minutes * 60
    assert ADMIN_PW not in r.text and "hash" not in r.text
    admin_token = body["access_token"]
    ok(f"login -> 200 with a bearer token valid for {body['expires_in'] // 60} minutes")
    assert login(client, "ADMIN_TEST", ADMIN_PW).status_code == 200
    ok("usernames are not case sensitive")

    bad_pw, unknown = login(client, "admin_test", "wrong-password-1"), login(client, "nobody", "wrong-password-1")
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json() == unknown.json() == {"detail": "Incorrect username or password."}
    assert "bearer" in bad_pw.headers["www-authenticate"].lower()
    ok("wrong password and unknown user give the identical 401 (no hint which usernames exist)")
    assert login(client, "admin_demo", "anything-at-all-1").status_code == 401
    assert login(client, "admin_test", "x" * 200).status_code == 401
    assert client.post("/api/auth/login", data={"username": "admin_test"}).status_code == 422
    ok("sample users with a placeholder hash cannot log in; a 200-character password -> 401; "
       "a missing field -> 422")

    me = client.get("/api/auth/me", headers=auth(admin_token))
    assert me.status_code == 200
    j = me.json()
    assert (j["username"], j["role"], j["email"], j["is_active"]) == ("admin_test", "admin", "admin.test@example.com", True)
    assert "password" not in me.text and "hash" not in me.text
    ok("GET /api/auth/me returns the account without any password data")
    ghost, _ = create_access_token(999999, settings)
    for label, headers in {"no token": {}, "garbage token": auth("garbage"), "a user that does not exist": auth(ghost),
                           "Basic instead of Bearer": {"Authorization": "Basic YWRtaW46eA=="}}.items():
        r = client.get("/api/auth/me", headers=headers)
        assert r.status_code == 401 and "bearer" in r.headers["www-authenticate"].lower(), label
    ok("/me refuses: no token, a garbage token, a validly signed token for a missing user, Basic auth")

    # ------------------------------------------------------------ 5
    print("\n--- 5. An admin creates accounts ---")
    H = auth(admin_token)
    r = client.post("/api/users", headers=H, json={"username": "Ravi_Analyst", "email": "ravi@example.com",
                                                   "password": ANALYST_PW, "role": "analyst", "full_name": "Ravi K"})
    assert r.status_code == 201, r.text
    analyst = r.json()
    assert analyst["username"] == "ravi_analyst" and analyst["role"] == "analyst" and ANALYST_PW not in r.text
    r = client.post("/api/users", headers=H, json={"username": "viewer_one", "email": "viewer.test@example.com",
                                                   "password": VIEWER_PW})
    assert r.status_code == 201 and r.json()["role"] == "viewer"
    viewer = r.json()
    ok("analyst and viewer created; usernames lower-cased; the role defaults to 'viewer'; no password in any response")
    assert client.post("/api/users", headers=H, json={"username": "RAVI_ANALYST", "email": "other@example.com",
                                                      "password": ANALYST_PW}).status_code == 409
    assert client.post("/api/users", headers=H, json={"username": "someone_else", "email": "RAVI@example.com",
                                                      "password": ANALYST_PW}).status_code == 409
    ok("duplicate username (even in another case) and duplicate email -> 409")
    weak = client.post("/api/users", headers=H, json={"username": "weak_user", "email": "weak@example.com",
                                                      "password": "tiny-pw-1"})
    assert weak.status_code == 422 and "at least 10" in weak.text and "tiny-pw-1" not in weak.text
    ok("a too-short password -> 422, and the rejected password is not repeated in the error")
    for label, extra in {"a username with spaces": {"username": "bad name!"},
                         "an invalid email": {"email": "not-an-email"},
                         "an unknown role": {"role": "root"}}.items():
        body = {"username": "valid_name", "email": "valid@example.com", "password": "long-enough-pass-1", **extra}
        assert client.post("/api/users", headers=H, json=body).status_code == 422, label
    assert scalar(cur, "SELECT count(*) FROM users") == 5      # 2 sample + admin + analyst + viewer
    ok("bad username, email and role -> 422; the database still has exactly 5 users")

    # ------------------------------------------------------------ 6
    print("\n--- 6. Only admins can manage users ---")
    analyst_token, viewer_token = token_for(client, "ravi_analyst", ANALYST_PW), token_for(client, "viewer_one", VIEWER_PW)
    assert client.get("/api/users").status_code == 401
    assert client.get("/api/users", headers=auth(viewer_token)).status_code == 403
    assert client.get("/api/users", headers=auth(analyst_token)).status_code == 403
    assert client.post("/api/users", headers=auth(analyst_token), json={
        "username": "sneaky", "email": "s@example.com", "password": "long-enough-pass-1"}).status_code == 403
    r = client.get("/api/users", headers=H)
    assert r.status_code == 200 and len(r.json()) == 5 and "hash" not in r.text
    assert len(client.get("/api/users?limit=2", headers=H).json()) == 2
    assert client.get("/api/users?limit=0", headers=H).status_code == 422
    ok("no token -> 401; viewer and analyst -> 403; admin sees 5 users with no password data; paging works")

    # ------------------------------------------------------------ 7
    print("\n--- 7. Changing roles and disabling accounts ---")
    vid = viewer["user_id"]
    r = client.patch(f"/api/users/{vid}", headers=H, json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.get("/api/users", headers=auth(viewer_token)).status_code == 200
    ok("promoting a viewer to admin works at once: the SAME old token now has admin rights")
    assert client.patch(f"/api/users/{vid}", headers=H, json={"role": "viewer"}).status_code == 200
    assert client.get("/api/users", headers=auth(viewer_token)).status_code == 403
    ok("demoting back takes effect at once too")

    aid = analyst["user_id"]
    assert client.get("/api/auth/me", headers=auth(analyst_token)).status_code == 200
    assert client.patch(f"/api/users/{aid}", headers=H, json={"is_active": False}).status_code == 200
    assert client.get("/api/auth/me", headers=auth(analyst_token)).status_code == 401
    r = login(client, "ravi_analyst", ANALYST_PW)
    assert r.status_code == 403 and "disabled" in r.json()["detail"]
    assert client.patch(f"/api/users/{aid}", headers=H, json={"is_active": True}).status_code == 200
    assert login(client, "ravi_analyst", ANALYST_PW).status_code == 200
    ok("disabling an account: the existing token stops working, login gives 403 'disabled'; re-enabling restores it")

    r = client.patch(f"/api/users/{aid}", headers=H, json={"full_name": "  Ravi Kumar  "})
    assert r.json()["full_name"] == "Ravi Kumar"
    assert client.patch(f"/api/users/{aid}", headers=H, json={"full_name": ""}).json()["full_name"] is None
    ok("full name can be changed (whitespace trimmed) and cleared with an empty string")

    demo_admin = scalar(cur, "SELECT user_id FROM users WHERE username = 'admin_demo'")
    assert client.patch(f"/api/users/{demo_admin}", headers=H, json={"is_active": False}).status_code == 200
    me_id = admin["user_id"]
    assert client.patch(f"/api/users/{me_id}", headers=H, json={"role": "analyst"}).status_code == 409
    assert client.patch(f"/api/users/{me_id}", headers=H, json={"is_active": False}).status_code == 409
    assert scalar(cur, "SELECT role || is_active::text FROM users WHERE user_id = %s", (me_id,)) == "admintrue"
    assert client.patch(f"/api/users/{me_id}", headers=H, json={"full_name": "Test Admin"}).status_code == 200
    assert client.patch(f"/api/users/{demo_admin}", headers=H, json={"is_active": True}).status_code == 200
    ok("the last active admin cannot be demoted or disabled (409); other changes to that admin are fine")

    assert client.patch("/api/users/999999", headers=H, json={"role": "viewer"}).status_code == 404
    assert client.patch(f"/api/users/{aid}", headers=H, json={}).status_code == 422
    assert client.patch(f"/api/users/{aid}", headers=H, json={"role": "root"}).status_code == 422
    assert client.patch("/api/users/0", headers=H, json={"role": "viewer"}).status_code == 422
    ok("unknown user -> 404; empty change, unknown role and id 0 -> 422")

    # ------------------------------------------------------------ 8
    print("\n--- 8. Changing your own password ---")
    t = token_for(client, "ravi_analyst", ANALYST_PW)
    new_pw = "a-brand-new-password-9"
    assert client.post("/api/auth/change-password", json={"current_password": ANALYST_PW, "new_password": new_pw}).status_code == 401
    assert client.post("/api/auth/change-password", headers=auth(t),
                       json={"current_password": "not-my-password-1", "new_password": new_pw}).status_code == 400
    assert client.post("/api/auth/change-password", headers=auth(t),
                       json={"current_password": ANALYST_PW, "new_password": ANALYST_PW}).status_code == 422
    r = client.post("/api/auth/change-password", headers=auth(t),
                    json={"current_password": ANALYST_PW, "new_password": "short-1"})
    assert r.status_code == 422 and "short-1" not in r.text
    assert login(client, "ravi_analyst", ANALYST_PW).status_code == 200      # nothing changed yet
    ok("refused: no login, wrong current password, same password, too-short password (and nothing changed)")
    r = client.post("/api/auth/change-password", headers=auth(t),
                    json={"current_password": ANALYST_PW, "new_password": new_pw})
    assert r.status_code == 204 and r.content == b""
    assert login(client, "ravi_analyst", ANALYST_PW).status_code == 401
    assert login(client, "ravi_analyst", new_pw).status_code == 200
    ok("password changed (204): the old one no longer works, the new one does")

    # ------------------------------------------------------------ 9
    print("\n--- 9. API documentation ---")
    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"])
    assert {"/api/auth/login", "/api/auth/me", "/api/auth/change-password",
            "/api/users", "/api/users/{user_id}"} <= paths
    assert any(s.get("type") == "oauth2" for s in spec["components"]["securitySchemes"].values())
    ok("login, me, change-password and user endpoints are documented; the OAuth2 'Authorize' button is available in /docs")

    app.dependency_overrides.clear()
    engine.dispose()
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    conn.close()
    print("\n  Test database reset to the sample data (the test users are gone).")
    print("\n" + SEP)
    print("  Accounts and login tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
