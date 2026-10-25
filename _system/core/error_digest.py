"""Durable mailbox outbox and one daily digest across all installations."""
import html
import imaplib
import json
import os
import smtplib
import socket
import threading
import uuid
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr
from core.logger import logger
from core.config_manager import config_mgr
from core.database import db
from core.posting_store import local_now, stamp, VIETNAM

SENDER_EMAIL='binhyentram89@gmail.com'
RECEIVER_EMAIL='thv.vinh@gmail.com'
BATCH_SUBJECT='[AUTO_VIDEO_ERROR_BATCH_V1]'
FIELDS={'event_id':36,'hbn_user':250,'hostname':250,'platform':100,
        'message':4000,'step':1000,'details':8000,'occurred_at':19}


class EmailReporter:
    def __init__(self,database=None):
        self.db=database or db
        self._lock=threading.Lock()
        with self.db.get_connection() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS error_events (
                    event_id TEXT PRIMARY KEY,hbn_user TEXT NOT NULL,hostname TEXT NOT NULL,
                    platform TEXT NOT NULL,message TEXT NOT NULL,step TEXT NOT NULL,
                    details TEXT NOT NULL,occurred_at TEXT NOT NULL,
                    delivered INTEGER NOT NULL DEFAULT 0,report_day TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS error_digest_runs (
                    report_day TEXT PRIMARY KEY,state TEXT NOT NULL,created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS error_mail_cursor (
                    mailbox TEXT PRIMARY KEY,validity TEXT NOT NULL,last_uid INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_error_events_pending ON error_events(report_day,occurred_at);
                CREATE INDEX IF NOT EXISTS idx_error_events_outbox ON error_events(delivered,occurred_at);
            ''')

    def get_identity(self):
        return {'hbn_user':config_mgr.get('hatbuinho',{}).get('username') or 'User_Mac_Dinh',
                'hostname':socket.gethostname()}

    def is_coordinator(self):
        host=config_mgr.get('email',{}).get('coordinator_hostname','')
        return bool(host and host.casefold()==socket.gethostname().casefold())

    def _password(self):
        return config_mgr.get('email',{}).get('smtp_password') or os.environ.get('AUTO_VIDEO_SMTP_PASSWORD','')

    def _redact(self,value,limit):
        text=str(value or '')
        for secret in (self._password(),config_mgr.get('hatbuinho',{}).get('password'),os.environ.get('VILAO_API_KEY')):
            if secret:
                text=text.replace(secret,'[REDACTED]')
        return text[:limit]

    def _smtp_send(self,message,recipient):
        with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=20) as server:
            server.login(SENDER_EMAIL,self._password())
            if server.send_message(message,from_addr=SENDER_EMAIL,to_addrs=[recipient]):
                raise RuntimeError('SMTP từ chối người nhận')

    def _send_raw_email(self,subject,html_body):
        try:
            message=EmailMessage()
            message['Subject'],message['From'],message['To']=subject,SENDER_EMAIL,RECEIVER_EMAIL
            message.set_content('Báo cáo tự động đăng video. Xem nội dung HTML trong email.')
            message.add_alternative(html_body,subtype='html')
            self._smtp_send(message,RECEIVER_EMAIL)
            logger.info('Đã gửi email tổng hợp tới quản trị viên.','EMAIL')
            return True
        except Exception as exc:
            logger.warning(f'Chưa gửi được báo cáo email: {type(exc).__name__}','EMAIL')
            return False

    def send_error_alert(self,platform,error_message,step='',details=''):
        """Persist every occurrence. No immediate admin email."""
        identity=self.get_identity()
        with self.db.get_connection() as conn:
            conn.execute('''INSERT INTO error_events
                (event_id,hbn_user,hostname,platform,message,step,details,occurred_at) VALUES (?,?,?,?,?,?,?,?)''',
                (str(uuid.uuid4()),identity['hbn_user'],identity['hostname'],str(platform)[:100],
                 self._redact(error_message,4000),self._redact(step,1000),self._redact(details,8000),stamp()))

    def _ingest(self,events):
        if not isinstance(events,list) or len(events)>250:
            raise ValueError('Invalid error batch')
        with self.db.get_connection() as conn:
            for event in events:
                if not isinstance(event,dict) or any(not isinstance(event.get(key),str) for key in FIELDS):
                    raise ValueError('Invalid event fields')
                uuid.UUID(event['event_id'])
                datetime.strptime(event['occurred_at'],'%Y-%m-%d %H:%M:%S')
                values=[str(event[key])[:limit] for key,limit in FIELDS.items()]
                conn.execute('''INSERT OR IGNORE INTO error_events
                    (event_id,hbn_user,hostname,platform,message,step,details,occurred_at,delivered)
                    VALUES (?,?,?,?,?,?,?,?,1)''',values)

    def flush_outbox(self):
        if self.is_coordinator():
            with self.db.get_connection() as conn:
                conn.execute('UPDATE error_events SET delivered=1 WHERE delivered=0')
            return
        with self.db.get_connection() as conn:
            rows=[dict(r) for r in conn.execute('SELECT * FROM error_events WHERE delivered=0 ORDER BY occurred_at LIMIT 250')]
        if not rows:
            return
        message=EmailMessage()
        message['Subject'],message['From'],message['To']=BATCH_SUBJECT,SENDER_EMAIL,SENDER_EMAIL
        message.set_content('Dữ liệu lỗi nội bộ để tổng hợp lúc 08:00. Không phải báo cáo quản trị.')
        payload=json.dumps({'version':1,'events':[{k:r[k] for k in FIELDS} for r in rows]},ensure_ascii=False)
        message.add_attachment(payload.encode('utf-8'),maintype='application',subtype='json',filename='errors.json')
        self._smtp_send(message,SENDER_EMAIL)
        with self.db.get_connection() as conn:
            conn.executemany('UPDATE error_events SET delivered=1 WHERE event_id=?',[(r['event_id'],) for r in rows])

    def collect_mailbox(self):
        with imaplib.IMAP4_SSL('imap.gmail.com',993,timeout=20) as mailbox:
            mailbox.login(SENDER_EMAIL,self._password())
            status,_=mailbox.select('INBOX',readonly=True)
            if status!='OK':
                raise RuntimeError('Không mở được hộp thư nhận lỗi')
            validity=str(mailbox.response('UIDVALIDITY')[1])
            with self.db.get_connection() as conn:
                cursor=conn.execute('SELECT * FROM error_mail_cursor WHERE mailbox=?',(SENDER_EMAIL,)).fetchone()
            last=cursor['last_uid'] if cursor and cursor['validity']==validity else 0
            status,data=mailbox.uid('search',None,'UID',f'{last+1}:*','HEADER','Subject',f'"{BATCH_SUBJECT}"')
            if status!='OK':
                raise RuntimeError('Không đọc được danh sách lỗi')
            uids=sorted(int(uid) for uid in data[0].split() if int(uid)>last)
            for uid in uids[:500]:
                status,fetched=mailbox.uid('fetch',str(uid),'(BODY.PEEK[])')
                if status!='OK':
                    raise RuntimeError('Không tải được dữ liệu lỗi')
                raw=next((part[1] for part in fetched if isinstance(part,tuple)),b'')
                if not raw:
                    raise RuntimeError('Email lỗi trống')
                try:
                    if len(raw)>6_000_000:
                        raise ValueError('Batch too large')
                    message=BytesParser(policy=policy.default).parsebytes(raw)
                    if str(message['Subject'])!=BATCH_SUBJECT or parseaddr(message['From'])[1].casefold()!=SENDER_EMAIL:
                        raise ValueError('Invalid sender or subject')
                    for part in message.iter_attachments():
                        if part.get_filename()=='errors.json':
                            payload=json.loads(part.get_payload(decode=True))
                            if not isinstance(payload,dict) or payload.get('version')!=1:
                                raise ValueError('Unknown version')
                            self._ingest(payload['events'])
                except (ValueError,KeyError,TypeError):
                    logger.warning(f'Bỏ qua dữ liệu báo lỗi không hợp lệ, UID {uid}.','EMAIL')
                with self.db.get_connection() as conn:
                    conn.execute('INSERT OR REPLACE INTO error_mail_cursor VALUES (?,?,?)',(SENDER_EMAIL,validity,uid))
            return len(uids)<=500

    def process_reports(self,now=None):
        if not self._lock.acquire(blocking=False):
            return False
        try:
            self.flush_outbox()
            if not self.is_coordinator():
                return False
            complete=self.collect_mailbox()
            return self.send_daily_summary(now) if complete else False
        except Exception as exc:
            logger.warning(f'Chưa đồng bộ hộp thư báo lỗi; sẽ thử lại: {type(exc).__name__}','EMAIL')
            return False
        finally:
            self._lock.release()

    def send_daily_summary(self,now=None):
        now=now or local_now()
        if now.tzinfo is not None:
            now=now.astimezone(VIETNAM).replace(tzinfo=None)
        if not self.is_coordinator() or now.hour<8:
            return False
        day=now.strftime('%Y-%m-%d')
        cutoff=day+' 08:00:00'
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # A previous interrupted send may be included next day, never twice today.
            conn.execute("""UPDATE error_events SET report_day='' WHERE report_day < ? AND report_day!=''
                AND report_day IN (SELECT report_day FROM error_digest_runs WHERE state!='sent')""",(day,))
            if conn.execute('SELECT 1 FROM error_digest_runs WHERE report_day=?',(day,)).fetchone():
                return False
            rows=conn.execute('''SELECT hbn_user,hostname,platform,message,step,MAX(details) details,
                COUNT(*) occurrences,MIN(occurred_at) first_seen,MAX(occurred_at) last_seen
                FROM error_events WHERE report_day='' AND occurred_at < ?
                GROUP BY hbn_user,hostname,platform,message,step ORDER BY hbn_user,hostname,platform''',(cutoff,)).fetchall()
            if not rows:
                return False
            # Reserve before SMTP; never repeat an ambiguous send on the same day.
            conn.execute('INSERT INTO error_digest_runs VALUES (?,?,?)',(day,'sending',stamp(now)))
            conn.execute("UPDATE error_events SET report_day=? WHERE report_day='' AND occurred_at < ?",(day,cutoff))
        esc=lambda value:html.escape(str(value or ''),quote=True)
        table=''.join(f"<tr><td>{esc(r['hbn_user'])}<br>{esc(r['hostname'])}</td><td>{esc(r['platform'])}</td>"
            f"<td>{esc(r['message'])}<br>{esc(r['step'])}<pre>{esc(r['details'])}</pre></td>"
            f"<td>{r['occurrences']}</td><td>{esc(r['first_seen'])}<br>{esc(r['last_seen'])}</td></tr>" for r in rows)
        body=f'''<html><body><h2>Báo cáo lỗi tất cả user — {day}, 08:00 (Việt Nam)</h2>
            <p>Các lỗi chưa báo cáo trước 08:00; lỗi lặp được gộp và đếm số lần.</p>
            <table border="1" cellpadding="8"><tr><th>User / Máy</th><th>Kênh</th><th>Lỗi / Bước / Chi tiết</th>
            <th>Số lần</th><th>Đầu / Cuối</th></tr>{table}</table></body></html>'''
        success=self._send_raw_email(f'[BÁO CÁO LỖI TẤT CẢ USER] {day} — 08:00',body)
        with self.db.get_connection() as conn:
            conn.execute('UPDATE error_digest_runs SET state=? WHERE report_day=?',('sent' if success else 'uncertain',day))
            if not success:
                conn.execute("UPDATE error_events SET report_day='' WHERE report_day=?",(day,))
        return success

    def send_test_email(self):
        return self._send_raw_email('[KIỂM THỬ] Kết nối báo cáo lỗi',
            '<p>Kết nối thành công. Các máy chuyển lỗi vào hộp thư chung; máy tổng hợp gửi một báo cáo lúc 08:00 giờ Việt Nam.</p>')
