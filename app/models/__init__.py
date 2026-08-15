"""
Import tất cả model ở đây để:
1. Alembic autogenerate có thể quét được toàn bộ schema khi tạo migration
2. Các model tham chiếu chéo nhau (vd Movie <-> Showtime) được SQLAlchemy
   nhận diện đầy đủ, tránh lỗi "relationship not found"
"""
from app.models.user import User
from app.models.movie import Movie
from app.models.showtime import Showtime
from app.models.seat import Seat, SeatStatus
from app.models.booking import Booking

__all__ = ["User", "Movie", "Showtime", "Seat", "SeatStatus", "Booking"]
