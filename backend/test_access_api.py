"""
GeoFlood AI - Phase 17d test: who may do what on the data endpoints.

DESTRUCTIVE: rebuilds every table in TEST_DATABASE_URL.
Usage (project root):  python -m backend.test_access_api
"""

import os
from datetime import timedelta

import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.config import Settings, get_settings
from backend.database import get_db
from backend.main import app
from backend.security import create_access_token
from backend.services import users as user_service

DB_DIR = config.ROOT / "database"
SEP = "=" * 70
BUILD_FILES = ("reset.sql", "schema.sql", "impact_analysis.sql", "sample_data.sql")

READS = ["/api/sources", "/api/events", "/api/events/1", "/api/analyses", "/api/analyses/1",
         "/api/analyses/1/zones", "/api/analyses/1/impact", "/api/analyses/1/impact/roads",
         "/api/stats/dashboard"]
READS_NOT_FOUND = ["/api/analyses/1/mask", "/api/predict/" + "0" * 32]     # allowed, but nothing to return: 404
# (method, url, request arguments, status when ACCESS IS ALLOWED)
WRITES = [("POST", "/api/events", {"json": {}}, 422),
          ("POST", "/api/predict", {}, 422),
          ("POST", "/api/analyses", {}, 422),
          ("POST", "/api/analyses/1/impact", {}, 200)]
