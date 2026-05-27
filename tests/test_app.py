from pathlib import Path
import sys

from werkzeug.security import check_password_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from blog_analytics import create_app
from blog_analytics.db import get_db


def build_app():
    return create_app(
        {
            "TESTING": True,
            "DATABASE": ":memory:",
            "ENCRYPTION_KEY_FILE": "memory-test.key",
            "SESSION_COOKIE_SECURE": False,
        }
    )


def get_csrf_token(client, slug="secure-content-growth"):
    response = client.get(f"/post/{slug}")
    assert response.status_code == 200
    with client.session_transaction() as sess:
        return sess["_csrf_token"]


def get_metrics(app, post_id=1):
    with app.app_context():
        return app.extensions["analytics_service"].get_post_metrics(post_id)


def login_visitor(client, username="visitor1", password="visit123"):
    response = client.get("/visitor/login")
    assert response.status_code == 200
    with client.session_transaction() as sess:
        token = sess["_csrf_token"]
    return client.post(
        "/visitor/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=True,
    )


def test_post_page_uses_external_tracker_contract():
    app = build_app()
    client = app.test_client()

    response = client.get("/post/secure-content-growth")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "static/js/tracker.js" in html
    assert 'data-post-root data-post-id="1"' in html
    assert 'data-comment-form data-post-id="1"' in html
    assert 'method="post" action="/api/posts/1/comment"' in html
    assert 'name="csrf_token"' in html
    assert "window.BlogTracker.initPostPage" not in html


