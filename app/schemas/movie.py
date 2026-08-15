from pydantic import BaseModel, ConfigDict


class MovieBase(BaseModel):
    title: str
    genres: str  # vd: "Action,Sci-Fi,Thriller"
    description: str
    duration_minutes: int
    rating: float = 0.0
    poster_url: str | None = None


class MovieCreate(MovieBase):
    """Dữ liệu client gửi lên khi tạo phim mới — giống MovieBase, không cần id."""
    pass


class MovieUpdate(BaseModel):
    """
    Tất cả field đều optional — cho phép client chỉ gửi field muốn sửa
    (PATCH-style update) thay vì phải gửi lại toàn bộ thông tin phim.
    """
    title: str | None = None
    genres: str | None = None
    description: str | None = None
    duration_minutes: int | None = None
    rating: float | None = None
    poster_url: str | None = None


class MovieRead(MovieBase):
    """Dữ liệu trả về cho client — có thêm id so với lúc tạo."""
    id: int

    # from_attributes=True: cho phép Pydantic đọc trực tiếp từ SQLAlchemy
    # model (object có attribute), không chỉ từ dict — cần thiết vì route
    # sẽ trả thẳng object Movie lấy từ database.
    model_config = ConfigDict(from_attributes=True)
