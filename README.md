# 🚀 Auto Video Pro — Tự Động Quét/Tải HatBuiNho & Đăng Đa Nền Tảng

> Hệ thống tự động hóa thông minh: Quét & tải video từ **HatBuiNho.com**, tự động sinh **Hashtag Đạo Lý & Phật Pháp**, và phân phối đăng tải lên đồng thời **YouTube Shorts, TikTok, Facebook Reels, Instagram Reels**.

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
5. **Dọn Dẹp Ổ Cứng Tự Động Sau 2 Ngày**:
   - Tự động xóa các file `.mp4` cũ trong thư mục `downloads/` mà vẫn bảo toàn 100% lịch sử và đường dẫn bài đăng trong Database.
6. **Bảo Mật Quyền Riêng Tư Tuyệt Đối**:
   - Không đồng bộ cookie cá nhân, file video nặng hoặc database lên Git (được bảo vệ qua `.gitignore`).

---

## 🛠️ Hướng Dẫn Cài Đặt & Chạy Trên Máy Mới

### Bước 1: Tải mã nguồn về máy tính mới
Mở Command Prompt (cmd) hoặc Terminal và chạy lệnh:
```bash
git clone https://github.com/ngonco/dangvideo.git
cd dangvideo
```

### Bước 2: Cài đặt môi trường (1-Click)
Chạy file:
👉 **`install.bat`**  
*(Script sẽ tự động cài đặt các thư viện Python từ `requirements.txt` và trình duyệt Playwright Chromium)*.

### Bước 3: Khởi động và sử dụng
Chạy file:
👉 **`run.bat`**  
*(Hệ thống sẽ tự động kiểm tra bản cập nhật mới từ GitHub, khởi động server và mở giao diện Web tại `http://127.0.0.1:8000`)*.

---

## 🔄 Cách Cập Nhật Phần Mềm Khi Có Bản Mới

- **Cách 1:** Chỉ cần khởi động lại file **`run.bat`** (hệ thống sẽ tự động cập nhật).
- **Cách 2:** Bấm nút **"🔄 Cập Nhật"** trực tiếp trên thanh điều hướng của Web Dashboard.
- **Cách 3:** Chạy file **`update.bat`**.

---

## 🚀 Đẩy Bản Cập Nhật Mới Lên GitHub (Dành cho Lập trình viên)
Khi bạn chỉnh sửa mã nguồn và muốn cập nhật cho tất cả các máy khác:
Chạy file:
👉 **`backup_to_github.bat`**

---

## 📖 Tài Liệu Kỹ Thuật Chi Tiết
Vui lòng đọc kỹ tài liệu kiến trúc và quy tắc bảo trì tại:
👉 **[`SYSTEM_MAP.MD`](./SYSTEM_MAP.MD)**
