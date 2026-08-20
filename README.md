# 🎬 Movie Booking System

Hệ thống tổng hợp lịch chiếu nhiều rạp, có cơ chế **chống
double-booking 2 lớp** (Redis + PostgreSQL transaction locking) cho inventory
nội bộ ở chế độ technical demo và **gợi ý phim cá nhân hóa** từ
hành vi khám phá phim trong flow external-booking thực tế.

🔗 **Demo trực tiếp:** [thêm link deploy ở đây]

---

## Vấn đề dự án giải quyết

Khi nhiều người cùng cố đặt 1 ghế trong cùng 1 suất chiếu tại cùng thời điểm, hệ thống phải đảm bảo **chỉ đúng 1 người** đặt được ghế đó — không được để xảy ra tình trạng 2 người cùng "sở hữu" 1 ghế (double-booking), và người thua cuộc phải nhận được thông báo rõ ràng thay vì lỗi hệ thống mơ hồ.

Đây là bài toán **race condition** kinh điển trong các hệ thống đặt chỗ thực tế (vé máy bay, vé concert, đặt phòng khách sạn).

## Cách giải quyết — kiến trúc 2 lớp bảo vệ

**Lớp 1 — Redis (giữ ghế tạm thời, TTL 5 phút)**
Khi user chọn ghế, hệ thống giành 1 khóa nguyên tử trong Redis (`SET ... NX`) — đảm bảo chỉ 1 request thành công dù nhiều request đến cùng lúc. Khóa tự động hết hạn nếu không thanh toán kịp, không cần job dọn dẹp thủ công.

**Lớp 2 — PostgreSQL `SELECT ... FOR UPDATE` (xác nhận cuối cùng)**
Trước khi ghi booking thật vào database, dòng dữ liệu ghế được khóa độc quyền — loại bỏ hoàn toàn khoảng hở giữa "đọc trạng thái" và "ghi booking" từng gây ra bug double-booking.

Kiến trúc này mô phỏng đúng cách các hệ thống đặt vé quy mô lớn (BookMyShow, Ticketmaster) xử lý bài toán tương tự: Redis lo tốc độ và trải nghiệm real-time, PostgreSQL đóng vai trò "nguồn sự thật" cuối cùng.

**Đã kiểm chứng bằng script mô phỏng 20 request đồng thời tranh giành 1 ghế** — chỉ 1 request thành công, 19 request còn lại nhận lỗi rõ ràng (409), không có double-booking hay lỗi hệ thống nào xảy ra.

## Các điểm kỹ thuật đáng chú ý khác

- **Chống spam giữ ghế:** mỗi user chỉ được giữ tối đa 10 ghế
  cho một suất, ràng buộc ở server
- **Import dữ liệu thật từ TMDB:** phim, poster, mô tả, trailer YouTube — không dùng dữ liệu giả
- **Gợi ý phim cá nhân hóa:** content-based filtering (TF-IDF +
  cosine similarity) từ lượt xem phim, tìm kiếm, xem lịch chiếu, bấm sang
  website rạp và booking nội bộ
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

## Vai trò Redis trong production

Flow dữ liệu thật chỉ có `external_redirect`, nên app không khởi động
seat-expiry listener hoặc expose WebSocket seat route theo mặc định. Redis
thay vào đó nằm trực tiếp trong các flow production:

- quota gợi ý theo user và IP, reset lúc 00:00 giờ Việt Nam;
- cache prompt embedding theo hash/model với TTL, không lưu prompt thô trong key;
- distributed lock ngăn hai job collector cùng nguồn chạy đè nhau;
- reset-password token có TTL.

```dotenv
AI_REQUESTS_PER_USER_PER_DAY=20
AI_REQUESTS_PER_IP_PER_DAY=100
AI_PROMPT_CACHE_TTL_SECONDS=86400
COLLECTOR_LOCK_TTL_SECONDS=3600
```

Khi cần demo race condition/seat hold, bật subsystem booking nội bộ:

```dotenv
ENABLE_INTERNAL_BOOKING=true
```

Test profile tự bật flag này. Production mặc định là `false`, nên không
có background Redis keyspace listener chạy liên tục.

## Database migrations

Schema được quản lý bằng Alembic; ứng dụng không còn gọi
`Base.metadata.create_all()` khi khởi động.

```bash
docker compose run --rm app alembic upgrade head
```

Kiểm tra database đang ở revision nào và metadata ORM có lệch schema không:

```bash
docker compose run --rm app alembic current
docker compose run --rm app alembic check
```

Migration đầu tiên tự nhận diện database trống hoặc schema legacy. Với dữ liệu
legacy, migration tạo một cinema/phòng chuyển tiếp, gắn `room_id`, sinh
`ShowtimeSeat`, sinh `BookingSeat`, rồi kiểm tra toàn vẹn trước khi commit.

## Cinema data ingestion

