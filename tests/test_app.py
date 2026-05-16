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


def test_dashboard_role_levels():
    app = build_app()
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "lin", "password": "blog123"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    assert "用户画像" in text
    assert "高级分析已保护" in text

    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "helen", "password": "blog123"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    assert "时间序列统计" in text
    assert "用户行为路径图谱" in text


def test_comment_is_encrypted_at_rest():
    app = build_app()
    client = app.test_client()
    client.get("/post/secure-content-growth")
    with client.session_transaction() as sess:
        token = sess["_csrf_token"]

    response = client.post(
        "/api/posts/1/comment",
        data={
            "author_alias": "测试者",
            "content": "这是一条用于验证加密存储的评论内容。",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200

    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT content_encrypted FROM comments ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert "验证加密存储" not in row["content_encrypted"]
