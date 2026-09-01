# 🚀 Auto Video Pro — Tự Động Quét/Tải HatBuiNho & Đăng Đa Nền Tảng

> Hệ thống tự động hóa thông minh: Quét & tải video từ **HatBuiNho.com**, tự động sinh **Hashtag Đạo Lý & Phật Pháp**, và phân phối đăng tải lên đồng thời **YouTube Shorts, TikTok, Facebook Reels, Instagram Reels**.

---

## ⚡ LINK TẢI CÔNG KHAI & CÀI ĐẶT NHANH (LUÔN LÀ BẢN MỚI NHẤT)

### 🌟 Cách 1: Cài đặt tự động siêu tốc 1 dòng lệnh (Khuyến nghị)
Mở **PowerShell** trên bất kỳ máy tính Windows nào và dán dòng lệnh sau rồi nhấn Enter:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://raw.githubusercontent.com/ngonco/dangvideo/main/quick_install.ps1 | Invoke-Expression"
```

*(Lệnh trên sẽ tự động: Tải bản mới nhất -> Giải nén vào thư mục `Auto_Video_Pro` -> Cài đặt thư viện -> Tạo Shortcut Màn hình Desktop -> Bật tự động khởi động cùng Windows -> Mở phần mềm ngay!)*

---

### 📦 Cách 2: Tải trực tiếp file ZIP mã nguồn mới nhất
👉 **[Tải xuống tệp ZIP bản mới nhất từ GitHub](https://github.com/ngonco/dangvideo/archive/refs/heads/main.zip)**

**Sau khi tải về:**
1. Giải nén file `.zip`.
2. Chạy file 👉 **`install.bat`** *(Cài đặt môi trường 1-click)*.
3. Chạy file 👉 **`run.bat`** *(Khởi động phần mềm & mở Web Dashboard tại `http://127.0.0.1:8000`)*.

---

## 🌟 Tính Năng Nổi Bật

1. **Quét & Tải Tự Động Từ HatBuiNho.com**:
   - Quét các video mới nhất có trạng thái *Chưa tải xuống*.
   - Hỗ trợ chế độ TEST ép tải video đầu tiên kể cả khi đã có trạng thái *Đã tải xuống*.
   - Tự động bóc tách tiêu đề hoàn chỉnh không bị ngắt cụt từ.
2. **Bộ Sinh Hashtag Đạo Lý & Phật Pháp Thông Minh**:
   - Tự động sinh ngẫu nhiên các bộ hashtag đạo lý, triết lý nhân quả, bài học cuộc sống (`#luatnhanqua`, `#loiphatday`, `#tutaptaigia`, `#chualanh`...).
3. **Đăng Tải Đa Nền Tảng Đồng Thời (4 Kênh)**:
   - **YouTube Shorts**: Tự động đặt nhãn *Not made for kids*, *AI use -> Yes*, chế độ *Unlisted* và trích xuất link dạng `https://youtube.com/shorts/<ID>`.
   - **TikTok Creator**: Xóa bỏ lớp phủ tour hướng dẫn `react-joyride`, bật nhãn AI, chọn chế độ *Chỉ mình tôi (Only you)*.
   - **Facebook Reels**: Tự động đính kèm video, điền caption/hashtags, đặt chế độ *Chỉ mình tôi (Only me)*.
   - **Instagram Reels**: Tự động vượt qua popup thông báo Reels, sử dụng Native FileChooser, chia sẻ bài đăng.
4. **Tự Động Cập Nhật Đa Máy (Auto-Updater)**:
   - Tự động kiểm tra và kéo bản mới từ GitHub mỗi khi khởi động qua `run.bat`.
   - Nút **"🔄 Cập Nhật Mã Nguồn"** trực tiếp 1-click trên Web Dashboard.
5. **Tự Động Khởi Động Cùng Windows (Auto-Start)**:
   - Chạy ngầm êm ái khi mở máy tính để đảm bảo đúng giờ vàng đăng video.
   - Bật/Tắt dễ dàng bằng công tắc trên Web Dashboard hoặc qua file `enable_autostart.bat` / `disable_autostart.bat`.
6. **Dọn Dẹp Ổ Cứng Tự Động Sau 2 Ngày**:
   - Tự động xóa các file `.mp4` cũ trong thư mục `downloads/` mà vẫn bảo toàn 100% lịch sử và đường dẫn bài đăng trong Database.
7. **Bản Đóng Gói Portable (Python Embedded)**:
   - Chạy file `package_portable.bat` để tạo ra bản chạy ngay không cần cài đặt Python.

---

## 📖 Tài Liệu Kỹ Thuật Chi Tiết
Vui lòng đọc kỹ tài liệu kiến trúc và quy tắc bảo trì tại:
👉 **[`SYSTEM_MAP.MD`](./SYSTEM_MAP.MD)**
