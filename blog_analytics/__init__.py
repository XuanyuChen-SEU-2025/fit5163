from __future__ import annotations

from functools import wraps
from pathlib import Path
import sqlite3

from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .config import Config
from .db import close_db, init_db
from .security import EncryptionService, get_csrf_token, validate_csrf_token
from .services import BlogAnalyticsService


def create_app(test_config: dict | None = None) -> Flask:
    template_folder = str(Path(__file__).resolve().parent.parent / "templates")
    static_folder = str(Path(__file__).resolve().parent.parent / "static")
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    if app.config["DATABASE"] == ":memory:":
        shared_db = sqlite3.connect(
            ":memory:",
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        shared_db.row_factory = sqlite3.Row
        app.extensions["shared_db"] = shared_db

    encryption = EncryptionService(app.config["ENCRYPTION_KEY_FILE"])
    service = BlogAnalyticsService(encryption)

    app.extensions["encryption"] = encryption
    app.extensions["analytics_service"] = service

    with app.app_context():
        init_db()
        service.seed_demo_data()

    app.teardown_appcontext(close_db)

    def login_required(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "blogger" not in session:
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped_view

    def csrf_protected(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not validate_csrf_token(token):
                abort(400, "无效的 CSRF token")
            return view(*args, **kwargs)

        return wrapped_view

    @app.context_processor
    def inject_globals():
        return {
            "csrf_token": get_csrf_token(),
            "current_blogger": session.get("blogger"),
        }

    @app.after_request
    def apply_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "font-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.get("/")
    def index():
        service.record_home_view()
        posts = service.list_posts()
        return render_template("index.html", posts=posts)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            blogger = service.authenticate(username, password)
            if not blogger:
                flash("用户名或密码错误，请使用演示账号登录。", "error")
            else:
                session["blogger"] = blogger
                flash(f"欢迎回来，{blogger['display_name']}。", "success")
                return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.post("/logout")
    @csrf_protected
    def logout():
        session.pop("blogger", None)
        flash("你已安全退出。", "success")
        return redirect(url_for("index"))

    @app.get("/post/<slug>")
    def post_detail(slug: str):
        post = service.get_post_by_slug(slug)
        if not post:
            abort(404)
        service.record_post_view(post)
        refreshed = service.get_post_by_slug(slug)
        return render_template("post.html", post=refreshed)

    @app.get("/dashboard")
    @login_required
    def dashboard():
        blogger = session["blogger"]
        payload = service.build_dashboard(blogger["id"], blogger["role"])
        return render_template("dashboard.html", dashboard=payload, blogger=blogger)

    @app.post("/api/posts/<int:post_id>/like")
    @csrf_protected
    def like_post(post_id: int):
        metrics = service.add_like(post_id)
        return jsonify({"ok": True, "metrics": metrics})

    @app.post("/api/posts/<int:post_id>/share")
    @csrf_protected
    def share_post(post_id: int):
        metrics = service.add_share(post_id)
        return jsonify({"ok": True, "metrics": metrics})

    @app.post("/api/posts/<int:post_id>/comment")
    @csrf_protected
    def comment_post(post_id: int):
        author_alias = request.form.get("author_alias", "匿名访客").strip() or "匿名访客"
        content = request.form.get("content", "").strip()
        if len(content) < 4:
            return jsonify({"ok": False, "error": "评论至少需要 4 个字符。"}), 400
        metrics = service.add_comment(post_id, author_alias[:20], content[:240])
        return jsonify({"ok": True, "metrics": metrics})

    @app.post("/api/track/dwell")
    @csrf_protected
    def track_dwell():
        post_id = int(request.form.get("post_id", 0))
        seconds = max(0, min(int(request.form.get("seconds", 0)), 3600))
        if not post_id:
            return jsonify({"ok": False, "error": "缺少文章编号。"}), 400
        metrics = service.record_dwell_time(post_id, seconds)
        return jsonify({"ok": True, "metrics": metrics})

    return app