Pipeline collector chuẩn hóa dữ liệu nguồn thành DTO rồi đồng bộ idempotent vào
Cinema, CinemaRoom, Movie, Showtime, Seat và ShowtimeSeat. Có thể thử pipeline
không cần nguồn bên ngoài bằng fixture đi kèm:

```bash
docker compose run --rm app \
  python -m app.scripts.sync_cinema_data \
  --source fixture \
  --date 2026-08-20
```

Chạy lại cùng lệnh không tạo dữ liệu trùng nhờ identity `(source,
external_id)` ở database. Mỗi record chạy trong savepoint riêng nên một record
lỗi không rollback các record hợp lệ khác trong batch.

Mỗi lượt sync còn giành Redis distributed lock theo `source`. Nếu scheduler
hoặc deploy vô tình kích hoạt hai job cùng lúc, job thứ hai trả
`collector_already_running` thay vì crawl và ghi dữ liệu song song.

Pipeline hỗ trợ hai loại suất chiếu:

- `internal`: có phòng, giá và inventory ghế để đặt trực tiếp trong hệ thống.
- `external_redirect`: có rạp và URL đặt vé bên ngoài; phòng/giá có thể thiếu và
hệ thống không sinh inventory ghế.

Đồng bộ dữ liệu lịch chiếu thật từ Cinestar. Ngày bắt đầu mặc định là hôm nay
theo giờ Việt Nam và collector lấy hôm nay cùng 6 ngày kế tiếp trong một lượt:

```bash
docker compose run --rm app \
  python -m app.scripts.sync_cinema_data --source cinestar
```

Collector tự đọc danh sách phim/rạp từ dữ liệu Next.js công khai, giới hạn
tốc độ request, retry lỗi tạm thời và chỉ lưu suất chiếu dưới dạng
`external_redirect`. Không cần nhập thủ công movie ID hoặc cinema ID.

Có thể thay đổi khoảng ngày (tối đa 31 ngày; nguồn chỉ trả những ngày thực sự
có lịch):

```bash
docker compose run --rm app \
  python -m app.scripts.sync_cinema_data \
  --source cinestar --date 2026-08-20 --days 7
```

Đồng bộ lịch Lotte Cinema. Collector tự tìm danh sách rạp toàn quốc, lấy địa
chỉ/toạ độ và gọi RPC lịch chiếu cho từng rạp/ngày; mặc định cũng lấy 7 ngày:

```bash
docker compose run --rm app \
  python -m app.scripts.sync_cinema_data --source lotte
```

Lotte dùng ASP.NET RPC (`GetCinemaDetailItem`, `GetMoviePlayDates`,
`GetPlaySequence`). Collector không lưu cookie trình duyệt và không cần
Playwright; request được giới hạn tốc độ và retry khi gặp lỗi tạm thời.

Đồng bộ lịch Galaxy Cinema. Galaxy nhúng danh sách rạp, phim và session nhiều
ngày trong `__NEXT_DATA__` của trang lịch chiếu nên collector chỉ tải một trang
rồi chuẩn hóa dữ liệu. Website có lớp chống bot; copy giá trị header `Cookie`
từ request `/lich-chieu/` trong DevTools vào biến môi trường, không ghi cookie
vào source code. Nếu Galaxy vẫn redirect, copy cả `User-Agent` của cùng request
vào `GALAXY_USER_AGENT`:

```bash
docker compose run --rm \
  -e GALAXY_COOKIE='muid_mly=...' \
  -e GALAXY_USER_AGENT='Mozilla/5.0 ...' \
  app python -m app.scripts.sync_cinema_data \
  --source galaxy --date 2026-08-20 --days 7
```

Cookie Galaxy có thể hết hạn. Khi đó collector dừng với thông báo yêu cầu cập
nhật `GALAXY_COOKIE`; dữ liệu đã đồng bộ trước đó không bị ảnh hưởng.

Fixture hiện có cả hai loại để phát triển API/UI mà chưa cần crawler thật.

Booking UI khôi phục các hold còn hạn sau khi refresh, dùng thời hạn sớm nhất
của nhóm ghế làm countdown, overlay Redis hold lên inventory database và tự
kết nối lại WebSocket với exponential backoff khi mạng gián đoạn.

Đồng bộ bộ demo external showtime cho ba provider:

```bash
docker compose run --rm app \
  python -m app.scripts.sync_cinema_data \
  --source demo \
  --date 2026-08-20
```

Có thể chạy riêng bằng `--source mock-cgv`, `mock-galaxy` hoặc
`mock-cinestar`. Trong database, source tương ứng vẫn là `cgv`, `galaxy` và
`cinestar`, giống collector thật sẽ dùng sau này.

## Canonical movie và chống trùng phim

`movies` chứa một bản ghi chuẩn cho mỗi phim. ID riêng của từng nguồn được lưu
trong `provider_movies`, còn `showtimes.movie_id` luôn trỏ về phim chuẩn. Ingestion
resolver ưu tiên mapping `(source, external_id)` đã có; với phim mới, resolver
so khớp tên đã bỏ dấu/hậu tố phân loại (`T13`, `T16`, `LT`, `Rerun`) cùng thời
lượng sai lệch tối đa 10 phút. Vì vậy một poster có thể tổng hợp lịch của
Cinestar, Galaxy và Lotte mà vẫn giữ đầy đủ provenance của từng nguồn.

