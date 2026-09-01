# 🚀 Tự Động Đăng Video — Quét HatBuiNho & Đăng Đa Nền Tảng

> Hệ thống tự động hóa thông minh: Quét & tải video từ **HatBuiNho.com**, tự động sinh **Hashtag Đạo Lý & Phật Pháp**, và phân phối đăng tải lên đồng thời **YouTube Shorts, TikTok, Facebook Reels, Instagram Reels**.

---

## ⚡ HƯỚNG DẪN CÀI ĐẶT & CHẠY 1-CLICK

### 🌟 Cách 1: Chạy trực tiếp qua file thực thi (Khuyến nghị)
Sau khi tải mã nguồn hoặc bản phát hành:
👉 **Click đúp vào file `Tu_dong_dang_video.exe` (hoặc `run.bat`)**
- 🌐 Tự động mở Giao diện Web Dashboard tại `http://127.0.0.1:8000`.
- 📌 Xuất hiện biểu tượng **System Tray Icon** ở khay hệ thống (góc phải dưới màn hình).
- 🖱️ **Click đúp vào Tray Icon** để mở lại giao diện bất kỳ lúc nào.
- 🖱️ **Chuột phải vào Tray Icon** để mở Menu: *Mở Bảng Điều Khiển*, *Khởi Động Cùng Windows*, *Kiểm Tra Cập Nhật*, *Thoát*.

---

### 📦 Cách 2: Tải trực tiếp file ZIP mã nguồn mới nhất từ GitHub
👉 **[Tải xuống tệp ZIP bản mới nhất từ GitHub](https://github.com/ngonco/dangvideo/archive/refs/heads/main.zip)**

**Sau khi tải về:**
1. Giải nén file `.zip`.
2. Click đúp vào file 👉 **`Tu_dong_dang_video.exe`** hoặc **`run.bat`** để sử dụng ngay!

---

### ⚡ Cách 3: Lệnh PowerShell cài đặt tự động 1 dòng lệnh
Mở **PowerShell** trên máy tính và dán lệnh:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-RestMethod https://raw.githubusercontent.com/ngonco/dangvideo/main/quick_install.ps1 | Invoke-Expression"
```

---

## 🌟 Tính Năng Nổi Bật

1. **System Tray Icon & Chạy Ngầm**:
   - Biểu tượng khay hệ thống thông minh giúp quản lý trạng thái máy chủ, khởi động cùng Windows và mở nhanh Dashboard.
2. **Quét & Tải Tự Động Từ HatBuiNho.com**:
   - Quét video mới chưa tải, hỗ trợ chế độ Test ép tải, bóc tách tiêu đề sạch.
3. **Bộ Sinh Hashtag Đạo Lý & Phật Pháp Thông Minh**:
   - Tự động sinh ngẫu nhiên hashtag bài học cuộc sống, luật nhân quả (`#luatnhanqua`, `#loiphatday`, `#tutaptaigia`...).
4. **Đăng Tải 4 Nền Tảng Đồng Thời**:
   - **YouTube Shorts**: Audience, AI label, Unlisted, trích xuất link shorts thực tế.
   - **TikTok Creator**: Xóa joyride tour, AI label, Only you.
   - **Facebook Reels**: Feed dialog, Only me.
   - **Instagram Reels**: Native FileChooser, đóng dialog Reels notice, chia sẻ bài đăng.
5. **Tự Động Khởi Động Cùng Windows (Auto-Start)**:
   - Tự động chạy ngầm cùng Windows để đảm bảo lịch đăng giờ vàng.
6. **Tự Động Dọn Dẹp Video Cũ Sau 2 Ngày**:
   - Tự dọn dẹp các file `.mp4` cũ trong `downloads/` mà vẫn bảo toàn 100% lịch sử và đường dẫn bài đăng.

---

## 📖 Tài Liệu Kỹ Thuật Chi Tiết
Vui lòng đọc kỹ tài liệu kiến trúc và quy tắc bảo trì tại:
👉 **[`SYSTEM_MAP.MD`](./SYSTEM_MAP.MD)**
