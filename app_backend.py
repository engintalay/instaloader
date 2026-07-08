#!/usr/bin/env python3
"""Core services for user-based Instagram downloads and file indexing."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import instaloader

BASE_DIR = Path(__file__).resolve().parent
USERS_DIR = BASE_DIR / "users"
DB_PATH = BASE_DIR / "file_index.db"
COOKIE_FILE = BASE_DIR / "cookies.json"
COOKIE_STORE_DIR = BASE_DIR / "cookie_files"

LogCallback = Callable[[str], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FileIndexDB:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    root_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    profile TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    absolute_path TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    extension TEXT,
                    size_bytes INTEGER NOT NULL,
                    modified_at TEXT NOT NULL,
                    sha256 TEXT,
                    source_type TEXT NOT NULL,
                    profile TEXT,
                    indexed_at TEXT NOT NULL,
                    UNIQUE(user_id, relative_path),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_files_user ON files(user_id);
                CREATE INDEX IF NOT EXISTS idx_files_name ON files(file_name);
                CREATE INDEX IF NOT EXISTS idx_downloads_user ON downloads(user_id);
                """
            )

    def ensure_user(self, user_name: str) -> int:
        user_root = str(get_user_root(user_name))
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(name, root_path, created_at)
                VALUES(?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET root_path=excluded.root_path
                """,
                (user_name, user_root, now),
            )
            row = conn.execute("SELECT id FROM users WHERE name = ?", (user_name,)).fetchone()
            if row is None:
                raise RuntimeError("User could not be created")
            return int(row[0])

    def list_users(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT name FROM users ORDER BY name ASC").fetchall()
        return [r[0] for r in rows]

    def record_download(
        self,
        user_name: str,
        profile: str,
        source: str,
        status: str,
        message: str,
        started_at: str,
        finished_at: Optional[str],
    ) -> None:
        user_id = self.ensure_user(user_name)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO downloads(user_id, profile, source, status, message, started_at, finished_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, profile, source, status, message, started_at, finished_at),
            )

    def index_file(
        self,
        user_name: str,
        file_path: Path,
        source_type: str,
        profile: Optional[str] = None,
        hash_file: bool = False,
    ) -> None:
        user_id = self.ensure_user(user_name)
        user_root = get_user_root(user_name)
        if not file_path.exists() or not file_path.is_file():
            return

        relative_path = str(file_path.resolve().relative_to(user_root.resolve()))
        stat = file_path.stat()
        sha256 = sha256_of_file(file_path) if hash_file else None
        indexed_at = utc_now_iso()
        ext = file_path.suffix.lower()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO files(
                    user_id, relative_path, absolute_path, file_name, extension,
                    size_bytes, modified_at, sha256, source_type, profile, indexed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, relative_path) DO UPDATE SET
                    absolute_path=excluded.absolute_path,
                    file_name=excluded.file_name,
                    extension=excluded.extension,
                    size_bytes=excluded.size_bytes,
                    modified_at=excluded.modified_at,
                    sha256=COALESCE(excluded.sha256, files.sha256),
                    source_type=excluded.source_type,
                    profile=excluded.profile,
                    indexed_at=excluded.indexed_at
                """,
                (
                    user_id,
                    relative_path,
                    str(file_path.resolve()),
                    file_path.name,
                    ext,
                    int(stat.st_size),
                    datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    sha256,
                    source_type,
                    profile,
                    indexed_at,
                ),
            )

    def prune_missing_files(self, user_name: str) -> int:
        user_id = self.ensure_user(user_name)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, absolute_path FROM files WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            removed = 0
            for file_id, abs_path in rows:
                if not Path(abs_path).exists():
                    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
                    removed += 1
        return removed

    def list_user_files(self, user_name: str, limit: int = 500) -> list[tuple]:
        user_id = self.ensure_user(user_name)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT relative_path, size_bytes, modified_at, source_type, COALESCE(profile, '')
                FROM files
                WHERE user_id = ?
                ORDER BY modified_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return rows


def get_user_root(user_name: str) -> Path:
    safe_name = user_name.strip()
    if not safe_name:
        raise ValueError("User name cannot be empty")
    return USERS_DIR / safe_name


def ensure_user_dirs(user_name: str) -> Path:
    root = get_user_root(user_name)
    (root / "downloads").mkdir(parents=True, exist_ok=True)
    (root / "manual").mkdir(parents=True, exist_ok=True)
    (root / "stories").mkdir(parents=True, exist_ok=True)
    return root


