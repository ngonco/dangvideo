import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from core.config_manager import DB_PATH

class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Videos table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hatbuinho_id TEXT UNIQUE,
                title TEXT,
                raw_script TEXT,
                suggested_title TEXT,
                hashtags TEXT,
                file_path TEXT,
                file_size INTEGER DEFAULT 0,
                status TEXT DEFAULT 'downloaded',
                created_date_str TEXT,
                downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Post history table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS post_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                platform TEXT,
                status TEXT,
                post_url TEXT,
                error_message TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos (id)
            )
            """)

            conn.commit()

    def add_or_update_video(self, video_data: Dict[str, Any]) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO videos (
                hatbuinho_id, title, raw_script, suggested_title, hashtags,
                file_path, file_size, status, created_date_str, downloaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(hatbuinho_id) DO UPDATE SET
                title = COALESCE(excluded.title, videos.title),
                suggested_title = COALESCE(excluded.suggested_title, videos.suggested_title),
                hashtags = COALESCE(excluded.hashtags, videos.hashtags),
                file_path = COALESCE(excluded.file_path, videos.file_path),
                file_size = COALESCE(excluded.file_size, videos.file_size),
                status = COALESCE(excluded.status, videos.status)
            """, (
                video_data.get("hatbuinho_id"),
                video_data.get("title", ""),
                video_data.get("raw_script", ""),
                video_data.get("suggested_title", ""),
                video_data.get("hashtags", ""),
                video_data.get("file_path", ""),
                video_data.get("file_size", 0),
                video_data.get("status", "downloaded"),
                video_data.get("created_date_str", "")
            ))
            conn.commit()
            return cursor.lastrowid

    def get_video_by_id(self, video_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_video_by_hatbuinho_id(self, hatbuinho_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM videos WHERE hatbuinho_id = ?", (hatbuinho_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def list_videos(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT v.*,
                (SELECT GROUP_CONCAT(platform || ':' || status) FROM post_history WHERE video_id = v.id) as platform_statuses,
                (SELECT COUNT(*) FROM post_history WHERE video_id = v.id) as post_attempts_count
            FROM videos v
            ORDER BY v.id DESC
            LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def record_post(self, video_id: int, platform: str, status: str, post_url: str = "", error_message: str = ""):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO post_history (video_id, platform, status, post_url, error_message, posted_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (video_id, platform, status, post_url, error_message))
            
            cursor.execute("""
            UPDATE videos SET status = 'posted' WHERE id = ? AND ? = 'success'
            """, (video_id, status))
            conn.commit()

    def get_post_history(self, video_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if video_id:
                cursor.execute("""
                SELECT ph.*, v.title, v.file_path, v.suggested_title FROM post_history ph
                JOIN videos v ON v.id = ph.video_id
                WHERE ph.video_id = ?
                ORDER BY ph.id DESC LIMIT ?
                """, (video_id, limit))
            else:
                cursor.execute("""
                SELECT ph.*, v.title, v.file_path, v.suggested_title FROM post_history ph
                JOIN videos v ON v.id = ph.video_id
                ORDER BY ph.id DESC LIMIT ?
                """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def clean_old_posted_videos(self, retention_days: int = 2) -> Dict[str, Any]:
        """Tự động dọn dẹp các tệp video .mp4 đã đăng sau số ngày chỉ định (mặc định 2 ngày)"""
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0
        freed_bytes = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, title, file_path, file_size FROM videos
            WHERE status = 'posted' 
              AND file_path IS NOT NULL 
              AND file_path != ''
              AND (
                  downloaded_at <= ? 
                  OR id IN (SELECT video_id FROM post_history WHERE status = 'success' AND posted_at <= ?)
              )
            """, (cutoff_date.strftime("%Y-%m-%d %H:%M:%S"), cutoff_date.strftime("%Y-%m-%d %H:%M:%S")))
            
            rows = cursor.fetchall()

            for row in rows:
                vid_id = row["id"]
                file_path = row["file_path"]
                file_size = row["file_size"] or 0

                if file_path and os.path.exists(file_path):
                    try:
                        actual_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        freed_bytes += actual_size
                        deleted_count += 1
                    except Exception:
                        pass

                cursor.execute("""
                UPDATE videos SET file_path = '', status = 'cleaned'
                WHERE id = ?
                """, (vid_id,))

            conn.commit()

        return {
            "deleted_count": deleted_count,
            "freed_bytes": freed_bytes,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2)
        }

    def get_stats(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM videos")
            total_videos = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM post_history WHERE status = 'success'")
            total_posts_success = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM post_history WHERE status = 'failed'")
            total_posts_failed = cursor.fetchone()[0]

            today_str = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("""
            SELECT COUNT(*) FROM post_history 
            WHERE status = 'success' AND DATE(posted_at) = ?
            """, (today_str,))
            posts_today = cursor.fetchone()[0]

            return {
                "total_videos": total_videos,
                "total_posts_success": total_posts_success,
                "total_posts_failed": total_posts_failed,
                "posts_today": posts_today
            }

db = Database()
