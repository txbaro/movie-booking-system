# Movie Booking System

Hệ thống đặt vé xem phim với xử lý conflict khi nhiều người cùng đặt 1 ghế,
và gợi ý phim dựa trên lịch sử mua (AI-powered).

**Tech stack:** FastAPI · PostgreSQL · SQLAlchemy (async) · Jinja2

## Trạng thái hiện tại (Task 1-2 hoàn thành)

- [x] Cấu trúc project
- [x] Database schema (users, movies, showtimes, seats, bookings)
- [x] CRUD phim & suất chiếu (Task 3)
- [ ] Đăng ký/đăng nhập (Task 4)
- [ ] Luồng đặt vé cơ bản (Task 5)
- [ ] Script test race condition (Task 6)
- [ ] Xử lý conflict bằng locking (Task 7)
- [ ] Recommendation (Task 8)
- [ ] Giao diện (Task 9)

## Setup (Docker — không cần cài Python/venv trên máy)

Toàn bộ project chạy trong Docker: PostgreSQL và FastAPI app đều là container,
tự nối mạng với nhau. Máy bạn chỉ cần cài Docker, không cần lo version Python.

### 1. Cấu hình biến môi trường
```bash
cp .env.example .env
# Mở .env, đổi SECRET_KEY (tạo bằng lệnh dưới) — các biến POSTGRES_* để mặc định cũng được
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Dựng toàn bộ (build image lần đầu)
```bash
docker compose up --build
```
Lần đầu sẽ hơi lâu vì phải build image (cài hết package trong `requirements.txt`).
Các lần sau chỉ cần `docker compose up` (không có `--build`) nếu không đổi
`requirements.txt` hay `Dockerfile`.

Mở http://localhost:8000/health — thấy `{"status": "ok"}` là thành công.
Swagger docs tự động: http://localhost:8000/docs

### 3. Chạy nền (không chiếm terminal)
```bash
docker compose up -d
```

## Các lệnh dùng hằng ngày khi code

**Sửa code Python** — tự động reload, không cần làm gì thêm (nhờ `--reload` +
volume mount trong `docker-compose.yml`). Chỉ cần lưu file, chờ vài giây,
gọi lại API là thấy thay đổi.

**Thêm package mới vào `requirements.txt`** — phải build lại image:
```bash
docker compose up --build
```

**Xem log của app** (hữu ích khi debug lỗi):
```bash
docker compose logs -f app
```

**Vào bên trong container app** (giống SSH vào máy ảo, dùng khi cần chạy lệnh
Python/pip thủ công, hoặc sau này chạy `alembic revision`):
```bash
docker compose exec app bash
```

**Vào PostgreSQL bằng psql** (xem dữ liệu trực tiếp bằng SQL):
```bash
docker compose exec db psql -U postgres -d movie_booking
```

**Dừng toàn bộ** (data trong PostgreSQL vẫn giữ nguyên nhờ volume):
```bash
docker compose down
```

**Dừng và xóa luôn data** (dùng khi muốn reset database về trạng thái sạch):
```bash
docker compose down -v
```

**Kiểm tra container nào đang chạy:**
```bash
docker compose ps
```

## Cấu trúc project

```
app/
├── main.py           # Entry point
├── core/
│   ├── config.py     # Đọc biến môi trường
│   └── database.py   # Kết nối DB async + dependency get_db()
├── models/           # SQLAlchemy models (5 bảng)
├── schemas/          # Pydantic schemas (validate request/response) - sắp làm
├── routes/           # API endpoints - sắp làm
├── templates/        # Jinja2 HTML templates - sắp làm
└── static/           # CSS/JS
```

## Ghi chú thiết kế quan trọng

**Tạo bảng tự động lúc khởi động (tạm thời, chỉ dùng cho dev)**
`app/main.py` hiện dùng `Base.metadata.create_all()` trong `lifespan` để tự
tạo bảng khi app chạy — tiện để test API ngay, nhưng **không theo dõi được
lịch sử thay đổi schema** và **không tự cập nhật bảng đã tồn tại** khi bạn
sửa model. Alembic (thêm ở bước sau) sẽ thay thế cách này bằng migration
đúng chuẩn.

**API endpoints hiện có (Task 3)**
```
POST   /movies              Tạo phim mới
GET    /movies              Danh sách phim (có phân trang + lọc theo genre)
GET    /movies/{id}         Chi tiết 1 phim
PATCH  /movies/{id}         Sửa thông tin phim
DELETE /movies/{id}         Xóa phim

POST   /showtimes           Tạo suất chiếu MỚI + TỰ ĐỘNG sinh toàn bộ ghế
GET    /showtimes           Danh sách suất chiếu (lọc theo movie_id)
GET    /showtimes/{id}      Chi tiết suất chiếu KÈM danh sách ghế
DELETE /showtimes/{id}      Xóa suất chiếu (ghế liên quan tự động bị xóa theo)
```
Test trực tiếp qua Swagger UI: http://localhost:8000/docs

**Vì sao tạo Showtime tự động sinh ghế luôn, không tách API riêng?**
Tránh trường hợp dữ liệu không nhất quán: suất chiếu tồn tại nhưng thiếu ghế
(vd do client quên gọi API tạo ghế, hoặc gọi giữa chừng bị lỗi mạng).

**Vì sao mỗi Showtime có bộ ghế riêng?**
Trạng thái "ghế đã đặt" chỉ có ý nghĩa trong phạm vi 1 suất chiếu. Ghế A5 của
suất 19h có thể trống trong khi ghế A5 của suất 21h đã có người đặt.

**2 lớp bảo vệ chống double-booking ở tầng database:**
1. `UniqueConstraint(showtime_id, seat_label)` trên bảng `seats` — không cho phép
   2 ghế trùng tên trong cùng suất chiếu
2. `unique=True` trên `booking.seat_id` — 1 ghế chỉ gắn được với tối đa 1 booking

Đây là "lưới an toàn cuối cùng" ở tầng DB. Logic xử lý concurrency chính (transaction
locking) sẽ được implement ở Task 7, trong `app/routes/booking.py`.