def get_cookies_from_file(path: Path = COOKIE_FILE) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def discover_cookie_files(include_example: bool = False) -> list[Path]:
    paths: list[Path] = []
    if BASE_DIR.exists():
        paths.extend(BASE_DIR.glob("cookies*.json"))
        paths.extend(BASE_DIR.glob("*cookies*.json"))
    if COOKIE_STORE_DIR.exists():
        paths.extend(COOKIE_STORE_DIR.glob("*.json"))

    unique: dict[str, Path] = {}
    for path in paths:
        if not path.is_file():
            continue
        if not include_example and path.name == "cookies.example.json":
            continue
        unique[str(path.resolve())] = path

    return sorted(unique.values(), key=lambda p: p.name.lower())


def import_cookie_file(
    src_path: Path,
    preferred_name: Optional[str] = None,
    overwrite: bool = False,
) -> Path:
    if not src_path.exists() or not src_path.is_file():
        raise FileNotFoundError(f"Cookie file not found: {src_path}")

    COOKIE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    file_name = (preferred_name or src_path.name).strip()
    if not file_name:
        file_name = src_path.name
    if not file_name.lower().endswith(".json"):
        file_name = f"{file_name}.json"

    target = COOKIE_STORE_DIR / file_name
    if target.exists() and not overwrite:
        stamp = int(time.time())
        target = COOKIE_STORE_DIR / f"{target.stem}_{stamp}{target.suffix}"

    shutil.copy2(src_path, target)
    return target


def get_cookies_chrome() -> dict:
    from pycookiecheat import chrome_cookies

    return chrome_cookies("https://www.instagram.com")


def get_cookies_firefox() -> dict:
    import browser_cookie3

    cj = browser_cookie3.firefox(domain_name=".instagram.com")
    return {c.name: c.value for c in cj if "instagram" in c.domain}


def resolve_cookies(source: str) -> dict:
    source = source.strip()
    if source == "file":
        return get_cookies_from_file()
    if source == "chrome":
        return get_cookies_chrome()
    if source == "firefox":
        return get_cookies_firefox()

    if source.startswith("cookie:"):
        cookie_ref = source.split(":", 1)[1].strip()
        cookie_path = Path(cookie_ref)
        if cookie_path.exists() and cookie_path.is_file():
            return get_cookies_from_file(cookie_path)
        for candidate in discover_cookie_files(include_example=False):
            if candidate.name == cookie_ref:
                return get_cookies_from_file(candidate)
        raise FileNotFoundError(f"Managed cookie file not found: {cookie_ref}")

    path = Path(source)
    if path.exists() and path.is_file():
        return get_cookies_from_file(path)

    for candidate in discover_cookie_files(include_example=False):
        if candidate.name == source:
            return get_cookies_from_file(candidate)

    raise FileNotFoundError(f"Cookie source not found: {source}")


@dataclass
class DownloadResult:
    ok: bool
    message: str
    files_indexed: int


