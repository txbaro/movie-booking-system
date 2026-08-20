"""
Lắng nghe sự kiện Redis "key hết hạn" (keyspace notification) để TỰ ĐỘNG
broadcast cho các client biết khi 1 ghế được giữ tạm đã HẾT HẠN 5 PHÚT mà
không ai xác nhận đặt vé - lúc đó ghế cần hiển thị lại là "trống" cho mọi
người, không cần họ tự bấm thử mới biết.

CƠ CHẾ: Redis hỗ trợ pub/sub đặc biệt gọi là "keyspace notifications" -
khi bật tính năng này, mỗi lần 1 key hết hạn, Redis tự publish 1 event vào
channel `__keyevent@{db}__:expired`. Ta subscribe channel đó, lọc ra đúng
những key dạng `seat_hold:{showtime_id}:{seat_id}` rồi broadcast đúng
"phòng" WebSocket tương ứng.
"""
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.redis_client import redis_client
from app.core.ws_manager import manager
from app.models.seat import SeatStatus
from app.models.showtime_seat import ShowtimeSeat

EXPIRED_CHANNEL = "__keyevent@0__:expired"


async def listen_for_expired_holds() -> None:
    """
    Chạy NỀN (background task) suốt vòng đời app - xem cách khởi động
    trong app/main.py (lifespan).
    """
    # Bật keyspace notification cho sự kiện "expired" (Ex) - phải bật
    # TRƯỚC khi subscribe, nếu không Redis sẽ không publish event nào.
    await redis_client.config_set("notify-keyspace-events", "Ex")

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(EXPIRED_CHANNEL)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        expired_key = message["data"]
        if not expired_key.startswith("seat_hold:"):
            continue  # bỏ qua key hết hạn không liên quan (vd password_reset:*)

        parts = expired_key.split(":")
        if len(parts) != 3:
            continue
        try:
            showtime_id, seat_id = int(parts[1]), int(parts[2])
        except ValueError:
            continue

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ShowtimeSeat.status).where(
                    ShowtimeSeat.showtime_id == showtime_id,
                    ShowtimeSeat.seat_id == seat_id,
                )
            )
            inventory_status = result.scalar_one_or_none()

        if inventory_status == SeatStatus.AVAILABLE:
            await manager.broadcast(
                showtime_id, {"type": "seat_update", "seat_id": seat_id, "status": "available"}
            )
