"""
Quản lý kết nối WebSocket, gom theo TỪNG SUẤT CHIẾU (showtime_id).

Vì nhiều user có thể xem CÙNG 1 suất chiếu cùng lúc, nhưng ghế của suất
chiếu A không liên quan gì đến suất chiếu B - broadcast tin nhắn theo
"phòng" (room) riêng cho từng showtime_id, tránh gửi thừa dữ liệu cho
người không liên quan.

LƯU Ý VỀ GIỚI HẠN: danh sách kết nối lưu TRONG BỘ NHỚ (in-memory dict) của
1 tiến trình app. Điều này ổn với quy mô project hiện tại (1 container app
duy nhất). Nếu sau này scale ra NHIỀU container app cùng lúc (load balancing),
cách này sẽ KHÔNG hoạt động đúng nữa - vì mỗi container có bộ nhớ riêng,
không "thấy" được kết nối của container khác. Giải pháp đúng ở quy mô lớn
hơn là dùng Redis Pub/Sub để các container broadcast được cho nhau (áp dụng
đúng nguyên tắc đã học: Redis phù hợp cho dữ liệu chia sẻ, tốc độ cao,
không cần bền vững tuyệt đối).
"""
import json

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # showtime_id -> list các WebSocket đang xem trang chọn ghế của suất đó
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, showtime_id: int) -> None:
        await websocket.accept()
        self.active_connections.setdefault(showtime_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, showtime_id: int) -> None:
        connections = self.active_connections.get(showtime_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections and showtime_id in self.active_connections:
            del self.active_connections[showtime_id]

    async def broadcast(self, showtime_id: int, message: dict) -> None:
        """Gửi message tới TẤT CẢ client đang xem cùng 1 suất chiếu."""
        connections = self.active_connections.get(showtime_id, [])
        payload = json.dumps(message)

        # Gửi cho từng connection; nếu 1 connection đã "chết" (client đóng
        # tab đột ngột mà chưa kịp disconnect() dọn dẹp), bỏ qua lỗi đó
        # thay vì làm hỏng việc broadcast cho những client còn lại.
        dead_connections = []
        for connection in connections:
            try:
                await connection.send_text(payload)
            except Exception:
                dead_connections.append(connection)

        for dead in dead_connections:
            connections.remove(dead)


manager = ConnectionManager()