from __future__ import annotations

import hashlib
import random
import secrets
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import has_request_context, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

PERSONA_SEGMENTS = ["内容创业者", "学生群体", "开发者", "产品经理", "自由撰稿人"]
REGIONS = ["上海", "北京", "深圳", "杭州", "成都", "新加坡", "悉尼"]
COMMENT_SNIPPETS = [
    "这篇文章的安全设计思路非常清楚。",
    "仪表盘的分层展示很适合团队协作。",
    "能否再补一个访客来源维度？",
    "我很喜欢把行为轨迹和时间序列结合展示的方式。",
]
EVENT_LABELS = {
    "home_view": "首页",
    "page_view": "文章浏览",
    "like": "点赞",
    "comment": "评论",
    "share": "分享",
    "dwell_time": "停留",
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
        exists = db.execute("SELECT COUNT(*) AS count FROM bloggers").fetchone()["count"]
        if exists:
            return

        created_at = utcnow()
        bloggers = [
            (
                "lin",
                generate_password_hash("blog123"),
                "林岚",
                "standard",
                "专注内容增长与基础运营复盘。",
                created_at,
            ),
            (
                "helen",
                generate_password_hash("blog123"),
                "何念",
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
                "安全内容增长的三层漏斗",
                "把访问、互动和转化统一到一个可追踪的博客增长模型。",
                (
                    "我们把博客活动拆成首页触达、文章消费和互动转化三层，"
                    "再通过安全追踪把浏览、停留和互动事件统一落库。"
                ),
                created_at,
            ),
            (
                blogger_map["lin"]["id"],
                "basic-metrics-playbook",
                "基础指标看板如何真正帮到普通博主",
                "总浏览量、点赞和画像标签并不只是展示，它们决定了复盘节奏。",
                (
                    "对普通博主来说，聚焦高频基础指标能更快发现哪些内容值得持续投入，"
                    "而不会在复杂图表中迷失。"
                ),
                created_at,
            ),
            (
                blogger_map["helen"]["id"],
                "zero-trust-analytics",
                "零信任思路下的内容分析平台",
                "从传输到存储都按最小暴露面设计用户行为分析系统。",
                (
                    "高级分析不意味着牺牲隐私。我们可以把敏感明细加密存储，"
                    "同时保留对时间序列和行为路径的可解释性。"
                ),
                created_at,
            ),
            (
                blogger_map["helen"]["id"],
                "journey-mapping-for-bloggers",
                "博主专属的用户行为路径图谱",
                "从首页进入到分享扩散，路径图谱帮助高级博主识别关键行为节点。",
                (
                    "当我们知道用户从哪里来、在哪篇文章停留更久、"
                    "又会在什么节点点赞或评论，运营动作就能更加精细。"
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
                        "journey_step": "首页",
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
                        "journey_step": f"阅读《{post['title']}》",
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
                        "journey_step": "深度阅读",
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
                        details={"journey_step": "点赞"},
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
                            "journey_step": "分享",
                            "channel": rnd.choice(["微信", "微博", "复制链接"]),
                        },
                        occurred_at=to_iso(view_time + timedelta(minutes=3)),
                    )

                if rnd.random() < 0.22:
                    author_alias = rnd.choice(["晨光", "Kevin", "Olivia", "Mia"])
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
                        details={"journey_step": "评论"},
                        occurred_at=to_iso(view_time + timedelta(minutes=4)),
                    )

        db.commit()

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
            SELECT author_alias, content_encrypted, created_at
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

    def ensure_visitor_session(self) -> dict:
        db = get_db()
        session_token = session.get("visitor_token")
        now = utcnow()
        if not session_token:
            session_token = f"vis-{secrets.token_urlsafe(18)}"
            session["visitor_token"] = session_token

        row = db.execute(
            """
            SELECT session_token, persona_segment, device_type, region, profile_encrypted
            FROM visitor_sessions
            WHERE session_token = ?
            """,
            (session_token,),
        ).fetchone()
        if row:
            db.execute(
                "UPDATE visitor_sessions SET last_seen_at = ? WHERE session_token = ?",
                (now, session_token),
            )
            db.commit()
            return dict(row)

        profile = self._build_profile(
            session_token,
            request.headers.get("User-Agent", "Unknown"),
            request.headers.get("Accept-Language", "Unknown"),
            request.referrer or "直接访问",
        )
        self._upsert_visitor_session(db, session_token, profile, now)
        db.commit()
        return {
            "session_token": session_token,
            "persona_segment": profile["persona_segment"],
            "device_type": profile["device_type"],
            "region": profile["region"],
            "profile_encrypted": self.encryption.encrypt_json(profile),
        }

    def record_home_view(self) -> None:
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=None,
            post_id=None,
            session_token=visitor["session_token"],
            event_type="home_view",
            path="/",
            dwell_seconds=0,
            details={
                "journey_step": "首页",
                "surface": "frontpage",
            },
        )

    def record_post_view(self, post: dict) -> None:
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=post["blogger_id"],
            post_id=post["id"],
            session_token=visitor["session_token"],
            event_type="page_view",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details={
                "journey_step": f"阅读《{post['title']}》",
                "post_title": post["title"],
                "referrer": request.referrer or "直接访问",
            },
        )

    def record_dwell_time(self, post_id: int, seconds: int) -> dict:
        post = self.get_post_by_id(post_id)
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=post["blogger_id"],
            post_id=post["id"],
            session_token=visitor["session_token"],
            event_type="dwell_time",
            path=f"/post/{post['slug']}",
            dwell_seconds=seconds,
            details={
                "journey_step": "深度阅读",
                "seconds": seconds,
            },
        )
        return self.get_post_metrics(post_id)

    def add_like(self, post_id: int) -> dict:
        post = self.get_post_by_id(post_id)
        visitor = self.ensure_visitor_session()
        self._log_activity(
            blogger_id=post["blogger_id"],
            post_id=post_id,
            session_token=visitor["session_token"],
            event_type="like",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details={"journey_step": "点赞"},
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
            event_type="share",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details={
                "journey_step": "分享",
                "channel": channel,
            },
        )
        return self.get_post_metrics(post_id)

    def add_comment(self, post_id: int, author_alias: str, content: str) -> dict:
        post = self.get_post_by_id(post_id)
        visitor = self.ensure_visitor_session()
        created_at = utcnow()
        db = get_db()
        self._insert_comment(
            db,
            blogger_id=post["blogger_id"],
            post_id=post_id,
            session_token=visitor["session_token"],
            author_alias=author_alias,
            content=content,
            occurred_at=created_at,
        )
        self._insert_activity(
            db,
            blogger_id=post["blogger_id"],
            post_id=post_id,
            session_token=visitor["session_token"],
            event_type="comment",
            path=f"/post/{post['slug']}",
            dwell_seconds=0,
            details={"journey_step": "评论"},
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
            WHERE a.blogger_id = ? AND a.event_type = 'page_view'
            GROUP BY s.persona_segment
            ORDER BY count DESC
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
        dashboard = {
            "metrics": {
                "views": metrics_row["views"] or 0,
                "likes": metrics_row["likes"] or 0,
                "shares": metrics_row["shares"] or 0,
                "comments": metrics_row["comments"] or 0,
                "avg_dwell": round(metrics_row["avg_dwell"] or 0, 1),
            },
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

    def _build_journey_paths(self, blogger_id: int) -> list[dict]:
        db = get_db()
        rows = db.execute(
            """
            SELECT session_token, event_type, details_encrypted, occurred_at
            FROM activity_logs
            WHERE blogger_id = ?
              AND event_type IN ('home_view', 'page_view', 'like', 'comment', 'share')
            ORDER BY session_token, occurred_at
            """,
            (blogger_id,),
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
                s.persona_segment,
                s.device_type,
                s.region,
                MAX(a.occurred_at) AS last_touch,
                COUNT(*) AS touchpoints
            FROM activity_logs a
            JOIN visitor_sessions s ON s.session_token = a.session_token
            WHERE a.blogger_id = ?
            GROUP BY s.session_token, s.persona_segment, s.device_type, s.region
            ORDER BY last_touch DESC
            LIMIT 6
            """,
            (blogger_id,),
        ).fetchall()
        return [
            {
                "token": row["session_token"][-8:],
                "persona": row["persona_segment"],
                "device": row["device_type"],
                "region": row["region"],
                "last_touch": row["last_touch"],
                "touchpoints": row["touchpoints"],
            }
            for row in rows
        ]

    def _build_profile(self, session_token: str, user_agent: str, language: str, referrer: str) -> dict:
        digest = int(hashlib.sha256(session_token.encode("utf-8")).hexdigest(), 16)
        device_type = "移动端" if "Mobile" in user_agent else "桌面端"
        persona_segment = PERSONA_SEGMENTS[digest % len(PERSONA_SEGMENTS)]
        region = REGIONS[(digest // 7) % len(REGIONS)]
        remote_addr = request.remote_addr if has_request_context() else session_token
        ip_hash = hashlib.sha256((remote_addr or session_token).encode("utf-8")).hexdigest()[:12]
        return {
            "persona_segment": persona_segment,
            "device_type": device_type,
            "region": region,
            "language": language,
            "referrer": referrer,
            "ip_hash": ip_hash,
            "user_agent": user_agent[:160],
        }

    def _upsert_visitor_session(self, db, session_token: str, profile: dict, timestamp: str) -> None:
        db.execute(
            """
            INSERT OR REPLACE INTO visitor_sessions (
                session_token,
                persona_segment,
                device_type,
                region,
                profile_encrypted,
                first_seen_at,
                last_seen_at
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                COALESCE((SELECT first_seen_at FROM visitor_sessions WHERE session_token = ?), ?),
                ?
            )
            """,
            (
                session_token,
                profile["persona_segment"],
                profile["device_type"],
                profile["region"],
                self.encryption.encrypt_json(profile),
                session_token,
                timestamp,
                timestamp,
            ),
        )

    def _log_activity(
        self,
        blogger_id: int | None,
        post_id: int | None,
        session_token: str,
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
    ) -> None:
        db.execute(
            """
            INSERT INTO activity_logs (
                blogger_id, post_id, session_token, event_type, path,
                dwell_seconds, details_encrypted, occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                blogger_id,
                post_id,
                session_token,
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
    ) -> None:
        db.execute(
            """
            INSERT INTO comments (
                blogger_id, post_id, session_token, author_alias, content_encrypted, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                blogger_id,
                post_id,
                session_token,
                author_alias,
                self.encryption.encrypt_text(content),
                occurred_at,
            ),
        )