PASSWORDS = {"admin_a": "admin-access-pw-1", "analyst_a": "analyst-access-pw-1", "viewer_a": "viewer-access-pw-1"}


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    return cur.fetchone()[0]


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 17d Access Rules Test")
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

    engine = create_engine(test_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, autoflush=False)

    def use_test_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    db = Session()
    for username, role in (("admin_a", "admin"), ("analyst_a", "analyst"), ("viewer_a", "viewer")):
        user_service.create_user(db, username=username, email=f"{username}@example.com",
                                 password=PASSWORDS[username], role=role)
    db.commit()
    db.close()

    app.dependency_overrides[get_db] = use_test_db
    client = TestClient(app)
    closed, open_ = Settings(public_read=False), Settings(public_read=True)
    real = get_settings()

    def policy(settings):
        app.dependency_overrides[get_settings] = lambda: settings

    def token(username):
        r = client.post("/api/auth/login", data={"username": username, "password": PASSWORDS[username]})
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def bearer(t):
        return {"Authorization": f"Bearer {t}"}

    def call(method, url, headers=None, **kwargs):
        return client.request(method, url, headers=headers, **kwargs)

    # ------------------------------------------------------------ 1
    print("\n--- 1. Setup and the default ---")
    assert Settings.model_fields["public_read"].default is False
    tokens = {name: token(name) for name in PASSWORDS}
    ok("three users created through the service and logged in through the API; "
       "the default for public_read is False (login required)")

    # ------------------------------------------------------------ 2
    print("\n--- 2. Always public: health checks and login ---")
    policy(closed)
    for url in ("/api/health", "/api/health/model", "/api/health/db", "/"):
        assert call("GET", url).status_code == 200, url
    assert client.post("/api/auth/login", data={"username": "viewer_a", "password": PASSWORDS["viewer_a"]}).status_code == 200
    ok("health checks and login work without a token, even when reads need a login")
    assert call("GET", "/api/users").status_code == 401
    assert call("GET", "/api/users", bearer(tokens["viewer_a"])).status_code == 403
    assert call("GET", "/api/users", bearer(tokens["admin_a"])).status_code == 200
    ok("/api/users stays admin-only: no token 401, viewer 403, admin 200")

    # ------------------------------------------------------------ 3
    print("\n--- 3. Reading needs a login (PUBLIC_READ off) ---")
    policy(closed)
    for url in READS + READS_NOT_FOUND:
        r = call("GET", url)
        assert r.status_code == 401 and "bearer" in r.headers["www-authenticate"].lower(), (url, r.status_code)
    ok(f"{len(READS) + len(READS_NOT_FOUND)} read endpoints refuse an anonymous caller with 401")
    uid = scalar(cur, "SELECT user_id FROM users WHERE username = 'analyst_a'")
    expired, _ = create_access_token(uid, real, timedelta(seconds=-5))
    for label, header in {"a garbage token": bearer("garbage"), "an expired token": bearer(expired)}.items():
        assert call("GET", "/api/events", header).status_code == 401, label
    ok("a garbage token and an expired token are refused too")
    for role in ("viewer_a", "analyst_a", "admin_a"):
        h = bearer(tokens[role])
        for url in READS:
            r = call("GET", url, h)
            assert r.status_code == 200, f"{role} {url}: {r.status_code} {r.text[:150]}"
        for url in READS_NOT_FOUND:
            assert call("GET", url, h).status_code == 404, url
    ok("viewer, analyst and admin can all read every endpoint (404 only where there is nothing to return)")

    # ------------------------------------------------------------ 4
    print("\n--- 4. Changing data needs an analyst ---")
    for method, url, kwargs, _ in WRITES:
        r = call(method, url, **kwargs)
        assert r.status_code == 401, (url, r.status_code)
        r = call(method, url, bearer(tokens["viewer_a"]), **kwargs)
        assert r.status_code == 403 and "analyst" in r.json()["detail"], (url, r.status_code, r.text[:150])
    ok(f"all {len(WRITES)} write endpoints: anonymous -> 401, viewer -> 403")
    for role in ("analyst_a", "admin_a"):
        for method, url, kwargs, allowed in WRITES:
            r = call(method, url, bearer(tokens[role]), **kwargs)
            assert r.status_code == allowed, f"{role} {url}: expected {allowed}, got {r.status_code} {r.text[:150]}"
    ok("analyst and admin pass the check on all of them (422 = access allowed, the empty request was then "
       "rejected as invalid; the impact computation really ran and returned 200)")
    r = call("POST", "/api/events", bearer(tokens["analyst_a"]), json={"name": "Created by an analyst"})
    assert r.status_code == 201 and r.json()["name"] == "Created by an analyst"
    ok("an analyst really can create an event (201)")
    assert call("POST", "/api/events", bearer(expired), json={"name": "x"}).status_code == 401
    ok("a write with an expired token -> 401")

    # ------------------------------------------------------------ 5
    print("\n--- 5. Role and activation changes apply to the next request ---")
    cur.execute("UPDATE users SET role = 'viewer' WHERE username = 'analyst_a'")
    assert call("POST", "/api/events", bearer(tokens["analyst_a"]), json={"name": "x"}).status_code == 403
    assert call("GET", "/api/events", bearer(tokens["analyst_a"])).status_code == 200
    ok("an analyst demoted to viewer: writes -> 403 at once, reading still works (same token)")
    cur.execute("UPDATE users SET role = 'analyst', is_active = false WHERE username = 'analyst_a'")
    assert call("GET", "/api/events", bearer(tokens["analyst_a"])).status_code == 401
    assert call("POST", "/api/events", bearer(tokens["analyst_a"]), json={"name": "x"}).status_code == 401
    ok("a disabled user: reading and writing -> 401 at once")
    cur.execute("UPDATE users SET is_active = true WHERE username = 'analyst_a'")
    assert call("POST", "/api/events", bearer(tokens["analyst_a"]), json={"name": "Back again"}).status_code == 201
    ok("re-enabled: the same token works again")

    # ------------------------------------------------------------ 6
    print("\n--- 6. PUBLIC_READ on: anyone may read, nobody may write without rights ---")
    policy(open_)
    for url in READS:
        assert call("GET", url).status_code == 200, url
    for url in READS_NOT_FOUND:
        assert call("GET", url).status_code == 404, url
    ok("every read endpoint works without a token")
    assert call("GET", "/api/events", bearer("garbage")).status_code == 200
    ok("on a public read a bad token is simply ignored")
    for method, url, kwargs, _ in WRITES:
        assert call(method, url, **kwargs).status_code == 401, url
        assert call(method, url, bearer(tokens["viewer_a"]), **kwargs).status_code == 403, url
    assert call("POST", "/api/events", bearer(tokens["admin_a"]), json={"name": "Admin event"}).status_code == 201
    ok("writes are unchanged: anonymous 401, viewer 403, admin 201")
    assert call("GET", "/api/users").status_code == 401
    ok("/api/users still needs an admin")

    # ------------------------------------------------------------ 7
    print("\n--- 7. API documentation ---")
    spec = client.get("/openapi.json").json()
    assert spec["paths"]["/api/events"]["post"].get("security")
    assert spec["paths"]["/api/analyses/{analysis_id}/impact"]["post"].get("security")
    assert not spec["paths"]["/api/health"]["get"].get("security")
    ok("data endpoints show a lock in /docs (use 'Authorize'); health does not")

    app.dependency_overrides.clear()
    engine.dispose()
    for name in BUILD_FILES:
        cur.execute((DB_DIR / name).read_text())
    conn.close()
    print("\n  Test database reset to the sample data (the test users are gone).")
    print("\n" + SEP)
    print("  Access rules tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()