## Discovery API

Các endpoint đọc hỗ trợ filter và pagination để dùng trực tiếp cho UI:

```text
GET /movies?title=conan&source=cgv&available_only=true&skip=0&limit=20
GET /showtimes?source=cgv&city=Hồ Chí Minh&date=2026-08-20&limit=50
GET /movies/{id}/showtimes?city=Hồ Chí Minh&date=2026-08-20
GET /cinemas?latitude=10.778&longitude=106.702&radius_km=10
```

Danh sách showtime và aggregation mặc định chỉ trả suất chưa bắt đầu; gửi
`upcoming_only=false` khi cần xem dữ liệu lịch sử. Khi có tọa độ, cinema được
sắp theo khoảng cách và response có thêm `distance_km`.

## Behavior tracking và recommendation

UI gửi event cho user đã đăng nhập khi họ xem phim, tìm kiếm, xem lịch
chiếu hoặc bấm nút đặt vé bên website rạp. API ghi nhận qua
`POST /events`, tự suy ra phim/rạp/nguồn từ `showtime_id` và gộp event
trùng trong cửa sổ hai phút.

`GET /recommendations/me` tạo content profile theo trọng số:

```text
movie_viewed=1, movie_searched=2, showtimes_viewed=3,
external_booking_clicked=7, internal_booking_confirmed=10
```

Tín hiệu cũ giảm một nửa sau mỗi 30 ngày; chỉ các phim còn suất
tương lai được đề xuất. User chưa có hành vi nhận danh sách trending
theo số suất sắp chiếu và rating. Lượt bấm sang rạp chỉ là tín hiệu
ý định, không được ghi nhận là một giao dịch đã hoàn tất.

### Gợi ý bằng ngôn ngữ tự nhiên

User đã đăng nhập có thể mô tả bộ phim họ muốn xem ngay trên trang
chủ. `POST /recommendations/natural-language` xếp hạng các phim còn
suất theo công thức hybrid:

```text
semantic similarity 60% + behavior 25% + showtime popularity 10% + rating 5%
```

Request có thể gửi thêm `latitude`, `longitude` và `radius_km`. Khi có
vị trí, backend loại rạp ngoài bán kính, tính Haversine từ user tới rạp,
chọn rạp gần nhất có suất cho từng phim và đổi trọng số thành:

```text
semantic 55% + behavior 20% + proximity 15% + popularity 5% + rating 5%
```

Response trả `nearest_showtime` gồm giờ chiếu, tên/địa chỉ rạp,
khoảng cách và booking URL thật. UI dùng Browser Geolocation nên không
cần Google Maps khi trình duyệt đã cung cấp tọa độ. Rạp thiếu tọa độ
không được đoán khoảng cách và sẽ bị bỏ qua trong chế độ nearby.
Tọa độ user không được lưu trong behavior event.

Khi cấu hình Gemini API, vector của canonical movie được cache trong
`movie_embeddings` theo hash nội dung và model. Phim không thay đổi không bị
embed lại; mỗi prompt bình thường chỉ tốn một query embedding. Tạo API key tại
Google AI Studio rồi cấu hình trong `.env`:

```dotenv
GEMINI_API_KEY=your-google-ai-studio-api-key
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_API_BASE_URL=https://generativelanguage.googleapis.com/v1beta
```

Query embedding của prompt được cache trong Redis 24 giờ theo mặc định.
Prompt lặp lại với cùng model không gọi provider lần nữa. API trả thêm
`quota_remaining` và phản hồi `429` kèm `Retry-After` khi hết quota.

Nếu API key chưa được cấu hình hoặc Gemini tạm lỗi, service
fallback sang word/character TF-IDF cục bộ và response ghi rõ
`engine=local_tfidf_fallback`. Mỗi response có `context_id`; event
`preference_prompt_submitted` và `recommendation_clicked` dùng ID này để
đo click-through rate theo từng lần gợi ý. Prompt được lưu cho user đã
đăng nhập để phân tích chất lượng recommendation.

## Automated tests

Test suite dùng PostgreSQL và Redis riêng, không đọc hoặc xóa dữ liệu development.
Lệnh dưới đây tự chạy Alembic trên database test trước khi chạy pytest:

```bash
docker compose --profile test run --rm --build test
```

Sau lần build đầu tiên, có thể bỏ `--build` để chạy nhanh hơn:

```bash
docker compose --profile test run --rm test
```

Các nhóm được kiểm tra gồm health/UI smoke test, discovery API, canonical movie
đa nguồn, authentication, behavior event/deduplication, semantic fallback,
embedding cache, location/radius filtering, nearest showtime, hybrid
recommendation, Redis AI quota, distributed lock, seat hold, booking inventory
và hai user tranh chấp cùng một ghế.

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
