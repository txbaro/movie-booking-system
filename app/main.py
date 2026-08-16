from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.database import Base, engine
from app.routes import auth, booking, movies, pages, recommendations, showtimes

# Import models package để đảm bảo tất cả model được đăng ký vào Base.metadata
# TRƯỚC khi create_all chạy — nếu thiếu dòng này, bảng nào chưa được import
# sẽ không được tạo, dù model đã định nghĩa đầy đủ.
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Tự động tạo bảng khi app khởi động — TIỆN CHO GIAI ĐOẠN HỌC/DEV.

    Lưu ý quan trọng: cách này KHÔNG phù hợp cho production, vì:
    - Không theo dõi được lịch sử thay đổi schema
    - Sửa model sau này (vd thêm cột) sẽ KHÔNG tự cập nhật bảng đã tồn tại,
      chỉ tạo bảng nếu nó CHƯA có (create_all bỏ qua bảng đã tồn tại)

    Alembic (sẽ setup ở bước sau) giải quyết đúng vấn đề này bằng migration
    có thể theo dõi, review, và rollback được. Tạm thời dùng create_all để
    có thể test API ngay mà không cần dừng lại học Alembic trước.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # (không cần cleanup gì thêm lúc shutdown)


app = FastAPI(title="Movie Booking System", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(booking.router)
app.include_router(movies.router)
app.include_router(recommendations.router)
app.include_router(showtimes.router)


@app.get("/health")
async def health_check():
    """Endpoint đơn giản để kiểm tra server có chạy không."""
    return {"status": "ok"}
