# Tự Động Đăng Video — Quét HatBuiNho & Đăng Đa Nền Tảng

Hệ thống tự động tải video từ **HatBuiNho.com** và đăng lên **YouTube Shorts, TikTok, Facebook, Instagram**.

---

## Tải về và cài (khuyến nghị)

Tải file `.exe` bản mới nhất:

**https://github.com/ngonco/dangvideo/releases/latest**

1. Tải `Tu_dong_dang_video.exe`.
2. Click đúp để chạy. Dashboard mở tại `http://127.0.0.1:8000`.
3. Điền tài khoản HatBuiNho trên Dashboard, rồi **Mở Trình Duyệt Đăng Nhập** từng kênh (YouTube / TikTok / Facebook / Instagram) một lần.

Từ bản `v1.12.0`, ứng dụng tự kiểm tra GitHub Releases, tải bản mới có SHA-256 hợp lệ và cài ở lần mở ứng dụng tiếp theo. Người đang dùng bản cũ hơn cần tải `v1.12.0` thủ công một lần.

Cookie đăng nhập, `browser_profiles`, `.env`, `data.db` và mật khẩu **chỉ nằm trên máy bạn** — không đưa lên GitHub.

---

## Mã nguồn (không gồm .exe)

[Tải ZIP mã nguồn `main`](https://github.com/ngonco/dangvideo/archive/refs/heads/main.zip)

Sao chép [`_system/config.example.json`](_system/config.example.json) thành `_system/config.json` rồi điền tài khoản. Không commit `config.json`.

---

## Tính năng

- Tự kiểm tra để đăng ngay khi mở ứng dụng; nếu hôm nay chưa đăng thành công, tự thử lại mỗi 30 phút.
- Hẹn native công khai **10:00 sáng mai** trên YouTube, TikTok, Facebook.
- Instagram web: **Bài viết, Share ngay**, lấy permalink từ thanh địa chỉ.
- Hashtag đạo lý + hashtag phổ biến do AI chọn khi tải (không chữ ký thương hiệu).
- Tray icon, khởi động cùng Windows, dọn video cũ.

Tài liệu kỹ thuật: [`_system/SYSTEM_MAP.MD`](_system/SYSTEM_MAP.MD)

## Báo cáo lỗi chung lúc 08:00

Mỗi máy lưu lỗi tại chỗ và chuyển dữ liệu vào hộp thư gửi `binhyentram89@gmail.com`. Chỉ máy được chọn làm máy tổng hợp mới gửi **một email chung cho tất cả user lúc 08:00 giờ Việt Nam** đến quản trị viên. Lỗi giống nhau được gộp và đếm số lần; không gửi cảnh báo riêng từng lỗi và không còn báo cáo 22:00.

- Mọi máy cần cấu hình mật khẩu ứng dụng Gmail hợp lệ trong `email.smtp_password` của `_system/config.json` local hoặc biến `AUTO_VIDEO_SMTP_PASSWORD`.
- Chỉ máy tổng hợp đặt `email.coordinator_hostname` bằng đúng tên máy Windows. Các máy khác để trống. Máy tổng hợp cần truy cập được IMAP SSL cổng 993.
- Máy tổng hợp phải bật và có mạng. Mở sau 08:00 thì gửi bù một lần trong ngày; lỗi sau 08:00 hoặc đến muộn được gộp vào ngày kế tiếp. Không có lỗi thì không gửi.
- Các máy phải chạy phiên bản mới để chuyển lỗi vào hộp thư chung. Không sao chép mật khẩu hoặc dữ liệu local vào mã nguồn, GitHub hoặc file EXE.
