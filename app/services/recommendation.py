"""
Content-based recommendation: gợi ý phim dựa trên ĐỘ TƯƠNG ĐỒNG nội dung
(thể loại + mô tả), KHÔNG dùng AI/LLM — như đã bàn từ đầu, với dataset chỉ
vài chục/vài trăm phim, thuật toán thống kê đơn giản này đã đủ chính xác.
AI (LLM) sẽ được thêm sau, chỉ để LÝ GIẢI gợi ý bằng ngôn ngữ tự nhiên,
không dùng để TÍNH gợi ý.

CƠ CHẾ TF-IDF + Cosine Similarity (giải thích ngắn gọn):
1. Ghép "genres + description" của mỗi phim thành 1 đoạn text
2. TF-IDF chuyển mỗi đoạn text thành 1 vector số — từ nào xuất hiện nhiều
   trong phim này nhưng HIẾM ở các phim khác sẽ có trọng số cao (đặc trưng
   riêng của phim đó), từ phổ biến ở mọi phim (the, a, movie...) bị giảm
   trọng số tự động.
3. Cosine similarity đo "góc" giữa 2 vector — góc càng nhỏ (vector càng
   "cùng hướng"), 2 phim càng giống nhau về nội dung.
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.movie import Movie


async def _load_all_movies(db: AsyncSession) -> list[Movie]:
    result = await db.execute(select(Movie))
    return list(result.scalars().all())


def _build_text(movie: Movie) -> str:
    """
    Ghép genres + description thành 1 đoạn text để đưa vào TF-IDF.
    Nhân genres lên 2 lần (viết 2 lần liền nhau) để nó có TRỌNG SỐ CAO HƠN
    description trong phép so sánh — vì "cùng thể loại" thường là tín hiệu
    mạnh hơn "vài từ trùng ngẫu nhiên trong mô tả dài".
    """
    return f"{movie.genres} {movie.genres} {movie.description}"


async def get_similar_movies(
    db: AsyncSession, movie_id: int, top_n: int = 5
) -> list[tuple[Movie, float]]:
    """
    Trả về top_n phim giống movie_id nhất, kèm điểm tương đồng (0.0 - 1.0).

    Lưu ý về hiệu năng: hàm này tính lại toàn bộ ma trận tương đồng MỖI LẦN
    gọi (không cache) — chấp nhận được ở quy mô vài trăm phim của project
    này. Nếu sau này có hàng chục nghìn phim, nên tính trước (precompute)
    và lưu cache thay vì tính runtime mỗi request.
    """
    movies = await _load_all_movies(db)
    if len(movies) < 2:
        return []

    target_index = next((i for i, m in enumerate(movies) if m.id == movie_id), None)
    if target_index is None:
        return []

    texts = [_build_text(m) for m in movies]

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(texts)

    # So sánh vector của phim target với TẤT CẢ phim khác cùng lúc
    similarity_scores = cosine_similarity(
        tfidf_matrix[target_index], tfidf_matrix
    ).flatten()

    # Ghép (phim, điểm số), loại bỏ chính phim target ra khỏi kết quả,
    # sắp xếp giảm dần theo độ tương đồng, lấy top_n
    scored = [
        (movies[i], float(similarity_scores[i]))
        for i in range(len(movies))
        if i != target_index
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    return scored[:top_n]


async def get_recommendations_for_user(
    db: AsyncSession, watched_movie_ids: list[int], top_n: int = 5
) -> list[tuple[Movie, float]]:
    """
    Gợi ý phim cho user dựa trên NHIỀU phim đã xem (lịch sử booking),
    không chỉ 1 phim. Cách làm: gộp điểm tương đồng từ TỪNG phim đã xem,
    cộng dồn lại — phim nào giống NHIỀU phim user từng xem sẽ được ưu tiên
    cao hơn phim chỉ giống 1 phim duy nhất.
    """
    if not watched_movie_ids:
        return []

    movies = await _load_all_movies(db)
    if len(movies) < 2:
        return []

    id_to_index = {m.id: i for i, m in enumerate(movies)}
    texts = [_build_text(m) for m in movies]

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(texts)

    combined_scores = [0.0] * len(movies)
    valid_watched_indices = set()

    for watched_id in watched_movie_ids:
        idx = id_to_index.get(watched_id)
        if idx is None:
            continue
        valid_watched_indices.add(idx)
        sims = cosine_similarity(tfidf_matrix[idx], tfidf_matrix).flatten()
        for i, score in enumerate(sims):
            combined_scores[i] += score

    scored = [
        (movies[i], combined_scores[i])
        for i in range(len(movies))
        # loại bỏ chính những phim user ĐÃ XEM rồi ra khỏi gợi ý
        if i not in valid_watched_indices
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    return scored[:top_n]