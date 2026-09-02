import os
import sys
import socket
import smtplib
import threading
import traceback
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List, Dict, Any

from core.logger import logger
from core.config_manager import config_mgr, ROOT_DIR, SYSTEM_DIR
from core.database import db

# Cấu hình SMTP Gmail mặc định
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = "binhyentram89@gmail.com"
SENDER_PASSWORD = "lddpyebeszvnbpss"
RECEIVER_EMAIL = "thv.vinh@gmail.com"

class EmailReporter:
    def __init__(self):
        self._last_errors: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get_identity(self) -> Dict[str, str]:
        """Lấy thông tin định danh máy tính và tài khoản user"""
        hbn_user = config_mgr.get("hatbuinho", {}).get("username", "Chua_dat_ten")
        if not hbn_user:
            hbn_user = "User_Mac_Dinh"
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "LAPTOP-UNKNOWN"
        return {
            "hbn_user": hbn_user,
            "hostname": hostname
        }

    def _send_raw_email(self, subject: str, html_body: str) -> bool:
        """Gửi email qua giao thức Gmail SMTP SSL (chạy đồng bộ trong thread riêng)"""
        try:
            identity = self.get_identity()
            sender_name = f"Tự Động Đăng Video [{identity['hbn_user']} | {identity['hostname']}]"
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{sender_name} <{SENDER_EMAIL}>"
            msg['To'] = RECEIVER_EMAIL
            
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            
            logger.info(f"Đã gửi email báo cáo thành công tới {RECEIVER_EMAIL}: {subject}", "EMAIL")
            return True
        except Exception as ex:
            logger.warning(f"Lỗi khi gửi email báo cáo ({RECEIVER_EMAIL}): {ex}", "EMAIL")
            return False

    def send_email_async(self, subject: str, html_body: str):
        """Gửi email bất đồng bộ trong thread nền để không làm nghẽn tiến trình đăng bài"""
        threading.Thread(
            target=self._send_raw_email,
            args=(subject, html_body),
            daemon=True
        ).start()

    def send_error_alert(self, platform: str, error_message: str, step: str = "", details: str = ""):
        """
        GỬI CẢNH BÁO LỖI KHẨN CẤP NGAY LẬP TỨC
        Tự động kích hoạt khi có lỗi xảy ra ở bất kỳ nền tảng nào
        """
        now = datetime.now()
        now_str = now.strftime("%d/%m/%Y %H:%M:%S")
        identity = self.get_identity()

        # Chống spam: Nếu cùng một lỗi xảy ra trong vòng 10 phút thì bỏ qua
        error_key = f"{platform}_{error_message}"
        with self._lock:
            last_time = self._last_errors.get(error_key, 0)
            if now.timestamp() - last_time < 600:
                logger.info(f"Bỏ qua gửi email lặp lại cho lỗi: {error_key}", "EMAIL")
                return
            self._last_errors[error_key] = now.timestamp()

        subject = f"🚨 [CẢNH BÁO LỖI] Máy: {identity['hbn_user']} ({identity['hostname']}) — Lỗi {platform.upper()}"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, Helvetica, sans-serif; background-color: #F7F4EE; padding: 20px; color: #2C1810; }}
                .container {{ max-width: 650px; margin: 0 auto; background: #FFFFFF; border: 2px solid #E2D9CF; border-radius: 12px; padding: 24px; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }}
                .header {{ border-bottom: 2px dashed #E2D9CF; padding-bottom: 16px; margin-bottom: 20px; }}
                .title {{ color: #C62828; font-size: 22px; font-weight: bold; margin: 0; }}
                .meta-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
                .meta-table td {{ padding: 10px 12px; border-bottom: 1px solid #F0EAE1; font-size: 14px; }}
                .meta-label {{ font-weight: bold; color: #5C4A42; width: 140px; background: #FAF8F5; }}
                .error-box {{ background: #FFEBEE; border: 1px solid #EF9A9A; border-radius: 8px; padding: 14px; color: #B71C1C; font-weight: bold; margin: 16px 0; font-size: 15px; }}
                .detail-box {{ background: #2C1810; color: #FFCDD2; padding: 14px; border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; overflow-x: auto; white-space: pre-wrap; }}
                .footer {{ margin-top: 24px; font-size: 12px; color: #7A6961; text-align: center; border-top: 1px solid #E2D9CF; padding-top: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 class="title">🚨 CẢNH BÁO LỖI HỆ THỐNG ĐĂNG VIDEO</h2>
                    <p style="margin: 4px 0 0 0; color: #5C4A42; font-size: 14px;">Hệ thống phát hiện sự cố trên máy của người dùng.</p>
                </div>

                <table class="meta-table">
                    <tr>
                        <td class="meta-label">👤 Tài Khoản User:</td>
                        <td><b style="color: #2E7D32; font-size: 15px;">{identity['hbn_user']}</b></td>
                    </tr>
                    <tr>
                        <td class="meta-label">💻 Tên Máy Tính:</td>
                        <td><b>{identity['hostname']}</b></td>
                    </tr>
                    <tr>
                        <td class="meta-label">⏰ Thời Gian Lỗi:</td>
                        <td>{now_str}</td>
                    </tr>
                    <tr>
                        <td class="meta-label">🌐 Nền Tảng:</td>
                        <td><b style="color: #D84315;">{platform.upper()}</b></td>
                    </tr>
                    {f"<tr><td class='meta-label'>📍 Bước Thực Hiện:</td><td>{step}</td></tr>" if step else ""}
                </table>

                <div class="error-box">
                    ⚠️ Nội Dung Sự Cố: {error_message}
                </div>

                {f'''
                <div style="margin-top: 14px;">
                    <b style="color: #5C4A42; font-size: 13px;">Chi Tiết Kỹ Thuật (Traceback):</b>
                    <div class="detail-box">{details}</div>
                </div>
                ''' if details else ""}

                <div class="footer">
                    🌿 Báo cáo tự động từ phần mềm Tự Động Đăng Video — Người nhận: {RECEIVER_EMAIL}
                </div>
            </div>
        </body>
        </html>
        """

        self.send_email_async(subject, html_body)

    def send_daily_summary(self):
        """
        GỬI BÁO CÁO TỔNG KẾT VIDEO ĐÃ ĐĂNG HÀNG NGÀY
        Tự động chạy vào 22:00 mỗi ngày để gửi bảng tổng hợp cho Admin
        """
        now = datetime.now()
        today_date = now.strftime("%d/%m/%Y")
        identity = self.get_identity()

        # Truy vấn lịch sử đăng trong ngày từ database
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT v.title, ph.platform, ph.post_url, ph.status, ph.error_message, ph.posted_at 
                    FROM post_history ph
                    LEFT JOIN videos v ON ph.video_id = v.id
                    WHERE DATE(ph.posted_at) = DATE('now', 'localtime') 
                    ORDER BY ph.id DESC
                """)
                rows = cursor.fetchall()
        except Exception as ex:
            rows = []
            logger.warning(f"Lỗi truy vấn lịch sử đăng ngày: {ex}", "EMAIL")

        total_posts = len(rows)
        success_posts = sum(1 for r in rows if r[3] == "success")
        failed_posts = sum(1 for r in rows if r[3] == "failed")

        subject = f"📊 [BÁO CÁO NGÀY {today_date}] Máy: {identity['hbn_user']} — Đã đăng {success_posts}/{total_posts} bài viết"

        # Tạo bảng danh sách video HTML
        if rows:
            table_rows_html = ""
            for idx, r in enumerate(rows, 1):
                title, platform, url, status, error, created_at = r
                status_badge = "<span style='color: #2E7D32; font-weight: bold;'>🟢 Thành Công</span>" if status == "success" else f"<span style='color: #C62828; font-weight: bold;'>❌ Thất Bại</span> ({error or ''})"
                
                if url and url.startswith("http"):
                    link_html = f"<a href='{url}' target='_blank' style='color: #1565C0; font-weight: bold; text-decoration: underline;'>Xem Bài Viết ↗</a>"
                else:
                    link_html = "<span style='color: #7A6961;'>-</span>"

                table_rows_html += f"""
                <tr style="border-bottom: 1px solid #E2D9CF;">
                    <td style="padding: 10px; text-align: center;">{idx}</td>
                    <td style="padding: 10px; font-weight: bold; color: #2C1810;">{title or 'Video Đạo Lý Hay'}</td>
                    <td style="padding: 10px; text-align: center; text-transform: uppercase; font-weight: bold;">{platform}</td>
                    <td style="padding: 10px; text-align: center;">{created_at or ''}</td>
                    <td style="padding: 10px; text-align: center;">{status_badge}</td>
                    <td style="padding: 10px; text-align: center;">{link_html}</td>
                </tr>
                """
        else:
            table_rows_html = """
            <tr>
                <td colspan="6" style="padding: 24px; text-align: center; color: #7A6961; font-style: italic;">
                    Hôm nay chưa có video nào được đăng từ máy này.
                </td>
            </tr>
            """

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, Helvetica, sans-serif; background-color: #F7F4EE; padding: 20px; color: #2C1810; }}
                .container {{ max-width: 800px; margin: 0 auto; background: #FFFFFF; border: 2px solid #E2D9CF; border-radius: 12px; padding: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }}
                .header {{ border-bottom: 2px dashed #E2D9CF; padding-bottom: 16px; margin-bottom: 20px; }}
                .title {{ color: #2E7D32; font-size: 22px; font-weight: bold; margin: 0; }}
                .stats-grid {{ display: table; width: 100%; margin: 16px 0; }}
                .stat-box {{ display: table-cell; width: 33%; padding: 14px; text-align: center; border-radius: 8px; }}
                .stat-num {{ font-size: 24px; font-weight: bold; display: block; }}
                .stat-label {{ font-size: 13px; font-weight: bold; margin-top: 4px; }}
                .table-main {{ width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 13px; }}
                .table-main th {{ background: #FAF8F5; padding: 12px; border-bottom: 2px solid #E2D9CF; color: #5C4A42; text-align: left; }}
                .footer {{ margin-top: 28px; font-size: 12px; color: #7A6961; text-align: center; border-top: 1px solid #E2D9CF; padding-top: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 class="title">📊 BÁO CÁO TỔNG KẾT ĐĂNG VIDEO NGÀY {today_date}</h2>
                    <p style="margin: 4px 0 0 0; color: #5C4A42; font-size: 14px;">Báo cáo hoạt động tự động từ máy tính người dùng.</p>
                </div>

                <div style="background: #FAF8F5; padding: 12px 16px; border-radius: 8px; border: 1px solid #E2D9CF; margin-bottom: 16px;">
                    <p style="margin: 4px 0;">👤 <b>Tài Khoản User:</b> <span style="color: #2E7D32; font-weight: bold;">{identity['hbn_user']}</span></p>
                    <p style="margin: 4px 0;">💻 <b>Tên Máy Tính:</b> {identity['hostname']}</p>
                    <p style="margin: 4px 0;">📅 <b>Ngày Báo Cáo:</b> {today_date}</p>
                </div>

                <div class="stats-grid">
                    <div class="stat-box" style="background: #E8F5E9; border: 1px solid #A5D6A7; color: #2E7D32;">
                        <span class="stat-num">{success_posts}</span>
                        <span class="stat-label">ĐĂNG THÀNH CÔNG</span>
                    </div>
                    <div class="stat-box" style="background: #FFEBEE; border: 1px solid #EF9A9A; color: #C62828; margin: 0 10px;">
                        <span class="stat-num">{failed_posts}</span>
                        <span class="stat-label">BÀI ĐĂNG THẤT BẠI</span>
                    </div>
                    <div class="stat-box" style="background: #EFEBE9; border: 1px solid #D7CCC8; color: #5D4037;">
                        <span class="stat-num">{total_posts}</span>
                        <span class="stat-label">TỔNG SỐ LƯỢT ĐĂNG</span>
                    </div>
                </div>

                <h3 style="color: #2C1810; margin-top: 24px; font-size: 16px;">📋 Danh Sách Chi Tiết Các Video Đã Đăng:</h3>
                <table class="table-main">
                    <thead>
                        <tr>
                            <th style="text-align: center;">STT</th>
                            <th>Tiêu Đề Video</th>
                            <th style="text-align: center;">Kênh</th>
                            <th style="text-align: center;">Thời Gian</th>
                            <th style="text-align: center;">Trạng Thái</th>
                            <th style="text-align: center;">Link Bài Viết</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows_html}
                    </tbody>
                </table>

                <div class="footer">
                    🌿 Báo cáo tự động từ phần mềm Tự Động Đăng Video — Người nhận: {RECEIVER_EMAIL}
                </div>
            </div>
        </body>
        </html>
        """

        self.send_email_async(subject, html_body)

    def send_test_email(self) -> bool:
        """Gửi email kiểm thử tức thì"""
        identity = self.get_identity()
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        subject = f"🌿 [KIỂM THỬ KẾT NỐI] Máy: {identity['hbn_user']} ({identity['hostname']}) đã sẵn sàng báo cáo Email!"
        
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; padding: 20px; border: 2px solid #E2D9CF; border-radius: 12px; background: #F7F4EE; color: #2C1810;">
            <h2 style="color: #2E7D32;">🌿 KẾT NỐI BÁO CÁO EMAIL THÀNH CÔNG!</h2>
            <p style="font-size: 15px;">Hệ thống <b>Tự Động Đăng Video</b> trên máy người dùng đã kết nối thành công với hộp thư quản trị viên của bạn.</p>
            <div style="background: #FFFFFF; padding: 15px; border-radius: 8px; margin: 15px 0; border: 1px solid #E2D9CF;">
                <p style="margin: 6px 0;">👤 <b>Tài Khoản User:</b> <span style="color: #2E7D32; font-weight: bold;">{identity['hbn_user']}</span></p>
                <p style="margin: 6px 0;">💻 <b>Tên Máy Tính:</b> {identity['hostname']}</p>
                <p style="margin: 6px 0;">⏰ <b>Thời Gian Kiểm Thử:</b> {now_str}</p>
                <p style="margin: 6px 0;">📧 <b>Email Nhận Báo Cáo:</b> {RECEIVER_EMAIL}</p>
            </div>
            <p style="font-size: 13px; color: #5C4A42;">Từ bây giờ, hệ thống sẽ <b>tự động gửi cảnh báo khẩn cấp khi có lỗi</b> và <b>gửi báo cáo tổng hợp video đã đăng vào 22:00 mỗi ngày</b>.</p>
        </div>
        """
        return self._send_raw_email(subject, html_body)

email_reporter = EmailReporter()
