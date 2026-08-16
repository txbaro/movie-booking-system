"""
Service gọi TMDB (The Movie Database) API để lấy dữ liệu phim thật.

Tách riêng thành module này (thay vì gọi thẳng trong route) để:
- Route chỉ lo việc HTTP request/response, không lẫn logic gọi API bên ngoài
- Dễ test độc lập, dễ thay đổi nguồn dữ liệu sau này (vd đổi sang nguồn khác)
  mà không phải sửa route
"""
import httpx

from app.core.config import settings

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"


class TMDBError(Exception):
    """Raise khi gọi TMDB thất bại — route sẽ bắt exception này để trả lỗi rõ ràng."""
    pass


async def _get_genre_map(client: httpx.AsyncClient) -> dict[int, str]:
    """
    TMDB trả thể loại phim dưới dạng genre_id (số), không phải tên trực tiếp.
    Cần gọi endpoint riêng để lấy bảng ánh xạ id -> tên, vd {28: "Action", ...}
    """
    resp = await client.get(
        f"{TMDB_BASE_URL}/genre/movie/list",
        params={"api_key": settings.TMDB_API_KEY, "language": "en-US"},
    )
    if resp.status_code != 200:
        raise TMDBError(f"Không lấy được danh sách genre: {resp.status_code}")

    data = resp.json()
    return {g["id"]: g["name"] for g in data["genres"]}


async def _get_runtime(client: httpx.AsyncClient, tmdb_movie_id: int) -> int:
    """
    Endpoint danh sách phim (popular/now_playing) KHÔNG trả về thời lượng phim —
    phải gọi thêm endpoint chi tiết cho từng phim mới có runtime.
    Đây là lý do import sẽ hơi chậm nếu import nhiều phim cùng lúc
    (N phim = 1 request danh sách + N request chi tiết).
    """
    resp = await client.get(
        f"{TMDB_BASE_URL}/movie/{tmdb_movie_id}",
        params={"api_key": settings.TMDB_API_KEY},
    )
    if resp.status_code != 200:
        return 0  # không chặn cả quá trình import chỉ vì 1 phim lấy runtime lỗi
    return resp.json().get("runtime") or 0


async def fetch_movies(category: str = "popular", page: int = 1) -> list[dict]:
    """
    Lấy danh sách phim từ TMDB, đã chuyển đổi sẵn sang format khớp với
    Movie model của mình (title, genres, description, duration_minutes...).

    category: "popular" | "now_playing" | "top_rated" | "upcoming"
    """
    if not settings.TMDB_API_KEY:
        raise TMDBError(
            "Chưa cấu hình TMDB_API_KEY trong file .env. "
            "Đăng ký miễn phí tại https://www.themoviedb.org/settings/api"
        )

    async with httpx.AsyncClient(timeout=15.0) as client:
        genre_map = await _get_genre_map(client)

        resp = await client.get(
            f"{TMDB_BASE_URL}/movie/{category}",
            params={"api_key": settings.TMDB_API_KEY, "language": "en-US", "page": page},
        )
        if resp.status_code != 200:
            raise TMDBError(f"TMDB trả lỗi {resp.status_code}: {resp.text}")

        results = resp.json().get("results", [])

        movies = []
        for item in results:
            genre_names = [genre_map.get(gid, "") for gid in item.get("genre_ids", [])]
            genre_names = [g for g in genre_names if g]  # bỏ genre không map được

            runtime = await _get_runtime(client, item["id"])

            poster_path = item.get("poster_path")
            poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None

            movies.append({
                "tmdb_id": item["id"],
                "title": item.get("title", "Untitled"),
                "genres": ",".join(genre_names) if genre_names else "Unknown",
                "description": item.get("overview") or "Chưa có mô tả.",
                "duration_minutes": runtime,
                "rating": round(item.get("vote_average", 0.0), 1),
                "poster_url": poster_url,
            })

        return movies