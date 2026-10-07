"""Durable daily assignments and per-channel delivery checkpoints."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

VIETNAM = timezone(timedelta(hours=7), 'Asia/Ho_Chi_Minh')


def local_now():
    return datetime.now(VIETNAM).replace(tzinfo=None)


def stamp(value=None):
    return (value or local_now()).strftime('%Y-%m-%d %H:%M:%S')


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class PostingStore:
    def init_posting_store(self):
        with self.get_connection() as conn:
            columns = {r[1] for r in conn.execute('PRAGMA table_info(videos)')}
            if 'content_sha256' not in columns:
                conn.execute("ALTER TABLE videos ADD COLUMN content_sha256 TEXT DEFAULT ''")
            if 'queue_removed_at' not in columns:
                conn.execute("ALTER TABLE videos ADD COLUMN queue_removed_at TEXT DEFAULT ''")
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS daily_runs (
                    day TEXT PRIMARY KEY, video_id INTEGER UNIQUE NOT NULL,
                    platforms TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS posting_tasks (
                    video_id INTEGER NOT NULL, platform TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry TEXT DEFAULT '', error TEXT DEFAULT '', submitted_at TEXT DEFAULT '',
                    post_url TEXT DEFAULT '', scheduled_for TEXT DEFAULT '', updated_at TEXT NOT NULL,
                    PRIMARY KEY(video_id, platform));
                CREATE TABLE IF NOT EXISTS posting_health (
                    name TEXT PRIMARY KEY, state TEXT NOT NULL, detail TEXT DEFAULT '', updated_at TEXT NOT NULL);
            ''')

    def recover_interrupted_uploads(self):
        # Called only by the owning application at startup, never by a reader/import.
        with self.get_connection() as conn:
            conn.execute("UPDATE posting_tasks SET state='failed', next_retry=? WHERE state='uploading' AND submitted_at=''", (stamp(),))

    def set_health(self, name, state, detail=''):
        with self.get_connection() as conn:
            old = conn.execute('SELECT state,detail FROM posting_health WHERE name=?', (name,)).fetchone()
            changed = not old or old['state'] != state or old['detail'] != detail
            conn.execute('INSERT INTO posting_health VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET state=excluded.state,detail=excluded.detail,updated_at=excluded.updated_at', (name,state,detail,stamp()))
            return changed

    def get_health(self, name):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM posting_health WHERE name=?',(name,)).fetchone()
            return dict(row) if row else None

    def get_daily_run(self, day=None):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM daily_runs WHERE day=?', (day or local_now().date().isoformat(),)).fetchone()
            if not row:
                return None
            result = dict(row)
            result['platforms'] = json.loads(result['platforms'])
            return result

    def assign_daily_video(self, platforms, day=None):
        """The transaction prevents manual/automatic calls claiming a second video."""
        day = day or local_now().date().isoformat()
        with self.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute('SELECT video_id FROM daily_runs WHERE day=?', (day,)).fetchone()
            if existing:
                return existing['video_id']
            if not platforms:
                return None
            rows = conn.execute("""SELECT * FROM videos WHERE status='downloaded'
                AND id NOT IN (SELECT video_id FROM daily_runs)
                AND id NOT IN (SELECT video_id FROM post_history WHERE status='success')
                ORDER BY id""").fetchall()
            for row in rows:
                if not row['file_path'] or not os.path.isfile(row['file_path']):
                    continue
                conn.execute('INSERT INTO daily_runs VALUES(?,?,?,?)', (day,row['id'],json.dumps(platforms),stamp()))
                for platform in platforms:
                    conn.execute("INSERT OR IGNORE INTO posting_tasks(video_id,platform,updated_at) VALUES(?,?,?)", (row['id'],platform,stamp()))
                return row['id']
            return None

    def reserve_count(self):
        with self.get_connection() as conn:
            rows = conn.execute("""SELECT file_path FROM videos WHERE status='downloaded'
                AND id NOT IN (SELECT video_id FROM daily_runs)
                AND id NOT IN (SELECT video_id FROM post_history WHERE status='success')""").fetchall()
            return sum(bool(r['file_path'] and os.path.isfile(r['file_path'])) for r in rows)

    def update_today_targets(self, platforms):
        """A settings change keeps the chosen video and updates enabled channel goals."""
        with self.get_connection() as conn:
            row=conn.execute('SELECT r.video_id,v.status FROM daily_runs r JOIN videos v ON v.id=r.video_id WHERE r.day=?',(local_now().date().isoformat(),)).fetchone()
            if not row or row['status']=='cleaned':
                return
            video_id=row['video_id']
            conn.execute('UPDATE daily_runs SET platforms=? WHERE day=?',(json.dumps(platforms),local_now().date().isoformat()))
            successful={r[0] for r in conn.execute("SELECT DISTINCT platform FROM post_history WHERE video_id=? AND status='success'",(video_id,))}
            for platform in set(platforms)-successful:
                conn.execute('INSERT OR IGNORE INTO posting_tasks(video_id,platform,updated_at) VALUES(?,?,?)',(video_id,platform,stamp()))
            if platforms:
                conn.execute('UPDATE videos SET status=? WHERE id=?',('posted' if set(platforms).issubset(successful) else 'downloaded',video_id))

    def ensure_posting_task(self, video_id, platform):
        with self.get_connection() as conn:
            conn.execute('INSERT OR IGNORE INTO posting_tasks(video_id,platform,updated_at) VALUES(?,?,?)', (video_id,platform,stamp()))
        return self.get_posting_task(video_id,platform)

    def get_posting_task(self, video_id, platform):
        with self.get_connection() as conn:
            row = conn.execute('SELECT * FROM posting_tasks WHERE video_id=? AND platform=?', (video_id,platform)).fetchone()
            return dict(row) if row else None

    def begin_posting(self, video_id, platform, scheduled_for=''):
        with self.get_connection() as conn:
            conn.execute("UPDATE posting_tasks SET state='uploading', attempts=attempts+1,error='',next_retry='',scheduled_for=?,updated_at=? WHERE video_id=? AND platform=?", (scheduled_for,stamp(),video_id,platform))

    def mark_submitting(self, video_id, platform, candidate_url=''):
        with self.get_connection() as conn:
            result = conn.execute("UPDATE posting_tasks SET state='verifying',submitted_at=?,updated_at=?,post_url=CASE WHEN ? != '' THEN ? ELSE post_url END WHERE video_id=? AND platform=?", (stamp(),stamp(),candidate_url,candidate_url,video_id,platform))
            if result.rowcount != 1:
                raise RuntimeError('Không lưu được checkpoint gửi bài; dừng trước khi bấm nút gửi.')

    def set_posting_candidate_url(self, video_id, platform, url):
        if url:
            with self.get_connection() as conn:
                conn.execute('UPDATE posting_tasks SET post_url=? WHERE video_id=? AND platform=?',(url,video_id,platform))

    def begin_verification_attempt(self, video_id, platform):
        with self.get_connection() as conn:
            conn.execute("UPDATE posting_tasks SET attempts=attempts+1,updated_at=? WHERE video_id=? AND platform=? AND submitted_at!=''",(stamp(),video_id,platform))

    def claim_manual_daily_video(self, video_id, platforms):
        with self.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute("SELECT 1 FROM post_history WHERE video_id=? AND status='success' LIMIT 1", (video_id,)).fetchone()
            if platforms and not previous:
                conn.execute('INSERT OR IGNORE INTO daily_runs VALUES(?,?,?,?)', (local_now().date().isoformat(),video_id,json.dumps(platforms),stamp()))

    def finish_posting_task(self, video_id, platform, state, error='', post_url='', retry_at=None):
        task = self.ensure_posting_task(video_id,platform)
        if state == 'failed' and task['submitted_at']:
            state = 'verifying'
        minutes = (30,60,120)[min(max(task['attempts']-1,0),2)]
        next_retry = stamp(retry_at or local_now()+timedelta(minutes=minutes)) if state in ('failed','verifying','deferred') else ''
        with self.get_connection() as conn:
            conn.execute('UPDATE posting_tasks SET state=?,error=?,post_url=CASE WHEN ? != \'\' THEN ? ELSE post_url END,next_retry=?,updated_at=? WHERE video_id=? AND platform=?', (state,error,post_url,post_url,next_retry,stamp(),video_id,platform))

    def pending_delivery_videos(self):
        with self.get_connection() as conn:
            rows = conn.execute("""SELECT DISTINCT t.video_id FROM posting_tasks t JOIN videos v ON v.id=t.video_id
                WHERE v.status != 'cleaned' AND t.state NOT IN ('scheduled','published','needs_login')
                AND (t.next_retry='' OR t.next_retry<=?) ORDER BY t.video_id""", (stamp(),)).fetchall()
            return [r['video_id'] for r in rows]

    def required_platforms(self, video_id):
        with self.get_connection() as conn:
            row = conn.execute('SELECT platforms FROM daily_runs WHERE video_id=?', (video_id,)).fetchone()
            return json.loads(row['platforms']) if row else []

    def tasks_missing_links(self):
        with self.get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM posting_tasks WHERE state IN ('scheduled','published') AND post_url='' AND (next_retry='' OR next_retry<=?) ORDER BY updated_at LIMIT 10", (stamp(),))]

    def get_posting_health(self):
        run = self.get_daily_run()
        with self.get_connection() as conn:
            health = {r['name']:dict(r) for r in conn.execute('SELECT * FROM posting_health')}
            tasks = [dict(r) for r in conn.execute("SELECT * FROM posting_tasks WHERE state NOT IN ('scheduled','published') OR post_url='' OR video_id=? ORDER BY video_id,platform", (run['video_id'] if run else -1,))]
        reserve = self.reserve_count()
        return {'source':health.get('source',{'state':'unchecked','detail':'Chưa kiểm tra nguồn'}),
                'reserve':{'available':reserve,'target':7,'warning_below':3},'today':run,
                'tasks':tasks,'next_retry':min((t['next_retry'] for t in tasks if t['next_retry']),default=None),
                'complete':bool(run and set(run['platforms']).issubset(self.get_successful_platforms_for_video(run['video_id'])))}

    def find_content_duplicate(self, path, exclude_id=None):
        digest = sha256_file(path)
        with self.get_connection() as conn:
            candidates = conn.execute('SELECT id,file_path,content_sha256 FROM videos WHERE file_size=?', (os.path.getsize(path),)).fetchall()
            for row in candidates:
                if row['id']==exclude_id:
                    continue
                known = row['content_sha256']
                if not known and row['file_path'] and os.path.isfile(row['file_path']):
                    known = sha256_file(row['file_path'])
                    conn.execute('UPDATE videos SET content_sha256=? WHERE id=?',(known,row['id']))
                if known and known==digest:
                    return row['id']
        return None

    def set_content_hash(self, video_id, path):
        digest = sha256_file(path)
        with self.get_connection() as conn:
            conn.execute('UPDATE videos SET content_sha256=? WHERE id=?',(digest,video_id))
