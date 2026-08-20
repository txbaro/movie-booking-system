from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.ws_manager import manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/showtime/{showtime_id}")
async def showtime_websocket(websocket: WebSocket, showtime_id: int):
    """
    Client (trang chọn ghế) kết nối vào đây khi mở trang, để nhận cập nhật
    real-time khi có ai giữ/nhả/đặt ghế trong CÙNG suất chiếu.

    Đây là kết nối MỘT CHIỀU về nghiệp vụ (server -> client) dù WebSocket
    về bản chất là 2 chiều - client không cần gửi gì lên, chỉ cần giữ kết
    nối mở để nhận broadcast. Vòng lặp receive() bên dưới chỉ dùng để PHÁT
    HIỆN khi nào client ngắt kết nối (đóng tab, mất mạng...), không xử lý
    nội dung message từ client.
    """
    await manager.connect(websocket, showtime_id)
    try:
        while True:
            # Không cần dùng dữ liệu client gửi lên, nhưng vẫn phải await
            # receive() để giữ vòng lặp sống và bắt được exception khi
            # client ngắt kết nối (WebSocketDisconnect).
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, showtime_id)