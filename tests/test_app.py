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
    assert "当前为匿名访客" in response.get_data(as_text=True)
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

    index_response = client.get("/")
    index_html = index_response.get_data(as_text=True)
    assert index_response.status_code == 200
    assert "avg_dwell" not in index_html
    assert "persona_segment" not in index_html
    assert "journey-list" not in index_html
    assert "timeline-chart" not in index_html
    assert "session snapshots" not in index_html.lower()

    post_response = client.get("/post/secure-content-growth")
    post_html = post_response.get_data(as_text=True)
    assert post_response.status_code == 200
    assert 'data-metric="views"' in post_html
    assert 'data-metric="likes"' in post_html
    assert 'data-metric="shares"' in post_html
    assert 'data-metric="comments"' in post_html
    assert 'data-metric="avg_dwell"' not in post_html
    assert "平均停留" not in post_html
    assert "persona_segment" not in post_html
    assert "journey-list" not in post_html
    assert "timeline-chart" not in post_html


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
        assert standard_dashboard["premium"] is None
        assert {
            "series",
            "journeys",
            "anonymous_journeys",
            "authenticated_journeys",
            "snapshots",
        }.issubset(premium_dashboard["premium"])


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
