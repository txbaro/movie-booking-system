"""
Script chứng minh bug double-booking (race condition) tồn tại trong
luồng đặt vé "naive" ở Task 5.

CÁCH HOẠT ĐỘNG:
1. Tạo N user test riêng biệt (mỗi user login lấy 1 cookie riêng)
2. Tạo 1 phim + 1 suất chiếu test, lấy ra 1 seat_id cụ thể
3. Bắn N request "đặt CÙNG 1 seat_id đó" GẦN NHƯ ĐỒNG THỜI
   (dùng asyncio.gather — tất cả request được gửi đi cùng lúc,
   không đợi lần lượt xong request trước mới gửi request sau)
4. Đếm xem có bao nhiêu request trả về 201 (thành công)
   -> Nếu > 1 request thành công cho CÙNG 1 ghế: BUG XÁC NHẬN TỒN TẠI

Chạy: docker compose exec app python app/scripts/test_race_condition.py
"""
import asyncio

import httpx

BASE_URL = "http://localhost:8000"
NUM_CONCURRENT_USERS = 20


async def register_and_login(client: httpx.AsyncClient, email: str) -> bool:
    """Đăng ký + đăng nhập 1 user test, cookie được httpx tự lưu vào client đó."""
    await client.post(
        f"{BASE_URL}/auth/register",
        json={"email": email, "password": "test1234", "full_name": "Race Tester"},
    )
    resp = await client.post(
        f"{BASE_URL}/auth/login", json={"email": email, "password": "test1234"}
    )
    return resp.status_code == 200


async def setup_test_data() -> tuple[int, int]:
    """
    Tạo sẵn 1 phim + 1 suất chiếu test, trả về seat_id của ghế đầu tiên
    để dùng làm "mục tiêu" cho cuộc tấn công race condition.
    """
    async with httpx.AsyncClient() as client:
        movie_resp = await client.post(
            f"{BASE_URL}/movies",
            json={
                "title": "Race Condition Test Movie",
                "genres": "Test",
                "description": "Phim test, không phải phim thật",
                "duration_minutes": 100,
                "rating": 0,
            },
        )
        movie_id = movie_resp.json()["id"]

        cinema_resp = await client.post(
            f"{BASE_URL}/cinemas",
            json={"name": "Race Test Cinema", "address": "Test", "city": "Test"},
        )
        cinema_id = cinema_resp.json()["id"]
        room_resp = await client.post(
            f"{BASE_URL}/cinemas/{cinema_id}/rooms",
            json={"name": "Race Room", "rows": 1, "cols": 1},
        )
        room_id = room_resp.json()["id"]

        showtime_resp = await client.post(
            f"{BASE_URL}/showtimes",
            json={
                "movie_id": movie_id,
                "room_id": room_id,
                "start_time": "2026-12-31T19:00:00",
                "price": "100000",
            },
        )
        showtime_id = showtime_resp.json()["id"]

        detail_resp = await client.get(f"{BASE_URL}/showtimes/{showtime_id}")
        seat_id = detail_resp.json()["seats"][0]["id"]

        print(f"✓ Đã tạo movie_id={movie_id}, showtime_id={showtime_id}, "
              f"seat_id={seat_id} (chỉ có 1 ghế duy nhất)")
        return showtime_id, seat_id


async def attack_seat(
    showtime_id: int, seat_id: int, user_index: int
) -> tuple[int, int]:
    """
    1 user cố đặt seat_id đó. Trả về (user_index, status_code) để
    biết chính xác user nào thành công/thất bại.
    """
    async with httpx.AsyncClient() as client:
        email = f"race_tester_{user_index}@test.com"
        logged_in = await register_and_login(client, email)
        if not logged_in:
            return user_index, -1

        resp = await client.post(
            f"{BASE_URL}/bookings",
            json={"showtime_id": showtime_id, "seat_ids": [seat_id]},
        )
        return user_index, resp.status_code


async def main():
    print(f"=== Test race condition với {NUM_CONCURRENT_USERS} user đồng thời ===\n")

    showtime_id, seat_id = await setup_test_data()

    print(f"\nBắn {NUM_CONCURRENT_USERS} request đặt CÙNG seat_id={seat_id} "
          f"GẦN NHƯ ĐỒNG THỜI...\n")

    # asyncio.gather chạy TẤT CẢ coroutine song song, không đợi lần lượt
    # -> đây là điểm mấu chốt để tạo ra race condition thật sự
    tasks = [
        attack_seat(showtime_id, seat_id, i)
        for i in range(NUM_CONCURRENT_USERS)
    ]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for _, status in results if status == 201)
    conflict_count = sum(1 for _, status in results if status == 409)

    print("Kết quả từng user:")
    for user_index, status in sorted(results):
        label = {201: "THÀNH CÔNG", 409: "bị từ chối (ghế đã có người đặt)"}.get(
            status, f"lỗi ({status})"
        )
        print(f"  User {user_index}: {label}")

    print(f"\n=== TỔNG KẾT ===")
    print(f"Số request THÀNH CÔNG (201): {success_count}")
    print(f"Số request bị từ chối (409): {conflict_count}")

    if success_count > 1:
        print(f"\n🐛 BUG XÁC NHẬN: {success_count} người đặt được CÙNG 1 ghế "
              f"(chỉ có 1 ghế, phải chỉ đúng 1 người đặt được)!")
        print("   -> Đây chính là lý do cần transaction locking ở Task 7.")
    else:
        print(f"\n✓ Không phát hiện double-booking trong lần chạy này "
              f"(chỉ {success_count} người đặt thành công).")
        print("   Race condition PHỤ THUỘC THỜI ĐIỂM — có thể cần chạy lại")
        print("   vài lần, hoặc tăng NUM_CONCURRENT_USERS, để bug lộ ra rõ hơn.")


if __name__ == "__main__":
    asyncio.run(main())
