"""
Script tự động tạo suất chiếu cho MỌI phim trong DB CHƯA có suất chiếu nào.

An toàn khi chạy nhiều lần (idempotent): phim đã có ít nhất 1 suất chiếu
sẽ được BỎ QUA, không tạo thêm - tránh việc chạy lại script làm nhân đôi
số suất chiếu mỗi lần.

Mỗi phim được tạo 3 suất chiếu trong 2 ngày tới, khung giờ cố định
(10:00, 15:00, 20:00), phòng 8 hàng x 10 cột (80 ghế), giá ngẫu nhiên
trong khoảng 75.000đ - 120.000đ.

Chạy: docker compose exec app python app/scripts/generate_showtimes.py
"""
import asyncio
import random
from datetime import datetime, timedelta, time

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.models.movie import Movie
from app.models.showtime import Showtime
from app.routes.showtimes import _generate_seats  # tái dùng logic sinh ghế đã có

SHOWTIME_HOURS = [time(10, 0), time(15, 0), time(20, 0)]
DAYS_AHEAD = [1, 2]  # tạo suất chiếu cho ngày mai và ngày kia
ROOM_ROWS = 8
ROOM_COLS = 10
PRICE_RANGE = (75_000, 120_000)


async def main():
    async with AsyncSessionLocal() as db:
        # selectinload(Movie.showtimes): tải sẵn showtimes cùng lúc, để check
        # "phim đã có suất chiếu chưa" mà không cần query riêng cho từng phim
        # (tránh N+1 query, đã học nguyên tắc này từ Task 3).
        result = await db.execute(select(Movie).options(selectinload(Movie.showtimes)))
        movies = result.scalars().all()

        if not movies:
            print("Chưa có phim nào trong DB. Import phim trước (Task 3: TMDB import).")
            return

        created_count = 0
        skipped_count = 0

        for movie in movies:
            if movie.showtimes:
                skipped_count += 1
                continue

            for day_offset in DAYS_AHEAD:
                for hour in SHOWTIME_HOURS:
                    show_date = datetime.now() + timedelta(days=day_offset)
                    start_time = datetime.combine(show_date.date(), hour)
                    price = random.randint(*PRICE_RANGE)
                    # làm tròn giá về hàng nghìn cho đẹp (vd 98700 -> 99000)
                    price = round(price, -3)

                    showtime = Showtime(
                        movie_id=movie.id,
                        start_time=start_time,
                        room_rows=ROOM_ROWS,
                        room_cols=ROOM_COLS,
                        price=price,
                    )
                    db.add(showtime)
                    await db.flush()  # lấy showtime.id trước khi sinh ghế

                    seats = _generate_seats(showtime.id, ROOM_ROWS, ROOM_COLS)
                    db.add_all(seats)

            created_count += 1
            print(f"✓ Đã tạo {len(DAYS_AHEAD) * len(SHOWTIME_HOURS)} suất chiếu cho: {movie.title}")

        await db.commit()

        print(f"\n=== HOÀN TẤT ===")
        print(f"Phim được tạo suất chiếu mới: {created_count}")
        print(f"Phim bị bỏ qua (đã có suất chiếu từ trước): {skipped_count}")


if __name__ == "__main__":
    asyncio.run(main())