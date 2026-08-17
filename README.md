# 🎬 Movie Booking System

Hệ thống đặt vé xem phim với cơ chế **chống double-booking 2 lớp** (Redis + PostgreSQL transaction locking) và **gợi ý phim cá nhân hóa** dựa trên lịch sử đặt vé.

🔗 **Demo trực tiếp:** [thêm link deploy ở đây]

---

## Vấn đề dự án giải quyết

Khi nhiều người cùng cố đặt 1 ghế trong cùng 1 suất chiếu tại cùng thời điểm, hệ thống phải đảm bảo **chỉ đúng 1 người** đặt được ghế đó — không được để xảy ra tình trạng 2 người cùng "sở hữu" 1 ghế (double-booking), và người thua cuộc phải nhận được thông báo rõ ràng thay vì lỗi hệ thống mơ hồ.

Đây là bài toán **race condition** kinh điển trong các hệ thống đặt chỗ thực tế (vé máy bay, vé concert, đặt phòng khách sạn).

## Cách giải quyết — kiến trúc 2 lớp bảo vệ

**Lớp 1 — Redis (giữ ghế tạm thời, TTL 10 phút)**
Khi user chọn ghế, hệ thống giành 1 khóa nguyên tử trong Redis (`SET ... NX`) — đảm bảo chỉ 1 request thành công dù nhiều request đến cùng lúc. Khóa tự động hết hạn nếu không thanh toán kịp, không cần job dọn dẹp thủ công.

**Lớp 2 — PostgreSQL `SELECT ... FOR UPDATE` (xác nhận cuối cùng)**
Trước khi ghi booking thật vào database, dòng dữ liệu ghế được khóa độc quyền — loại bỏ hoàn toàn khoảng hở giữa "đọc trạng thái" và "ghi booking" từng gây ra bug double-booking.

Kiến trúc này mô phỏng đúng cách các hệ thống đặt vé quy mô lớn (BookMyShow, Ticketmaster) xử lý bài toán tương tự: Redis lo tốc độ và trải nghiệm real-time, PostgreSQL đóng vai trò "nguồn sự thật" cuối cùng.

**Đã kiểm chứng bằng script mô phỏng 20 request đồng thời tranh giành 1 ghế** — chỉ 1 request thành công, 19 request còn lại nhận lỗi rõ ràng (409), không có double-booking hay lỗi hệ thống nào xảy ra.

## Các điểm kỹ thuật đáng chú ý khác

- **Chống spam giữ ghế:** mỗi user chỉ được giữ tối đa 1 ghế tại 1 thời điểm, ràng buộc ở tầng server (không phụ thuộc hành vi phía client)
- **Import dữ liệu thật từ TMDB:** phim, poster, mô tả, trailer YouTube — không dùng dữ liệu giả
- **Gợi ý phim cá nhân hóa:** content-based filtering (TF-IDF + cosine similarity) dựa trên lịch sử đặt vé của từng user
- **Xác thực an toàn:** JWT lưu trong HttpOnly cookie, mật khẩu hash bằng bcrypt, luồng quên/đặt lại mật khẩu qua email thật (SMTP)
- **Toàn bộ hạ tầng chạy bằng Docker:** PostgreSQL, Redis, và ứng dụng — môi trường nhất quán, không phụ thuộc cấu hình máy cá nhân

## Tech stack

| Thành phần | Công nghệ |
|---|---|
| Backend | FastAPI (async), SQLAlchemy (async ORM) |
| Database | PostgreSQL |
| Cache / tạm thời | Redis |
| Frontend | Jinja2 (server-side rendering) |
| Gợi ý phim | scikit-learn (TF-IDF, cosine similarity) |
| Dữ liệu phim | TMDB API |
| Hạ tầng | Docker, Docker Compose |
| Xác thực | JWT (HttpOnly cookie), bcrypt |

## Cấu trúc project

app/
├── main.py # Entry point
├── core/ # Config, kết nối DB/Redis, bảo mật
├── models/ # SQLAlchemy models
├── schemas/ # Pydantic schemas
├── routes/ # API endpoints
├── services/ # Logic nghiệp vụ (TMDB, recommendation, email)
├── templates/ # Giao diện Jinja2
└── static/ # CSS/JS