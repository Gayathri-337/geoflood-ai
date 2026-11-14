
"""
GeoFlood AI - Phase 28 test: PDF report endpoint and access rules.

DESTRUCTIVE:
Rebuilds every table in TEST_DATABASE_URL before and after the test.
Never point TEST_DATABASE_URL at your main database.

Usage (from project root):
    python -m backend.test_report_api
"""

import os

import io
from pypdf import PdfReader

import psycopg2
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai.src import config
from backend.config import Settings, get_settings
from backend.database import get_db
from backend.main import app
from backend.routers.report import collect_report_data
from backend.services import users as user_service
from backend.services.report import build_report


DB_DIR = config.ROOT / "database"
SEP = "=" * 70

BUILD_FILES = (
    "reset.sql",
    "schema.sql",
    "impact_analysis.sql",
    "sample_data.sql",
)

ROLES = {
    "viewer_x": "viewer",
    "analyst_x": "analyst",
}

PASSWORDS = {
    name: f"{name}-test-password-1"
    for name in ROLES
}

TABLES = (
    "flood_analysis",
    "flood_zones",
    "affected_roads",
    "affected_villages",
    "agricultural_areas",
    "critical_infrastructure",
    "emergency_actions",
    "flood_reports",
)


def ok(message):
    print(f"  [OK] {message}")


def scalar(cur, sql, params=None):
    cur.execute(sql, params)
    row = cur.fetchone()

    if row is None:
        raise AssertionError(f"Query returned no rows: {sql}")

    return row[0]


