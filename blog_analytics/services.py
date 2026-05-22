from __future__ import annotations

import hashlib
import random
import secrets
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import has_request_context, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

PERSONA_SEGMENTS = ["Content Entrepreneurs", "Students", "Developers", "Product Managers", "Freelance Writers"]
REGIONS = ["Shanghai", "Beijing", "Shenzhen", "Hangzhou", "Chengdu", "Singapore", "Sydney"]
COMMENT_SNIPPETS = [
    "The security design in this article is very clear.",
    "The dashboard's tiered view works well for team collaboration.",
    "Could you add another dimension for visitor sources?",
    "I like how the journey path and time series are shown together.",
]
EVENT_LABELS = {
    "home_view": "Home",
    "page_view": "Article View",
    "like": "Like",
    "comment": "Comment",
    "share": "Share",
    "dwell_time": "Dwell",
}


def utcnow() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def to_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


class BlogAnalyticsService:
    def __init__(self, encryption_service) -> None:
        self.encryption = encryption_service

    def seed_demo_data(self) -> None:
        db = get_db()
        self._seed_demo_visitors(db)
        exists = db.execute("SELECT COUNT(*) AS count FROM bloggers").fetchone()["count"]
        if exists:
            db.commit()
            return

        created_at = utcnow()
        bloggers = [
            (
                "lin",
                generate_password_hash("blog123"),
                "Lin Lan",
                "standard",
                "专注内容增长与基础运营复盘。",
                created_at,
            ),
            (
                "helen",
                generate_password_hash("blog123"),
                "Helen He",
                "premium",
                "关注安全、增长与高阶分析实践。",
                created_at,
            ),
        ]
        db.executemany(
            """
            INSERT INTO bloggers (username, password_hash, display_name, role, bio, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            bloggers,
        )
        blogger_rows = db.execute(
            "SELECT id, username, display_name, role FROM bloggers ORDER BY id"
        ).fetchall()
        blogger_map = {row["username"]: row for row in blogger_rows}

        posts = [
            (
                blogger_map["lin"]["id"],
                "secure-content-growth",
                "Three-Layer Funnel for Secure Content Growth",
                "Unify visits, engagement, and conversion into one trackable blog growth model.",
                (
                    "We split blog activity into homepage reach, article consumption, and interaction conversion, "
                    "then use secure tracking to store views, dwell time, and interaction events together."
                ),
                created_at,
            ),
            (
                blogger_map["lin"]["id"],
                "basic-metrics-playbook",
                "How Basic Metrics Dashboards Help Basic Bloggers",
                "Total views, likes, and persona tags do more than display data; they shape the review rhythm.",
                (
                    "For Basic Bloggers, focusing on frequent core metrics makes it easier to see which content deserves continued investment "
                    "without getting lost in complex charts."
                ),
                created_at,
            ),
            (
                blogger_map["helen"]["id"],
                "zero-trust-analytics",
                "A Content Analytics Platform Built on Zero Trust",
                "Design a user behavior analytics system with minimal exposure from transport to storage.",
                (
                    "Advanced analytics does not have to sacrifice privacy. We can encrypt sensitive details at rest "
                    "while preserving interpretability for time series and behavior paths."
                ),
                created_at,
            ),
            (
                blogger_map["helen"]["id"],
                "journey-mapping-for-bloggers",
                "User Journey Mapping for Bloggers",
                "From homepage entry to shared reach, journey maps help Premium Bloggers identify key behavior nodes.",
                (
                    "When we know where users come from, which articles they spend more time on, "
                    "and where they like or comment, operations can become much more precise."
                ),
                created_at,
            ),
        ]
        db.executemany(
            """
            INSERT INTO posts (blogger_id, slug, title, excerpt, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            posts,
        )
        post_rows = db.execute(
            "SELECT id, blogger_id, slug, title FROM posts ORDER BY id"
        ).fetchall()

        rnd = random.Random(5163)
        base_date = datetime.utcnow() - timedelta(days=9)
        for day_offset in range(10):
            day = base_date + timedelta(days=day_offset)
            for index in range(rnd.randint(7, 11)):
                post = rnd.choice(post_rows)
                session_token = f"seed-{day_offset}-{index}-{post['id']}"
                profile = self._build_profile(session_token, "SeedAgent/1.0", "zh-CN", "seed")
                timestamp = day + timedelta(hours=rnd.randint(8, 22), minutes=rnd.randint(0, 55))
                self._upsert_visitor_session(db, session_token, profile, to_iso(timestamp))

                self._insert_activity(
                    db,
                    blogger_id=post["blogger_id"],
                    post_id=post["id"],
                    session_token=session_token,
                    event_type="home_view",
                    path="/",
                    dwell_seconds=0,
                    details={
                        "journey_step": "Home",
                        "source": "seed",
                    },
                    occurred_at=to_iso(timestamp),
                )

                view_time = timestamp + timedelta(minutes=rnd.randint(1, 6))
                self._insert_activity(
                    db,
                    blogger_id=post["blogger_id"],
                    post_id=post["id"],
                    session_token=session_token,
                    event_type="page_view",
                    path=f"/post/{post['slug']}",
                    dwell_seconds=0,
                    details={
                        "journey_step": f"Read: {post['title']}",
                        "referrer": "首页推荐",
                    },
                    occurred_at=to_iso(view_time),
                )

                dwell_seconds = rnd.randint(35, 280)
                self._insert_activity(
                    db,
                    blogger_id=post["blogger_id"],
                    post_id=post["id"],
                    session_token=session_token,
                    event_type="dwell_time",
                    path=f"/post/{post['slug']}",
                    dwell_seconds=dwell_seconds,
                    details={
                        "journey_step": "Deep read",
                        "seconds": dwell_seconds,
                    },
                    occurred_at=to_iso(view_time + timedelta(minutes=1)),
                )

                if rnd.random() < 0.58:
                    self._insert_activity(
                        db,
                        blogger_id=post["blogger_id"],
                        post_id=post["id"],
                        session_token=session_token,
                        event_type="like",
                        path=f"/post/{post['slug']}",
                        dwell_seconds=0,
                        details={"journey_step": "Like"},
                        occurred_at=to_iso(view_time + timedelta(minutes=2)),
                    )

                if rnd.random() < 0.27:
                    self._insert_activity(
                        db,
                        blogger_id=post["blogger_id"],
                        post_id=post["id"],
                        session_token=session_token,
                        event_type="share",
                        path=f"/post/{post['slug']}",
                        dwell_seconds=0,
                        details={
                            "journey_step": "Share",
                            "channel": rnd.choice(["微信", "微博", "复制链接"]),
                        },
                        occurred_at=to_iso(view_time + timedelta(minutes=3)),
                    )

                if rnd.random() < 0.22:
                    author_alias = rnd.choice(["Dawn", "Kevin", "Olivia", "Mia"])
                    content = rnd.choice(COMMENT_SNIPPETS)
                    self._insert_comment(
                        db,
                        blogger_id=post["blogger_id"],
                        post_id=post["id"],
                        session_token=session_token,
                        author_alias=author_alias,
                        content=content,
                        occurred_at=to_iso(view_time + timedelta(minutes=4)),
                    )
                    self._insert_activity(
                        db,
                        blogger_id=post["blogger_id"],
                        post_id=post["id"],
                        session_token=session_token,
                        event_type="comment",
                        path=f"/post/{post['slug']}",
                        dwell_seconds=0,
                        details={"journey_step": "Comment"},
                        occurred_at=to_iso(view_time + timedelta(minutes=4)),
                    )

        db.commit()

    def _seed_demo_visitors(self, db) -> None:
        created_at = utcnow()
        visitors = [
            (
                "visitor1",
                "visitor1@example.test",
                generate_password_hash("visit123"),
                "visitor1",
                created_at,
            ),
            (
                "visitor2",
                "visitor2@example.test",
                generate_password_hash("visit123"),
                "visitor2",
                created_at,
            ),
        ]
        db.executemany(
            """
            INSERT OR IGNORE INTO visitors (
                username, email, password_hash, display_name, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            visitors,
        )

    def list_posts(self) -> list[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT
                p.id,
                p.slug,
                p.title,
                p.excerpt,
                p.content,
                p.created_at,
                b.display_name,
                b.role,
                (
                    SELECT COUNT(*)
                    FROM activity_logs a
                    WHERE a.post_id = p.id AND a.event_type = 'page_view'
                ) AS views,
                (
                    SELECT COUNT(*)
                    FROM activity_logs a
                    WHERE a.post_id = p.id AND a.event_type = 'like'
                ) AS likes,
                (
                    SELECT COUNT(*)
                    FROM activity_logs a
                    WHERE a.post_id = p.id AND a.event_type = 'share'
                ) AS shares,
                (
                    SELECT COUNT(*)
                    FROM comments c
                    WHERE c.post_id = p.id
                ) AS comments
            FROM posts p
            JOIN bloggers b ON b.id = p.blogger_id
            ORDER BY p.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_post_by_slug(self, slug: str) -> dict | None:
        db = get_db()
        row = db.execute(
            """
            SELECT p.*, b.display_name, b.role
            FROM posts p
            JOIN bloggers b ON b.id = p.blogger_id
            WHERE p.slug = ?
            """,
            (slug,),
        ).fetchone()
        if not row:
            return None
        post = dict(row)
        post["metrics"] = self.get_post_metrics(post["id"])
        post["comments"] = self.get_comments(post["id"])
        return post

    def get_post_metrics(self, post_id: int) -> dict:
        db = get_db()
        row = db.execute(
            """
            SELECT
                SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS views,
                SUM(CASE WHEN event_type = 'like' THEN 1 ELSE 0 END) AS likes,
                SUM(CASE WHEN event_type = 'share' THEN 1 ELSE 0 END) AS shares,
                SUM(CASE WHEN event_type = 'dwell_time' THEN dwell_seconds ELSE 0 END) AS total_dwell,
                AVG(CASE WHEN event_type = 'dwell_time' THEN dwell_seconds END) AS avg_dwell
            FROM activity_logs
            WHERE post_id = ?
            """,
            (post_id,),
        ).fetchone()
        comment_count = db.execute(
            "SELECT COUNT(*) AS count FROM comments WHERE post_id = ?",
            (post_id,),
        ).fetchone()["count"]
        return {
            "views": row["views"] or 0,
            "likes": row["likes"] or 0,
            "shares": row["shares"] or 0,
            "comments": comment_count,
            "avg_dwell": round(row["avg_dwell"] or 0, 1),
            "total_dwell": row["total_dwell"] or 0,
        }

    def get_comments(self, post_id: int) -> list[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT author_alias, content_encrypted, created_at, visitor_type
            FROM comments
            WHERE post_id = ?
            ORDER BY created_at DESC
            LIMIT 6
            """,
            (post_id,),
        ).fetchall()
        comments = []
        for row in rows:
            comments.append(
                {
                    "author_alias": row["author_alias"],
                    "content": self.encryption.decrypt_text(row["content_encrypted"]),
                    "created_at": row["created_at"],
                    "visitor_type": row["visitor_type"],
                }
            )
        return comments

    def authenticate(self, username: str, password: str) -> dict | None:
        db = get_db()
        row = db.execute(
            """
            SELECT id, username, display_name, password_hash, role, bio
            FROM bloggers
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if not row:
            return None
        if not check_password_hash(row["password_hash"], password):
            return None
        blogger = dict(row)
        blogger.pop("password_hash", None)
        return blogger

    def authenticate_visitor(self, username: str, password: str) -> dict | None:
        db = get_db()
        row = db.execute(
            """
            SELECT id, username, email, display_name, password_hash
            FROM visitors
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if not row:
            return None
        if not check_password_hash(row["password_hash"], password):
            return None
        visitor = dict(row)
        visitor.pop("password_hash", None)
        return visitor

    def ensure_visitor_session(self) -> dict:
        db = get_db()
        visitor_account = self._visitor_account_from_session()
        visitor_id = visitor_account["id"] if visitor_account else None
        visitor_type = "authenticated" if visitor_account else "anonymous"
        session_token = session.get("visitor_token")
        now = utcnow()
        if not session_token:
            session_token = f"vis-{secrets.token_urlsafe(18)}"
            session["visitor_token"] = session_token

        row = db.execute(
            """
            SELECT
                session_token,
                visitor_id,
                visitor_type,
                persona_segment,
                device_type,
                region,
                profile_encrypted
            FROM visitor_sessions
            WHERE session_token = ?
            """,
            (session_token,),
        ).fetchone()
        if row:
            row_visitor_id = row["visitor_id"] if row["visitor_id"] is not None else None
            if row_visitor_id != visitor_id or row["visitor_type"] != visitor_type:
                session_token = f"vis-{secrets.token_urlsafe(18)}"
                session["visitor_token"] = session_token
                row = None

        if row:
            db.execute(
                "UPDATE visitor_sessions SET last_seen_at = ? WHERE session_token = ?",
                (now, session_token),
            )
            db.commit()
            visitor = dict(row)
            if visitor_account:
                visitor.update(
                    {
                        "username": visitor_account["username"],
                        "display_name": visitor_account["display_name"],
                        "email": visitor_account.get("email"),
                    }
                )
            return visitor

        profile = self._build_profile(
            session_token,
            request.headers.get("User-Agent", "Unknown"),
            request.headers.get("Accept-Language", "Unknown"),
            request.referrer or "直接访问",
            visitor_account=visitor_account,
        )
        self._upsert_visitor_session(
            db,
            session_token,
            profile,
            now,
            visitor_id=visitor_id,
            visitor_type=visitor_type,
        )
        db.commit()
        visitor = {
            "session_token": session_token,
            "visitor_id": visitor_id,
            "visitor_type": visitor_type,
            "persona_segment": profile["persona_segment"],
            "device_type": profile["device_type"],
            "region": profile["region"],
            "profile_encrypted": self.encryption.encrypt_json(profile),
        }
        if visitor_account:
            visitor.update(
                {
                    "username": visitor_account["username"],
                    "display_name": visitor_account["display_name"],
                    "email": visitor_account.get("email"),
                }
            )
        return visitor

    def record_home_view(self) -> None:
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=None,
            post_id=None,
            session_token=visitor["session_token"],
            visitor_id=visitor["visitor_id"],
            visitor_type=visitor["visitor_type"],
            event_type="home_view",
            path="/",
            dwell_seconds=0,
            details=self._with_visitor_details({
                "journey_step": "Home",
                "surface": "frontpage",
            }, visitor),
        )

    def record_post_view(self, post: dict) -> None:
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=post["blogger_id"],
            post_id=post["id"],
            session_token=visitor["session_token"],
            visitor_id=visitor["visitor_id"],
            visitor_type=visitor["visitor_type"],
            event_type="page_view",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details=self._with_visitor_details({
                "journey_step": f"Read: {post['title']}",
                "post_title": post["title"],
                "referrer": request.referrer or "直接访问",
            }, visitor),
        )

    def record_dwell_time(self, post_id: int, seconds: int) -> dict:
        post = self.get_post_by_id(post_id)
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=post["blogger_id"],
            post_id=post["id"],
            session_token=visitor["session_token"],
            visitor_id=visitor["visitor_id"],
            visitor_type=visitor["visitor_type"],
            event_type="dwell_time",
            path=f"/post/{post['slug']}",
            dwell_seconds=seconds,
            details=self._with_visitor_details({
                "journey_step": "Deep read",
                "seconds": seconds,
            }, visitor),
        )
        return self.get_post_metrics(post_id)

    def add_like(self, post_id: int) -> dict:
        post = self.get_post_by_id(post_id)
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=post["blogger_id"],
            post_id=post_id,
            session_token=visitor["session_token"],
            visitor_id=visitor["visitor_id"],
            visitor_type=visitor["visitor_type"],
            event_type="like",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details=self._with_visitor_details({"journey_step": "Like"}, visitor),
        )
        return self.get_post_metrics(post_id)

    def add_share(self, post_id: int) -> dict:
        post = self.get_post_by_id(post_id)
        visitor = self.ensure_visitor_session()
        channel = request.headers.get("X-Share-Channel", "复制链接")
        self._log_activity(
            blogger_id=post["blogger_id"],
            post_id=post_id,
            session_token=visitor["session_token"],
            visitor_id=visitor["visitor_id"],
            visitor_type=visitor["visitor_type"],
            event_type="share",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details=self._with_visitor_details({
                "journey_step": "Share",
                "channel": channel,
            }, visitor),
        )
        return self.get_post_metrics(post_id)

    def add_comment(self, post_id: int, author_alias: str, content: str) -> dict:
        post = self.get_post_by_id(post_id)
        visitor = self.ensure_visitor_session()
        display_alias = author_alias
        if visitor["visitor_type"] == "authenticated":
            display_alias = visitor.get("display_name") or visitor.get("username") or author_alias
        created_at = utcnow()
        db = get_db()
        self._insert_comment(
            db,
            blogger_id=post["blogger_id"],
            post_id=post_id,
            session_token=visitor["session_token"],
            visitor_id=visitor["visitor_id"],
            visitor_type=visitor["visitor_type"],
            author_alias=display_alias,
            content=content,
            occurred_at=created_at,
        )
        self._insert_activity(
            db,
            blogger_id=post["blogger_id"],
            post_id=post_id,
            session_token=visitor["session_token"],
            visitor_id=visitor["visitor_id"],
            visitor_type=visitor["visitor_type"],
            event_type="comment",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details=self._with_visitor_details({
                "journey_step": "Comment",
                "author_alias": display_alias,
            }, visitor),
            occurred_at=created_at,
        )
        db.commit()
        return self.get_post_metrics(post_id)

    def get_post_by_id(self, post_id: int) -> dict:
        db = get_db()
        row = db.execute(
            """
            SELECT p.*, b.display_name, b.role
            FROM posts p
            JOIN bloggers b ON b.id = p.blogger_id
            WHERE p.id = ?
            """,
            (post_id,),
        ).fetchone()
        if not row:
            raise ValueError("Post not found")
        return dict(row)

    def build_dashboard(self, blogger_id: int, role: str) -> dict:
        db = get_db()
        metrics_row = db.execute(
            """
            SELECT
                SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS views,
                SUM(CASE WHEN event_type = 'like' THEN 1 ELSE 0 END) AS likes,
                SUM(CASE WHEN event_type = 'share' THEN 1 ELSE 0 END) AS shares,
                SUM(CASE WHEN event_type = 'comment' THEN 1 ELSE 0 END) AS comments,
                AVG(CASE WHEN event_type = 'dwell_time' THEN dwell_seconds END) AS avg_dwell
            FROM activity_logs
            WHERE blogger_id = ?
            """,
            (blogger_id,),
        ).fetchone()

        persona_rows = db.execute(
            """
            SELECT s.persona_segment, COUNT(*) AS count
            FROM activity_logs a
            JOIN visitor_sessions s ON s.session_token = a.session_token
            WHERE a.blogger_id = ?
              AND a.event_type = 'page_view'
            GROUP BY s.persona_segment
            ORDER BY count DESC
            """,
            (blogger_id,),
        ).fetchall()

        visitor_summary_row = db.execute(
            """
            SELECT
                COUNT(DISTINCT CASE
                    WHEN COALESCE(a.visitor_type, s.visitor_type, 'anonymous') = 'anonymous'
                    THEN a.session_token
                END) AS anonymous_sessions,
                COUNT(DISTINCT CASE
                    WHEN COALESCE(a.visitor_type, s.visitor_type, 'anonymous') = 'authenticated'
                    THEN a.visitor_id
                END) AS logged_in_visitors,
                SUM(CASE
                    WHEN COALESCE(a.visitor_type, s.visitor_type, 'anonymous') = 'anonymous'
                    THEN 1 ELSE 0
                END) AS anonymous_activity,
                SUM(CASE
                    WHEN COALESCE(a.visitor_type, s.visitor_type, 'anonymous') = 'authenticated'
                    THEN 1 ELSE 0
                END) AS logged_in_activity
            FROM activity_logs a
            JOIN visitor_sessions s ON s.session_token = a.session_token
            WHERE a.blogger_id = ?
            """,
            (blogger_id,),
        ).fetchone()

        visitor_type_rows = db.execute(
            """
            SELECT
                COALESCE(a.visitor_type, s.visitor_type, 'anonymous') AS visitor_type,
                COUNT(*) AS activity_count,
                COUNT(DISTINCT a.session_token) AS session_count,
                COUNT(DISTINCT a.visitor_id) AS account_count
            FROM activity_logs a
            JOIN visitor_sessions s ON s.session_token = a.session_token
            WHERE a.blogger_id = ?
            GROUP BY COALESCE(a.visitor_type, s.visitor_type, 'anonymous')
            ORDER BY activity_count DESC
            """,
            (blogger_id,),
        ).fetchall()

        post_rows = db.execute(
            """
            SELECT
                p.title,
                SUM(CASE WHEN a.event_type = 'page_view' THEN 1 ELSE 0 END) AS views,
                SUM(CASE WHEN a.event_type = 'like' THEN 1 ELSE 0 END) AS likes,
                SUM(CASE WHEN a.event_type = 'share' THEN 1 ELSE 0 END) AS shares,
                SUM(CASE WHEN a.event_type = 'comment' THEN 1 ELSE 0 END) AS comments
            FROM posts p
            LEFT JOIN activity_logs a ON a.post_id = p.id
            WHERE p.blogger_id = ?
            GROUP BY p.id
            ORDER BY views DESC, likes DESC
            """,
            (blogger_id,),
        ).fetchall()

        persona_total = sum(row["count"] for row in persona_rows) or 1
        anonymous_sessions = visitor_summary_row["anonymous_sessions"] or 0
        logged_in_visitors = visitor_summary_row["logged_in_visitors"] or 0
        visitor_type_total = anonymous_sessions + logged_in_visitors
        if visitor_type_total:
            anonymous_ratio = round(anonymous_sessions / visitor_type_total * 100, 1)
            authenticated_ratio = round(logged_in_visitors / visitor_type_total * 100, 1)
            anonymous_degrees = round(anonymous_sessions / visitor_type_total * 360, 1)
        else:
            anonymous_ratio = 0
            authenticated_ratio = 0
            anonymous_degrees = 0
        dashboard = {
            "metrics": {
                "views": metrics_row["views"] or 0,
                "likes": metrics_row["likes"] or 0,
                "shares": metrics_row["shares"] or 0,
                "comments": metrics_row["comments"] or 0,
                "avg_dwell": round(metrics_row["avg_dwell"] or 0, 1),
            },
            "visitor_summary": {
                "total_visitors": anonymous_sessions + logged_in_visitors,
                "anonymous_sessions": anonymous_sessions,
                "logged_in_visitors": logged_in_visitors,
                "anonymous_activity": visitor_summary_row["anonymous_activity"] or 0,
                "logged_in_activity": visitor_summary_row["logged_in_activity"] or 0,
            },
            "visitor_type_breakdown": {
                "anonymous_count": anonymous_sessions,
                "authenticated_count": logged_in_visitors,
                "total_count": visitor_type_total,
                "anonymous_ratio": anonymous_ratio,
                "authenticated_ratio": authenticated_ratio,
                "anonymous_degrees": anonymous_degrees,
            },
            "visitor_types": [
                {
                    "label": "Logged-in visitor" if row["visitor_type"] == "authenticated" else "Anonymous visitor",
                    "visitor_type": row["visitor_type"],
                    "activity_count": row["activity_count"],
                    "session_count": row["session_count"],
                    "account_count": row["account_count"],
                }
                for row in visitor_type_rows
            ],
            "personas": [
                {
                    "label": row["persona_segment"],
                    "count": row["count"],
                    "ratio": round(row["count"] / persona_total * 100, 1),
                }
                for row in persona_rows
            ],
            "top_posts": [
                {
                    "title": row["title"],
                    "views": row["views"] or 0,
                    "likes": row["likes"] or 0,
                    "shares": row["shares"] or 0,
                    "comments": row["comments"] or 0,
                }
                for row in post_rows
            ],
            "premium": None,
        }

        if role == "premium":
            dashboard["premium"] = {
                "series": self._build_time_series(blogger_id),
                "journeys": self._build_journey_paths(blogger_id),
                "anonymous_journeys": self._build_journey_paths(blogger_id, "anonymous"),
                "authenticated_journeys": self._build_journey_paths(blogger_id, "authenticated"),
                "snapshots": self._build_session_snapshots(blogger_id),
            }
        return dashboard

    def _build_time_series(self, blogger_id: int) -> list[dict]:
        db = get_db()
        start_day = (datetime.utcnow() - timedelta(days=6)).date().isoformat()
        rows = db.execute(
            """
            SELECT
                DATE(occurred_at) AS day,
                SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS views,
                SUM(CASE WHEN event_type = 'like' THEN 1 ELSE 0 END) AS likes,
                SUM(CASE WHEN event_type = 'share' THEN 1 ELSE 0 END) AS shares,
                SUM(CASE WHEN event_type = 'comment' THEN 1 ELSE 0 END) AS comments
            FROM activity_logs
            WHERE blogger_id = ? AND DATE(occurred_at) >= ?
            GROUP BY DATE(occurred_at)
            ORDER BY DATE(occurred_at)
            """,
            (blogger_id, start_day),
        ).fetchall()
        data_map = {row["day"]: dict(row) for row in rows}
        days = []
        peak = 1
        for offset in range(7):
            day = (datetime.utcnow().date() - timedelta(days=6 - offset)).isoformat()
            entry = data_map.get(
                day,
                {"day": day, "views": 0, "likes": 0, "shares": 0, "comments": 0},
            )
            peak = max(peak, entry["views"])
            days.append(entry)
        for entry in days:
            entry["view_ratio"] = round(entry["views"] / peak * 100, 1) if peak else 0
        return days

    def _build_journey_paths(self, blogger_id: int, visitor_type: str | None = None) -> list[dict]:
        db = get_db()
        visitor_filter = ""
        params: list = [blogger_id]
        if visitor_type:
            visitor_filter = "AND COALESCE(visitor_type, 'anonymous') = ?"
            params.append(visitor_type)
        rows = db.execute(
            f"""
            SELECT session_token, event_type, details_encrypted, occurred_at
            FROM activity_logs
            WHERE blogger_id = ?
              {visitor_filter}
              AND event_type IN ('home_view', 'page_view', 'like', 'comment', 'share')
            ORDER BY session_token, occurred_at
            """,
            params,
        ).fetchall()

        sequences: defaultdict[str, list[str]] = defaultdict(list)
        for row in rows:
            details = self.encryption.decrypt_json(row["details_encrypted"])
            label = details.get("journey_step") or EVENT_LABELS.get(row["event_type"], row["event_type"])
            if not sequences[row["session_token"]] or sequences[row["session_token"]][-1] != label:
                sequences[row["session_token"]].append(label)

        transitions = Counter()
        for labels in sequences.values():
            for index in range(len(labels) - 1):
                transitions[(labels[index], labels[index + 1])] += 1

        if not transitions:
            return []

        peak = transitions.most_common(1)[0][1]
        return [
            {
                "from": pair[0],
                "to": pair[1],
                "count": count,
                "ratio": round(count / peak * 100, 1),
            }
            for pair, count in transitions.most_common(6)
        ]

    def _build_session_snapshots(self, blogger_id: int) -> list[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT
                s.session_token,
                s.visitor_type,
                s.persona_segment,
                s.device_type,
                s.region,
                MAX(a.occurred_at) AS last_touch,
                COUNT(*) AS touchpoints
            FROM activity_logs a
            JOIN visitor_sessions s ON s.session_token = a.session_token
            WHERE a.blogger_id = ?
            GROUP BY
                s.session_token,
                s.visitor_type,
                s.persona_segment,
                s.device_type,
                s.region
            ORDER BY last_touch DESC
            LIMIT 6
            """,
            (blogger_id,),
        ).fetchall()
        snapshots = []
        for index, row in enumerate(rows, start=1):
            snapshots.append(
                {
                    "display_label": f"Session {index:02d}",
                    "visitor_type": row["visitor_type"],
                    "visitor_label": (
                        "Logged-in visitor"
                        if row["visitor_type"] == "authenticated"
                        else "Anonymous visitor"
                    ),
                    "persona_label": row["persona_segment"],
                    "device_label": row["device_type"],
                    "region_label": row["region"],
                    "last_touch": row["last_touch"],
                    "touch_count": row["touchpoints"],
                }
            )
        return snapshots

    def _visitor_account_from_session(self) -> dict | None:
        visitor = session.get("visitor")
        if not isinstance(visitor, dict) or "id" not in visitor:
            return None
        return {
            "id": int(visitor["id"]),
            "username": visitor.get("username", ""),
            "email": visitor.get("email"),
            "display_name": visitor.get("display_name") or visitor.get("username", "Visitor"),
        }

    def _with_visitor_details(self, details: dict, visitor: dict) -> dict:
        enriched = dict(details)
        enriched["visitor_type"] = visitor["visitor_type"]
        if visitor.get("visitor_id") is not None:
            enriched["visitor_id"] = visitor["visitor_id"]
            enriched["visitor_username"] = visitor.get("username")
        else:
            enriched["anonymous_session"] = True
        return enriched

    def _build_profile(
        self,
        session_token: str,
        user_agent: str,
        language: str,
        referrer: str,
        visitor_account: dict | None = None,
    ) -> dict:
        digest = int(hashlib.sha256(session_token.encode("utf-8")).hexdigest(), 16)
        device_type = "Mobile" if "Mobile" in user_agent else "Desktop"
        persona_segment = PERSONA_SEGMENTS[digest % len(PERSONA_SEGMENTS)]
        region = REGIONS[(digest // 7) % len(REGIONS)]
        remote_addr = request.remote_addr if has_request_context() else session_token
        ip_hash = hashlib.sha256((remote_addr or session_token).encode("utf-8")).hexdigest()[:12]
        profile = {
            "persona_segment": persona_segment,
            "device_type": device_type,
            "region": region,
            "language": language,
            "referrer": referrer,
            "ip_hash": ip_hash,
            "user_agent": user_agent[:160],
        }
        if visitor_account:
            profile.update(
                {
                    "visitor_type": "authenticated",
                    "visitor_id": visitor_account["id"],
                    "username": visitor_account["username"],
                    "display_name": visitor_account["display_name"],
                    "email": visitor_account.get("email"),
                }
            )
        else:
            profile.update(
                {
                    "visitor_type": "anonymous",
                    "visitor_id": None,
                    "session_label": "anonymous visitor session",
                }
            )
        return profile

    def _upsert_visitor_session(
        self,
        db,
        session_token: str,
        profile: dict,
        timestamp: str,
        visitor_id: int | None = None,
        visitor_type: str = "anonymous",
    ) -> None:
        encrypted_profile = self.encryption.encrypt_json(profile)
        existing = db.execute(
            "SELECT session_token FROM visitor_sessions WHERE session_token = ?",
            (session_token,),
        ).fetchone()
        if existing:
            db.execute(
                """
                UPDATE visitor_sessions
                SET
                    visitor_id = ?,
                    visitor_type = ?,
                    persona_segment = ?,
                    device_type = ?,
                    region = ?,
                    profile_encrypted = ?,
                    last_seen_at = ?
                WHERE session_token = ?
                """,
                (
                    visitor_id,
                    visitor_type,
                    profile["persona_segment"],
                    profile["device_type"],
                    profile["region"],
                    encrypted_profile,
                    timestamp,
                    session_token,
                ),
            )
            return

        db.execute(
            """
            INSERT INTO visitor_sessions (
                session_token,
                visitor_id,
                visitor_type,
                persona_segment,
                device_type,
                region,
                profile_encrypted,
                first_seen_at,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_token,
                visitor_id,
                visitor_type,
                profile["persona_segment"],
                profile["device_type"],
                profile["region"],
                encrypted_profile,
                timestamp,
                timestamp,
            ),
        )

    def _log_activity(
        self,
        blogger_id: int | None,
        post_id: int | None,
        session_token: str,
        visitor_id: int | None,
        visitor_type: str,
        event_type: str,
        path: str,
        dwell_seconds: int,
        details: dict,
    ) -> None:
        db = get_db()
        self._insert_activity(
            db,
            blogger_id=blogger_id,
            post_id=post_id,
            session_token=session_token,
            visitor_id=visitor_id,
            visitor_type=visitor_type,
            event_type=event_type,
            path=path,
            dwell_seconds=dwell_seconds,
            details=details,
            occurred_at=utcnow(),
        )
        db.commit()

    def _insert_activity(
        self,
        db,
        blogger_id: int | None,
        post_id: int | None,
        session_token: str,
        event_type: str,
        path: str,
        dwell_seconds: int,
        details: dict,
        occurred_at: str,
        visitor_id: int | None = None,
        visitor_type: str = "anonymous",
    ) -> None:
        db.execute(
            """
            INSERT INTO activity_logs (
                blogger_id, post_id, session_token, visitor_id, visitor_type,
                event_type, path, dwell_seconds, details_encrypted, occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                blogger_id,
                post_id,
                session_token,
                visitor_id,
                visitor_type,
                event_type,
                path,
                dwell_seconds,
                self.encryption.encrypt_json(details),
                occurred_at,
            ),
        )

    def _insert_comment(
        self,
        db,
        blogger_id: int,
        post_id: int,
        session_token: str,
        author_alias: str,
        content: str,
        occurred_at: str,
        visitor_id: int | None = None,
        visitor_type: str = "anonymous",
    ) -> None:
        db.execute(
            """
            INSERT INTO comments (
                blogger_id, post_id, session_token, visitor_id, visitor_type,
                author_alias, content_encrypted, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                blogger_id,
                post_id,
                session_token,
                visitor_id,
                visitor_type,
                author_alias,
                self.encryption.encrypt_text(content),
                occurred_at,
            ),
        )
