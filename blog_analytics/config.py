from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INSTANCE_DIR = BASE_DIR / "instance"
DB_PATH = INSTANCE_DIR / "secure_blog.db"
KEY_PATH = INSTANCE_DIR / "fernet.key"


class Config:
    SECRET_KEY = os.environ.get("BLOG_SESSION_SECRET", "secure-blog-demo-session")
    DATABASE = os.environ.get("BLOG_DATABASE", str(DB_PATH))
    ENCRYPTION_KEY_FILE = os.environ.get("BLOG_ENCRYPTION_KEY_FILE", str(KEY_PATH))
    PREFERRED_URL_SCHEME = "https"
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    JSON_AS_ASCII = False