def download_instagram_profile(
    user_name: str,
    profile: str,
    source: str,
    db: FileIndexDB,
    log: Optional[LogCallback] = None,
) -> DownloadResult:
    def emit(msg: str) -> None:
        if log:
            log(msg)

    ensure_user_dirs(user_name)
    user_root = get_user_root(user_name)
    started_at = utc_now_iso()

    try:
        cookies = resolve_cookies(source)
        if "sessionid" not in cookies:
            raise RuntimeError("Instagram sessionid cookie bulunamadı")

        emit(f"[*] {source} cookie kaynağı yükleniyor")
        loader = instaloader.Instaloader(
            save_metadata=False,
            compress_json=False,
            post_metadata_txt_pattern="",
            dirname_pattern=str(user_root / "downloads" / "{target}"),
        )

        loader.load_session("_temp_", cookies)
        username = loader.test_login()
        if not username:
            raise RuntimeError("Cookie geçersiz veya süresi dolmuş")

        loader.load_session(username, cookies)
        emit(f"[+] {username} ile giriş yapıldı")

        prof = instaloader.Profile.from_username(loader.context, profile)

        emit("[*] Profil görseli çekiliyor")
        try:
            loader.download_profile(prof.username, profile_pic_only=True)
        except Exception as ex:  # noqa: BLE001
            emit(f"[!] Profil görseli çekilemedi: {ex}")

        emit("[*] Postlar çekiliyor")
        for post in prof.get_posts():
            try:
                loader.download_post(post, target=profile)
            except Exception as ex:  # noqa: BLE001
                emit(f"[!] Post atlandı {post.shortcode}: {ex}")

        emit("[*] Etiketli postlar çekiliyor")
        try:
            for post in prof.get_tagged_posts():
                try:
                    loader.download_post(post, target=f"{profile}:tagged")
                except Exception as ex:  # noqa: BLE001
                    emit(f"[!] Etiketli post atlandı {post.shortcode}: {ex}")
        except Exception as ex:  # noqa: BLE001
            emit(f"[!] Etiketli postlar alınamadı: {ex}")

        emit("[*] Highlights çekiliyor")
        try:
            highlights = loader.get_highlights(prof)
            loader.download_highlights(highlights, target=profile, fast_update=True)
        except Exception as ex:  # noqa: BLE001
            emit(f"[!] Highlights alınamadı: {ex}")

        emit("[*] Story çekiliyor")
        try:
            loader.download_stories(userids=[prof.userid], fast_update=True)
        except Exception as ex:  # noqa: BLE001
            emit(f"[!] Story alınamadı: {ex}")

        indexed_count = index_user_tree(db, user_name=user_name)
        msg = f"{profile} tamamlandı, indekslenen dosya: {indexed_count}"
        finished_at = utc_now_iso()
        db.record_download(
            user_name=user_name,
            profile=profile,
            source=source,
            status="success",
            message=msg,
            started_at=started_at,
            finished_at=finished_at,
        )
        emit(f"[+] {msg}")
        return DownloadResult(ok=True, message=msg, files_indexed=indexed_count)

    except Exception as ex:  # noqa: BLE001
        finished_at = utc_now_iso()
        error_message = str(ex)
        db.record_download(
            user_name=user_name,
            profile=profile,
            source=source,
            status="failed",
            message=error_message,
            started_at=started_at,
            finished_at=finished_at,
        )
        emit(f"[!] İndirme hatası: {error_message}")
        return DownloadResult(ok=False, message=error_message, files_indexed=0)


def index_user_tree(db: FileIndexDB, user_name: str) -> int:
    user_root = ensure_user_dirs(user_name)
    count = 0
    for root, _, files in os.walk(user_root):
        root_path = Path(root)
        if any(part in {".thumb_cache", ".thumbcache"} for part in root_path.parts):
            continue
        for name in files:
            path = Path(root) / name
            try:
                db.index_file(user_name, path, source_type="scan", profile=None, hash_file=False)
                count += 1
            except Exception:
                continue
    db.prune_missing_files(user_name)
    return count


def add_manual_files(
    db: FileIndexDB,
    user_name: str,
    src_files: list[Path],
    category: str = "manual",
    copy_into_user_folder: bool = True,
) -> int:
    user_root = ensure_user_dirs(user_name)
    target_dir = user_root / "manual" / category
    target_dir.mkdir(parents=True, exist_ok=True)

    added = 0
    for src in src_files:
        if not src.exists() or not src.is_file():
            continue
        if copy_into_user_folder:
            dst = target_dir / src.name
            if dst.exists():
                stem = dst.stem
                suffix = dst.suffix
                dst = target_dir / f"{stem}_{int(time.time())}{suffix}"
            shutil.copy2(src, dst)
            index_target = dst
            source_type = "manual-copy"
        else:
            index_target = src
            source_type = "manual-link"

        db.index_file(user_name, index_target, source_type=source_type, profile=None, hash_file=False)
        added += 1

    return added


class DownloadQueueWorker:
    def __init__(self, db: FileIndexDB, log: Optional[LogCallback] = None) -> None:
        self.db = db
        self.log = log
        self.jobs: queue.Queue[tuple[str, str, str]] = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def emit(self, msg: str) -> None:
        if self.log:
            self.log(msg)

    def enqueue(self, user_name: str, profile: str, source: str) -> None:
        self.jobs.put((user_name, profile, source))
        self.emit(f"[q] Kuyruğa eklendi: user={user_name}, profile={profile}, source={source}")

    def pending_jobs(self) -> int:
        return self.jobs.qsize()

    def stop(self) -> None:
        self._stop.set()
        self.jobs.put(("", "", ""))
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            user_name, profile, source = self.jobs.get()
            if self._stop.is_set() or not user_name:
                self.jobs.task_done()
                break

            self.emit(f"[>] Arka plan çekim başladı: {profile}")
            result = download_instagram_profile(
                user_name=user_name,
                profile=profile,
                source=source,
                db=self.db,
                log=self.emit,
            )
            status = "OK" if result.ok else "ERROR"
            self.emit(f"[{status}] Arka plan çekim bitti: {result.message}")
            self.jobs.task_done()