def test_anonymous_visitor_can_browse_and_comment_as_anonymous():
    app = build_app()
    client = app.test_client()

    response = client.get("/post/secure-content-growth")
    assert response.status_code == 200
    assert "Current visitor is anonymous" in response.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert "visitor" not in sess
        token = sess["_csrf_token"]

    comment_text = "Anonymous visitor comment is allowed."
    response = client.post(
        "/api/posts/1/comment",
        data={"author_alias": "anonymous tester", "content": comment_text},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        comment = db.execute(
            """
            SELECT visitor_id, visitor_type, author_alias, content_encrypted
            FROM comments
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert comment["visitor_id"] is None
        assert comment["visitor_type"] == "anonymous"
        assert comment["author_alias"] == "anonymous tester"
        assert comment_text not in comment["content_encrypted"]

        activity = db.execute(
            """
            SELECT visitor_id, visitor_type, details_encrypted
            FROM activity_logs
            WHERE event_type = 'comment'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert activity["visitor_id"] is None
        assert activity["visitor_type"] == "anonymous"
        details = app.extensions["encryption"].decrypt_json(activity["details_encrypted"])
        assert details["visitor_type"] == "anonymous"


def test_visitor_login_binds_comment_and_cannot_access_dashboard():
    app = build_app()
    client = app.test_client()

    response = login_visitor(client)
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["visitor"]["username"] == "visitor1"
        assert "blogger" not in sess

    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 302
    assert "/login" in dashboard_response.headers["Location"]

    token = get_csrf_token(client)
    comment_text = "Authenticated visitor comment is bound."
    response = client.post(
        "/api/posts/1/comment",
        data={"author_alias": "should be ignored", "content": comment_text},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        visitor = db.execute("SELECT id FROM visitors WHERE username = 'visitor1'").fetchone()
        comment = db.execute(
            """
            SELECT visitor_id, visitor_type, author_alias, content_encrypted
            FROM comments
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert comment["visitor_id"] == visitor["id"]
        assert comment["visitor_type"] == "authenticated"
        assert comment["author_alias"] == "visitor1"
        assert comment_text not in comment["content_encrypted"]

        activity = db.execute(
            """
            SELECT visitor_id, visitor_type, details_encrypted
            FROM activity_logs
            WHERE event_type = 'comment'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert activity["visitor_id"] == visitor["id"]
        assert activity["visitor_type"] == "authenticated"
        details = app.extensions["encryption"].decrypt_json(activity["details_encrypted"])
        assert details["visitor_type"] == "authenticated"
        assert details["visitor_id"] == visitor["id"]

        session_row = db.execute(
            """
            SELECT visitor_id, visitor_type, profile_encrypted
            FROM visitor_sessions
            WHERE visitor_type = 'authenticated'
            ORDER BY last_seen_at DESC
            LIMIT 1
            """
        ).fetchone()
        assert session_row["visitor_id"] == visitor["id"]
        assert "visitor1" not in session_row["profile_encrypted"]
        profile = app.extensions["encryption"].decrypt_json(session_row["profile_encrypted"])
        assert profile["visitor_type"] == "authenticated"
        assert profile["username"] == "visitor1"


def test_public_pages_do_not_expose_dashboard_only_analytics():
    app = build_app()
    client = app.test_client()

    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 302
    assert "/login" in dashboard_response.headers["Location"]

    index_response = client.get("/")
    index_html = index_response.get_data(as_text=True)
    assert index_response.status_code == 200
    assert "avg_dwell" not in index_html
    assert "persona_segment" not in index_html
    assert "journey-list" not in index_html
    assert "timeline-chart" not in index_html
    assert "session snapshots" not in index_html.lower()
    assert "Recent Session Snapshots" not in index_html
    assert "Visitor Type Share" not in index_html
    assert "data-visitor-type-chart" not in index_html

    post_response = client.get("/post/secure-content-growth")
    post_html = post_response.get_data(as_text=True)
    assert post_response.status_code == 200
    assert 'data-metric="views"' in post_html
    assert 'data-metric="likes"' in post_html
    assert 'data-metric="shares"' in post_html
    assert 'data-metric="comments"' in post_html
    assert 'data-metric="avg_dwell"' not in post_html
    assert "Avg. Dwell" not in post_html
    assert "persona_segment" not in post_html
    assert "journey-list" not in post_html
    assert "timeline-chart" not in post_html
    assert "Recent Session Snapshots" not in post_html
    assert "Visitor Type Share" not in post_html
    assert "data-visitor-type-chart" not in post_html

    visitor_client = app.test_client()
    visitor_response = login_visitor(visitor_client)
    visitor_html = visitor_response.get_data(as_text=True)
    assert visitor_response.status_code == 200
    assert "Recent Session Snapshots" not in visitor_html
    assert "Session 01" not in visitor_html


def test_basic_and_premium_dashboards_render_visitor_type_pie():
    app = build_app()
    client = app.test_client()

    basic_response = client.post(
        "/login",
        data={"username": "lin", "password": "blog123"},
        follow_redirects=True,
    )
    basic_html = basic_response.get_data(as_text=True)
    assert basic_response.status_code == 200
    assert "Visitor Personas" in basic_html
    assert "Visitor Type Share" in basic_html
    assert "Anonymous visitor" in basic_html
    assert "Logged-in visitor" in basic_html
    assert "data-visitor-type-chart" in basic_html
    assert "Recent Session Snapshots" not in basic_html
    assert "Session 01" not in basic_html

    client = app.test_client()
    premium_response = client.post(
        "/login",
        data={"username": "helen", "password": "blog123"},
        follow_redirects=True,
    )
    premium_html = premium_response.get_data(as_text=True)
    assert premium_response.status_code == 200
    assert "Visitor Personas" in premium_html
    assert "Visitor Type Share" in premium_html
    assert "Anonymous visitor" in premium_html
    assert "Logged-in visitor" in premium_html
    assert "data-visitor-type-chart" in premium_html
    assert "Recent Session Snapshots" in premium_html
    assert "Session 01" in premium_html
    assert "Visitor Type" in premium_html
    assert "Device" in premium_html
    assert "Region" in premium_html
    assert "Touchpoints" in premium_html

    with app.app_context():
        db = get_db()
        helen = db.execute("SELECT id FROM bloggers WHERE username = 'helen'").fetchone()
        raw_tokens = db.execute(
            """
            SELECT DISTINCT session_token
            FROM activity_logs
            WHERE blogger_id = ?
            LIMIT 6
            """,
            (helen["id"],),
        ).fetchall()
    for row in raw_tokens:
        assert row["session_token"] not in premium_html
        assert f"#{row['session_token'][-8:]}" not in premium_html


def test_like_share_comment_and_dwell_posts_succeed_with_csrf():
    app = build_app()
    client = app.test_client()
    token = get_csrf_token(client)

    before = get_metrics(app)
    response = client.post("/api/posts/1/like", headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    assert response.get_json()["metrics"]["likes"] == before["likes"] + 1

    before = get_metrics(app)
    response = client.post(
        "/api/posts/1/share",
        headers={"X-CSRF-Token": token, "X-Share-Channel": "manual-channel"},
    )
    assert response.status_code == 200
    assert response.get_json()["metrics"]["shares"] == before["shares"] + 1

    comment_text = "This comment proves encrypted storage."
    before = get_metrics(app)
    response = client.post(
        "/api/posts/1/comment",
        data={"author_alias": "tester", "content": comment_text},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    assert response.get_json()["metrics"]["comments"] == before["comments"] + 1

    before = get_metrics(app)
    response = client.post(
        "/api/track/dwell",
        data={"post_id": "1", "seconds": "9", "csrf_token": token},
    )
    assert response.status_code == 200
    assert response.get_json()["metrics"]["total_dwell"] == before["total_dwell"] + 9

    with app.app_context():
        db = get_db()
        comment = db.execute(
            """
            SELECT visitor_id, visitor_type, content_encrypted
            FROM comments
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert comment is not None
        assert comment["visitor_id"] is None
        assert comment["visitor_type"] == "anonymous"
        assert comment_text not in comment["content_encrypted"]

        share = db.execute(
            """
            SELECT details_encrypted
            FROM activity_logs
            WHERE event_type = 'share'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert share is not None
        assert "manual-channel" not in share["details_encrypted"]
        details = app.extensions["encryption"].decrypt_json(share["details_encrypted"])
        assert details["channel"] == "manual-channel"
        assert details["visitor_type"] == "anonymous"

        dwell = db.execute(
            """
            SELECT dwell_seconds, details_encrypted
            FROM activity_logs
            WHERE event_type = 'dwell_time'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert dwell["dwell_seconds"] == 9
        dwell_details = app.extensions["encryption"].decrypt_json(dwell["details_encrypted"])
        assert dwell_details["seconds"] == 9


def test_dynamic_posts_reject_missing_csrf():
    app = build_app()
    client = app.test_client()
    client.get("/post/secure-content-growth")

    requests = [
        client.post("/api/posts/1/like"),
        client.post("/api/posts/1/share"),
        client.post(
            "/api/posts/1/comment",
            data={"author_alias": "tester", "content": "Missing CSRF should fail."},
        ),
        client.post("/api/track/dwell", data={"post_id": "1", "seconds": "5"}),
    ]

    assert [response.status_code for response in requests] == [400, 400, 400, 400]


def test_dashboard_login_role_levels_are_server_side():
    app = build_app()
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "lin", "password": "blog123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Secure Blog Analytics" in response.data
    with client.session_transaction() as sess:
        assert sess["blogger"]["role"] == "standard"

    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "helen", "password": "blog123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Secure Blog Analytics" in response.data
    with client.session_transaction() as sess:
        assert sess["blogger"]["role"] == "premium"

    with app.app_context():
        service = app.extensions["analytics_service"]
        lin = service.authenticate("lin", "blog123")
        helen = service.authenticate("helen", "blog123")

        standard_dashboard = service.build_dashboard(lin["id"], lin["role"])
        premium_dashboard = service.build_dashboard(helen["id"], helen["role"])

        assert "avg_dwell" in standard_dashboard["metrics"]
        assert "avg_dwell" in premium_dashboard["metrics"]
        assert standard_dashboard["visitor_summary"]["anonymous_sessions"] >= 0
        assert standard_dashboard["visitor_summary"]["logged_in_activity"] >= 0
        for payload in (standard_dashboard, premium_dashboard):
            breakdown = payload["visitor_type_breakdown"]
            assert breakdown["anonymous_count"] == payload["visitor_summary"]["anonymous_sessions"]
            assert breakdown["authenticated_count"] == payload["visitor_summary"]["logged_in_visitors"]
            assert breakdown["total_count"] == (
                breakdown["anonymous_count"] + breakdown["authenticated_count"]
            )
            assert breakdown["anonymous_ratio"] >= 0
            assert breakdown["authenticated_ratio"] >= 0
        assert standard_dashboard["premium"] is None
        snapshots = premium_dashboard["premium"]["snapshots"]
        assert snapshots
        assert snapshots[0]["display_label"] == "Session 01"
        assert snapshots[0]["visitor_label"] in {"Anonymous visitor", "Logged-in visitor"}
        assert "persona_label" in snapshots[0]
        assert "device_label" in snapshots[0]
        assert "region_label" in snapshots[0]
        assert "touch_count" in snapshots[0]
        assert "token" not in snapshots[0]
        assert {
            "series",
            "journeys",
            "anonymous_journeys",
            "authenticated_journeys",
            "snapshots",
        }.issubset(premium_dashboard["premium"])


def test_dashboard_persona_distribution_includes_authenticated_page_views():
    app = build_app()
    anonymous_client = app.test_client()
    visitor_client = app.test_client()

    anonymous_response = anonymous_client.get("/post/secure-content-growth")
    assert anonymous_response.status_code == 200

    visitor_response = login_visitor(visitor_client)
    assert visitor_response.status_code == 200
    authenticated_response = visitor_client.get("/post/secure-content-growth")
    assert authenticated_response.status_code == 200

    with app.app_context():
        service = app.extensions["analytics_service"]
        lin = service.authenticate("lin", "blog123")
        dashboard = service.build_dashboard(lin["id"], lin["role"])
        persona_count = sum(item["count"] for item in dashboard["personas"])

        db = get_db()
        all_page_views = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM activity_logs a
            JOIN visitor_sessions s ON s.session_token = a.session_token
            WHERE a.blogger_id = ?
              AND a.event_type = 'page_view'
            """,
            (lin["id"],),
        ).fetchone()["count"]
        anonymous_page_views = db.execute(
            """
            SELECT COUNT(*) AS count
            FROM activity_logs a
            JOIN visitor_sessions s ON s.session_token = a.session_token
            WHERE a.blogger_id = ?
              AND a.event_type = 'page_view'
              AND COALESCE(a.visitor_type, s.visitor_type, 'anonymous') = 'anonymous'
            """,
            (lin["id"],),
        ).fetchone()["count"]

        assert all_page_views > anonymous_page_views
        assert persona_count == all_page_views


def test_passwords_and_visitor_profiles_remain_protected():
    app = build_app()
    client = app.test_client()
    get_csrf_token(client)

    with app.app_context():
        db = get_db()
        blogger = db.execute(
            "SELECT password_hash FROM bloggers WHERE username = 'lin'"
        ).fetchone()
        assert blogger["password_hash"] != "blog123"
        assert check_password_hash(blogger["password_hash"], "blog123")

        visitor_account = db.execute(
            "SELECT password_hash FROM visitors WHERE username = 'visitor1'"
        ).fetchone()
        assert visitor_account["password_hash"] != "visit123"
        assert check_password_hash(visitor_account["password_hash"], "visit123")

        visitor = db.execute(
            """
            SELECT visitor_type, profile_encrypted
            FROM visitor_sessions
            ORDER BY last_seen_at DESC
            LIMIT 1
            """
        ).fetchone()
        assert visitor is not None
        assert visitor["visitor_type"] == "anonymous"
        assert "user_agent" not in visitor["profile_encrypted"]
        profile = app.extensions["encryption"].decrypt_json(visitor["profile_encrypted"])
        assert "user_agent" in profile
        assert profile["visitor_type"] == "anonymous"
