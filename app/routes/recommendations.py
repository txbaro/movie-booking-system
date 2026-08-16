from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.booking import Booking
from app.models.movie import Movie
from app.models.showtime import Showtime
from app.models.user import User
from app.schemas.recommendation import RecommendedMovie
from app.services.recommendation import get_recommendations_for_user, get_similar_movies

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/movie/{movie_id}", response_model=list[RecommendedMovie])
async def similar_movies(
    movie_id: int, limit: int = 5, db: AsyncSession = Depends(get_db)
):
    """
    Gợi ý phim tương tự 1 phim cụ thể — dùng cho trang chi tiết phim,
    kiểu "Nếu bạn thích phim này, có thể bạn cũng thích...".
    Không cần đăng nhập vì không phụ thuộc lịch sử cá nhân.
    """
    movie = await db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phim")

    results = await get_similar_movies(db, movie_id, top_n=limit)
    return [
        RecommendedMovie(movie=m, similarity_score=round(score, 3))
        for m, score in results
    ]


@router.get("/me", response_model=list[RecommendedMovie])
async def recommendations_for_me(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Gợi ý phim cho user hiện tại, dựa trên TOÀN BỘ lịch sử đặt vé của họ.
    Đây là API dùng cho trang chủ / dashboard cá nhân sau khi đăng nhập.
    """
    # Lấy danh sách movie_id user đã từng đặt vé xem, qua join
    # Booking -> Showtime -> Movie (booking không lưu trực tiếp movie_id,
    # phải đi qua showtime để biết booking đó thuộc phim nào).
    result = await db.execute(
        select(Showtime.movie_id)
        .join(Booking, Booking.showtime_id == Showtime.id)
        .where(Booking.user_id == current_user.id)
        .distinct()
    )
    watched_movie_ids = [row[0] for row in result.all()]

    if not watched_movie_ids:
        return []  # user chưa đặt vé phim nào -> chưa có cơ sở để gợi ý
                    # (đây chính là "cold-start problem" đã bàn từ đầu -
                    #  xử lý kỹ hơn vấn đề này có thể làm ở phần mở rộng sau)

    results = await get_recommendations_for_user(db, watched_movie_ids, top_n=limit)
    return [
        RecommendedMovie(movie=m, similarity_score=round(score, 3))
        for m, score in results
    ]