"""
Kết nối Redis dùng cho tính năng "giữ ghế tạm thời".

decode_responses=True: Redis mặc định trả về bytes (vd b"hello"), bật cờ này
để tự động decode sang str — tiện hơn khi làm việc trong Python, không phải
tự gọi .decode() ở mọi nơi.
"""
import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)