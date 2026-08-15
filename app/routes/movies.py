from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.movie import Movie
from app.schemas.movie import MovieCreate, MovieRead, MovieUpdate

router = APIRouter(prefix="/movies", tags=["movies"])


@router.post("", response_model=MovieRead, status_code=status.HTTP_201_CREATED)
async def create_movie(payload: MovieCreate, db: AsyncSession = Depends(get_db)):
    """Tạo phim mới. Dùng cho trang quản trị (admin thêm phim)."""
    movie = Movie(**payload.model_dump())
    db.add(movie)
    await db.commit()
    await db.refresh(movie)  # lấy lại id vừa được DB sinh ra
    return movie


@router.get("", response_model=list[MovieRead])
async def list_movies(
    skip: int = 0,
    limit: int = 20,
    genre: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Danh sách phim, có phân trang (skip/limit) và lọc theo thể loại (tuỳ chọn).
    vd: GET /movies?genre=Action&limit=10
    """
    query = select(Movie)
    if genre:
        # ILIKE = so sánh không phân biệt hoa/thường, %...% để match "chứa"
        # thể loại đó trong chuỗi genres (vd "Action,Sci-Fi" match genre="action")
        query = query.where(Movie.genres.ilike(f"%{genre}%"))
    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{movie_id}", response_model=MovieRead)
async def get_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    movie = await db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phim")
    return movie


@router.patch("/{movie_id}", response_model=MovieRead)
async def update_movie(
    movie_id: int, payload: MovieUpdate, db: AsyncSession = Depends(get_db)
):
    movie = await db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phim")

    # exclude_unset=True: chỉ lấy field mà client THỰC SỰ gửi lên,
    # bỏ qua field không gửi (giữ nguyên giá trị cũ trong DB)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(movie, field, value)

    await db.commit()
    await db.refresh(movie)
    return movie


@router.delete("/{movie_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_movie(movie_id: int, db: AsyncSession = Depends(get_db)):
    movie = await db.get(Movie, movie_id)
    if movie is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phim")

    await db.delete(movie)
    await db.commit()