def rebuild_test_database(cur):
    """Rebuild the test database using the project's SQL scripts."""
    for name in BUILD_FILES:
        path = DB_DIR / name

        if not path.is_file():
            raise FileNotFoundError(f"Required SQL file not found: {path}")

        cur.execute(path.read_text(encoding="utf-8"))


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 28 PDF Report API Test")
    print(SEP)

    load_dotenv(config.ROOT / ".env")

    test_url = os.getenv("TEST_DATABASE_URL")
    main_url = os.getenv("DATABASE_URL")

    if not test_url:
        raise SystemExit("TEST_DATABASE_URL is missing from .env.")

    if not main_url:
        raise SystemExit("DATABASE_URL is missing from .env.")

    if test_url == main_url:
        raise SystemExit(
            "TEST_DATABASE_URL must differ from DATABASE_URL. "
            "This test DROPS and rebuilds tables."
        )

    try:
        conn = psycopg2.connect(test_url, connect_timeout=5)
    except psycopg2.OperationalError as err:
        raise SystemExit(f"Could not connect to the test database:\n{err}")

    conn.autocommit = True
    cur = conn.cursor()

    engine = None
    client = None

    try:
        db_name = scalar(cur, "SELECT current_database()")

        if "test" not in db_name.lower():
            raise SystemExit(
                f"Refusing to run: database '{db_name}' "
                "does not look like a test database."
            )

        print(f"\nTest database: {db_name}")

        # Rebuild only the test database.
        rebuild_test_database(cur)

        aid = scalar(
            cur,
            "SELECT analysis_id FROM flood_analysis "
            "ORDER BY analysis_id LIMIT 1",
        )

        if aid is None:
            raise AssertionError("Sample data did not create an analysis.")

        engine = create_engine(test_url, pool_pre_ping=True)
        Session = sessionmaker(bind=engine, autoflush=False)

        def use_test_db():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        # Create temporary test users.
        db = Session()

        try:
            for username, role in ROLES.items():
                user_service.create_user(
                    db,
                    username=username,
                    email=f"{username}@example.com",
                    password=PASSWORDS[username],
                    role=role,
                )

            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # Use the test database and disable public access.
        closed = Settings(public_read=False)

        app.dependency_overrides[get_db] = use_test_db
        app.dependency_overrides[get_settings] = lambda: closed

        client = TestClient(app)

        # Log in both test users.
        tokens = {}

        for name in ROLES:
            response = client.post(
                "/api/auth/login",
                data={
                    "username": name,
                    "password": PASSWORDS[name],
                },
            )

            assert response.status_code == 200, (
                f"Login failed for {name}: "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

            tokens[name] = response.json()["access_token"]

        def call(method, url, who=None, **kwargs):
            headers = {}

            if who:
                headers["Authorization"] = f"Bearer {tokens[who]}"

            return client.request(
                method,
                url,
                headers=headers,
                **kwargs,
            )

        def row_counts():
            return {
                table: scalar(cur, f"SELECT count(*) FROM {table}")
                for table in TABLES
            }

        url = f"/api/analyses/{aid}/report.pdf"

        # ------------------------------------------------------------
        # 1. Who may download?
        # ------------------------------------------------------------
        print("\n--- 1. Who may download ---")

        response = call("GET", url)

        assert response.status_code == 401, (
            "Unauthenticated report request should return HTTP 401. "
            f"Received HTTP {response.status_code}. "
            f"Response: {response.text[:500]}"
        )

        response = call("GET", url, "viewer_x")

        assert response.status_code == 200, (
            f"Viewer report request failed: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

        assert response.headers["content-type"] == "application/pdf"

        assert response.headers["content-disposition"] == (
            f'attachment; filename="geoflood_analysis_{aid}_report.pdf"'
        )

        assert response.headers["cache-control"] == "no-store"
        assert response.content.startswith(b"%PDF-")
        assert len(response.content) > 20_000

        response = call("GET", url, "analyst_x")

        assert response.status_code == 200, (
            f"Analyst report request failed: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

        ok(
            "No login -> 401; viewer and analyst can download "
            "the PDF without caching."
        )

        # ------------------------------------------------------------
        # 2. Invalid requests
        # ------------------------------------------------------------
        print("\n--- 2. Wrong requests ---")

        response = call(
            "GET",
            f"/api/analyses/{aid + 1000}/report.pdf",
            "viewer_x",
        )
        assert response.status_code == 404, response.text

        response = call(
            "GET",
            "/api/analyses/0/report.pdf",
            "viewer_x",
        )
        assert response.status_code == 422, response.text

        response = call(
            "GET",
            "/api/analyses/abc/report.pdf",
            "viewer_x",
        )
        assert response.status_code == 422, response.text

        response = call("POST", url, "analyst_x")
        assert response.status_code == 405, response.text

        ok(
            "Unknown analysis -> 404; invalid IDs -> 422; "
            "POST -> 405."
        )

        # ------------------------------------------------------------
        # 3. Downloading must not change database records
        # ------------------------------------------------------------
        print("\n--- 3. Downloading changes nothing ---")

        before = row_counts()

        call("GET", url, "viewer_x")
        call("GET", url, "viewer_x")

        after = row_counts()

        assert after == before, (
            f"Database row counts changed during PDF downloads. "
            f"Before: {before}; After: {after}"
        )

        ok(
            "PDF downloads did not add, modify, or remove rows in "
            + ", ".join(TABLES)
        )

        # ------------------------------------------------------------
        # 4. Report contents before and after impact calculation
        # ------------------------------------------------------------
        print("\n--- 4. What the report is made from ---")

        db = Session()

        try:
            data = collect_report_data(
                db,
                aid,
                generated_by="viewer_x",
            )

            assert data["analysis"]["analysis_id"] == aid
            assert data["event"]["name"]

            assert data["zones"]["type"] == "FeatureCollection"

            assert (
                len(data["zones"]["features"])
                == data["analysis"]["zone_count"]
            )

            assert data["impact"]["summary"]["last_computed_at"] is None
            assert data["impact"]["layers"] is None
            assert data["severity"]["impact_included"] is False

            pdf = build_report(data, compress=False)

            reader = PdfReader(io.BytesIO(pdf))
            pdf_text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

            assert (
                "Impact has not been computed for this analysis"
                in pdf_text
            )
            assert "viewer_x" in pdf_text

        finally:
            db.close()

        ok(
            "Before impact calculation, the report explains that "
            "impact has not been computed instead of showing zeros."
        )

        # Calculate impact as analyst.
        response = call(
            "POST",
            f"/api/analyses/{aid}/impact",
            "analyst_x",
        )

        assert response.status_code == 200, (
            f"Impact calculation failed: "
            f"HTTP {response.status_code}: {response.text[:500]}"
        )

        db = Session()

        try:
            data = collect_report_data(db, aid)

            assert data["impact"]["summary"]["last_computed_at"] is not None

            assert set(data["impact"]["layers"]) == {
                "villages",
                "roads",
                "farmland",
                "infrastructure",
            }

            assert data["severity"]["impact_included"] is True

            pdf = build_report(data, compress=False)

            reader = PdfReader(io.BytesIO(pdf))
            pdf_text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

            assert (
                "Impact has not been computed for this analysis"
                not in pdf_text
            )

            assert "Flooded roads (bridges excluded)" in pdf_text
            assert "Bridges over the detected water" in pdf_text

            response = call("GET", url, "viewer_x")

            assert response.status_code == 200, (
                f"PDF download after impact calculation failed: "
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

            assert response.content.startswith(b"%PDF-")

        finally:
            db.close()

        ok(
            "After impact calculation, the report includes impact "
            "figures and lists bridges separately from flooded roads."
        )

        # ------------------------------------------------------------
        # 5. Emergency actions belonging to the event
        # ------------------------------------------------------------
        print("\n--- 5. The event's actions ---")

        names = [
            action["title"]
            for action in data["actions"]
        ]

        action_count = scalar(
            cur,
            """
            SELECT count(*)
            FROM emergency_actions
            WHERE event_id = %s
            """,
            (data["analysis"]["event_id"],),
        )

        assert len(names) == action_count, (
            f"Report action count ({len(names)}) does not match "
            f"database action count ({action_count})."
        )

        assert names, (
            "The sample event should contain emergency actions, "
            "and the report should list them."
        )

        reader = PdfReader(io.BytesIO(pdf))
        pdf_text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )
        assert "7. Emergency response actions of this event" in pdf_text

        ok(
            f"The report lists all {len(names)} emergency action(s) "
            "belonging to the analysis event."
        )

    finally:
        # Always remove dependency overrides and close resources.
        app.dependency_overrides.clear()

        if client is not None:
            client.close()

        if engine is not None:
            engine.dispose()

        # Restore sample data in the TEST database.
        # This does not touch DATABASE_URL.
        try:
            rebuild_test_database(cur)
            print(
                "\n  Test database reset to sample data "
                "(temporary test users removed)."
            )
        finally:
            cur.close()
            conn.close()

    print("\n" + SEP)
    print("  PDF report API tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
