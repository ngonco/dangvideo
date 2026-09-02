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

    def get_oldest_pending_video(self) -> Optional[Dict[str, Any]]:
        """Lấy video chưa đăng cũ nhất trong kho hàng đợi (FIFO)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM videos 
            WHERE status = 'downloaded' 
              AND file_path IS NOT NULL 
              AND file_path != ''
            ORDER BY id ASC 
            LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_pending_videos_count(self) -> int:
        """Đếm tổng số video đang chờ trong hàng đợi"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT COUNT(*) FROM videos 
            WHERE status = 'downloaded' 
              AND file_path IS NOT NULL 
              AND file_path != ''
            """)
            return cursor.fetchone()[0]

    def get_queue_summary(self, slots_per_day: int = 3) -> Dict[str, Any]:
        """Tổng hợp thông tin kho hàng đợi và số ngày dự kiến đăng"""
        import math
        total = self.get_pending_videos_count()
        slots = max(1, slots_per_day)
        estimated_days = math.ceil(total / slots) if total > 0 else 0
        return {
            "total_pending": total,
            "slots_per_day": slots,
            "estimated_days": estimated_days
        }

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

    def get_all_videos_with_latest_posts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Lấy toàn bộ danh sách video kèm kết quả mới nhất cho từng nền tảng, không bị trùng lặp"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id, hatbuinho_id, title, suggested_title, file_path, status, created_date_str, downloaded_at
            FROM videos
            ORDER BY id DESC
            LIMIT ?
            """, (limit,))
            videos = [dict(r) for r in cursor.fetchall()]

            for v in videos:
                vid_id = v["id"]
                cursor.execute("""
                SELECT platform, status, post_url, error_message, posted_at
                FROM post_history
                WHERE video_id = ?
                ORDER BY id DESC
                """, (vid_id,))
                posts = [dict(r) for r in cursor.fetchall()]

                # Deduplicate: chỉ giữ kết quả mới nhất cho mỗi platform
                latest_platforms = {}
                for p in posts:
                    plat = p["platform"]
                    if plat not in latest_platforms:
                        latest_platforms[plat] = p

                v["platforms"] = latest_platforms

                if posts:
                    v["time"] = posts[0]["posted_at"]
                else:
                    v["time"] = v.get("downloaded_at") or v.get("created_date_str") or ""

            return videos

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

    def get_last_success_at(self, platform: str) -> Optional[datetime]:
        """Thời điểm success gần nhất của một nền tảng (posted_at)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT posted_at FROM post_history
                WHERE platform = ? AND status = 'success'
                ORDER BY id DESC LIMIT 1
                """,
                (platform,),
            )
            row = cursor.fetchone()
            if not row or not row[0]:
                return None
            raw = str(row[0]).replace("T", " ").split(".")[0]
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(str(row[0]))
            except Exception:
                return None

db = Database()
