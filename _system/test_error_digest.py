import gc
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, Mock
from core.database import Database
from core.error_digest import EmailReporter, SENDER_EMAIL, RECEIVER_EMAIL


class ErrorDigestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(str(Path(self.temp.name)/'test.db'))
        self.reporter=EmailReporter(self.db)
        self.reporter.is_coordinator=Mock(return_value=True)
        self.reporter._send_raw_email=Mock(return_value=True)

    def tearDown(self):
        self.reporter=None
        self.db=None
        gc.collect()
        self.temp.cleanup()

    def event(self,user='user1',host='PC1',message='Upload failed',when='2026-10-24 23:00:00'):
        return dict(event_id=str(uuid.uuid4()),hbn_user=user,hostname=host,platform='tiktok',
            message=message,step='Schedule',details='<script>bad</script>',occurred_at=when)

    def test_records_without_immediate_email_and_survives_restart(self):
        with patch.object(self.reporter,'_smtp_send') as smtp:
            self.reporter.send_error_alert('facebook','fail')
            smtp.assert_not_called()
        other=EmailReporter(self.db)
        with other.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM error_events').fetchone()[0],1)

    def test_all_users_grouped_and_duplicate_transport_deduplicated(self):
        first=self.event()
        self.reporter._ingest([first,first,self.event(),self.event('user2','PC2')])
        self.assertFalse(self.reporter.send_daily_summary(datetime(2026,10,25,7,59)))
        self.assertTrue(self.reporter.send_daily_summary(datetime(2026,10,25,8)))
        self.reporter._send_raw_email.assert_called_once()
        body=self.reporter._send_raw_email.call_args.args[1]
        for value in ('user1','user2','PC1','PC2','<td>2</td>','&lt;script&gt;'):
            self.assertIn(value,body)
        self.assertNotIn('<script>',body)
        other=EmailReporter(self.db)
        other.is_coordinator=Mock(return_value=True)
        other._send_raw_email=Mock()
        self.assertFalse(other.send_daily_summary(datetime(2026,10,25,22)))
        other._send_raw_email.assert_not_called()

    def test_after_cutoff_and_late_arriving_errors_wait_for_next_day(self):
        self.reporter._ingest([self.event(),self.event(when='2026-10-25 08:00:00')])
        self.reporter.send_daily_summary(datetime(2026,10,25,9))
        self.reporter._ingest([self.event('offline-PC')])
        self.assertFalse(self.reporter.send_daily_summary(datetime(2026,10,25,22)))
        self.assertTrue(self.reporter.send_daily_summary(datetime(2026,10,26,8)))
        self.assertIn('offline-PC',self.reporter._send_raw_email.call_args.args[1])

    def test_failed_send_never_retries_same_day_and_preserves_errors(self):
        self.reporter._ingest([self.event()])
        self.reporter._send_raw_email.return_value=False
        self.assertFalse(self.reporter.send_daily_summary(datetime(2026,10,25,8)))
        self.assertFalse(self.reporter.send_daily_summary(datetime(2026,10,25,9)))
        self.reporter._send_raw_email.assert_called_once()
        self.reporter._send_raw_email.return_value=True
        self.assertTrue(self.reporter.send_daily_summary(datetime(2026,10,26,8)))

    def test_remote_machine_transports_only_to_collection_mailbox(self):
        self.reporter.is_coordinator.return_value=False
        self.reporter.send_error_alert('facebook','fail')
        with patch.object(self.reporter,'_smtp_send') as smtp:
            self.reporter.flush_outbox()
            message,recipient=smtp.call_args.args
            self.assertEqual(recipient,SENDER_EMAIL)
            self.assertNotEqual(recipient,RECEIVER_EMAIL)
            data=json.loads(next(message.iter_attachments()).get_payload(decode=True))
            self.assertEqual(len(data['events']),1)
            self.reporter.flush_outbox()
            smtp.assert_called_once()
        self.assertFalse(self.reporter.send_daily_summary(datetime(2026,10,25,8)))

    def test_mailbox_failure_does_not_send_partial_digest(self):
        self.reporter._ingest([self.event()])
        with patch.object(self.reporter,'collect_mailbox',side_effect=OSError('offline')):
            self.assertFalse(self.reporter.process_reports(datetime(2026,10,25,8)))
        self.reporter._send_raw_email.assert_not_called()

    def test_utc_clock_is_converted_to_vietnam(self):
        self.reporter._ingest([self.event()])
        self.assertTrue(self.reporter.send_daily_summary(datetime(2026,10,25,1,tzinfo=timezone.utc)))

    def test_mailbox_roundtrip_keeps_messages_unread_and_persists_cursor(self):
        remote=EmailReporter(self.db)
        remote.is_coordinator=Mock(return_value=False)
        remote.send_error_alert('tiktok','failed')
        with patch.object(remote,'_smtp_send') as send:
            remote.flush_outbox()
            raw=send.call_args.args[0].as_bytes()
        mailbox=Mock()
        mailbox.__enter__=Mock(return_value=mailbox)
        mailbox.__exit__=Mock(return_value=False)
        mailbox.select.return_value=('OK',[b'1'])
        mailbox.response.return_value=('UIDVALIDITY',[b'123'])
        mailbox.uid.side_effect=[('OK',[b'10']),('OK',[(b'10 (BODY[]',raw),b')'])]
        with patch('core.error_digest.imaplib.IMAP4_SSL',return_value=mailbox):
            self.assertTrue(self.reporter.collect_mailbox())
        mailbox.select.assert_called_once_with('INBOX',readonly=True)
        mailbox.uid.assert_any_call('fetch','10','(BODY.PEEK[])')
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM error_events').fetchone()[0],1)
        mailbox.uid.side_effect=[('OK',[b'10'])]
        with patch('core.error_digest.imaplib.IMAP4_SSL',return_value=mailbox):
            self.assertTrue(self.reporter.collect_mailbox())
        self.assertIn('11:*',mailbox.uid.call_args.args)


if __name__=='__main__':
    unittest.main()
