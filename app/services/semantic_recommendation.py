import hashlib
import json
import logging
from math import sqrt

import httpx
from redis.exceptions import RedisError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import FeatureUnion
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis_client import redis_client
from app.models.movie import Movie
from app.models.movie_embedding import MovieEmbedding


logger = logging.getLogger(__name__)


def movie_embedding_document(movie: Movie) -> str:
    return (
        f"Tên phim: {movie.title}. "
        f"Thể loại: {movie.genres or 'chưa rõ'}. "
        f"Mô tả: {movie.description or 'chưa có mô tả'}. "
        f"Thời lượng: {movie.duration_minutes} phút."
    )


def _content_hash(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


def _gemini_query_document(prompt: str) -> str:
    return f"task: search result | query: {prompt}"


def _gemini_movie_document(movie: Movie, document: str) -> str:
    return f"title: {movie.title} | text: {document}"


def _prompt_cache_key(prompt: str) -> str:
    normalized = " ".join(prompt.lower().split())
    digest = hashlib.sha256(
        f"gemini:{settings.GEMINI_EMBEDDING_MODEL}:{normalized}".encode("utf-8")
    ).hexdigest()
    return f"prompt_embedding:{digest}"


async def _get_cached_prompt_embedding(prompt: str) -> list[float] | None:
    try:
        payload = await redis_client.get(_prompt_cache_key(prompt))
        if payload is None:
            return None
        vector = json.loads(payload)
        if not isinstance(vector, list) or not vector:
            return None
        return [float(value) for value in vector]
    except (RedisError, TypeError, ValueError, json.JSONDecodeError):
        return None


async def _cache_prompt_embedding(prompt: str, vector: list[float]) -> None:
    try:
        await redis_client.set(
            _prompt_cache_key(prompt),
            json.dumps(vector),
            ex=settings.AI_PROMPT_CACHE_TTL_SECONDS,
        )
    except RedisError:
        logger.warning("Redis prompt embedding cache is unavailable")


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    denominator = sqrt(sum(value * value for value in left)) * sqrt(
        sum(value * value for value in right)
    )
    if denominator == 0:
        return 0.0
    return max(0.0, min(1.0, sum(a * b for a, b in zip(left, right)) / denominator))


async def _request_embeddings(texts: list[str]) -> list[list[float]]:
    model = settings.GEMINI_EMBEDDING_MODEL
    model_resource = f"models/{model}"
    endpoint = (
        f"{settings.GEMINI_API_BASE_URL.rstrip('/')}"
        f"/{model_resource}:batchEmbedContents"
    )
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.GEMINI_API_KEY,
    }
    requests = [
        {
            "model": model_resource,
            "content": {"parts": [{"text": text}]},
        }
        for text in texts
    ]
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            endpoint,
            headers=headers,
            json={"requests": requests},
        )
        response.raise_for_status()
    payload = response.json()
    vectors = [row["values"] for row in payload["embeddings"]]
    if len(vectors) != len(texts) or any(not vector for vector in vectors):
        raise ValueError("Embedding API trả về sai số lượng vector")
    return [[float(value) for value in vector] for vector in vectors]


async def _api_semantic_scores(
    db: AsyncSession,
    movies: list[Movie],
    prompt: str,
) -> dict[int, float]:
    cached = {
        row.movie_id: row
        for row in (
            await db.scalars(
                select(MovieEmbedding).where(
                    MovieEmbedding.movie_id.in_([movie.id for movie in movies])
                )
            )
        ).all()
    }
    documents = {movie.id: movie_embedding_document(movie) for movie in movies}
    missing = [
        movie
        for movie in movies
        if movie.id not in cached
        or cached[movie.id].content_hash != _content_hash(documents[movie.id])
        or cached[movie.id].model != settings.GEMINI_EMBEDDING_MODEL
        or cached[movie.id].provider != "gemini"
    ]

    query_vector = await _get_cached_prompt_embedding(prompt)
    request_texts = [
        _gemini_movie_document(movie, documents[movie.id]) for movie in missing
    ]
    query_was_missing = query_vector is None
    if query_was_missing:
        request_texts.insert(0, _gemini_query_document(prompt))
    vectors = await _request_embeddings(request_texts) if request_texts else []
    if query_was_missing:
        query_vector = vectors[0]
        await _cache_prompt_embedding(prompt, query_vector)
        vectors = vectors[1:]

    for movie, vector in zip(missing, vectors):
        cache = cached.get(movie.id)
        if cache is None:
            cache = MovieEmbedding(movie_id=movie.id)
            db.add(cache)
            cached[movie.id] = cache
        cache.provider = "gemini"
        cache.model = settings.GEMINI_EMBEDDING_MODEL
        cache.content_hash = _content_hash(documents[movie.id])
        cache.dimensions = len(vector)
        cache.vector = vector
    await db.flush()

    return {
        movie.id: _cosine(query_vector, cached[movie.id].vector)
        for movie in movies
    }


def _local_semantic_scores(movies: list[Movie], prompt: str) -> dict[int, float]:
    documents = [movie_embedding_document(movie) for movie in movies]
    vectorizer = FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    strip_accents="unicode",
                    sublinear_tf=True,
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    strip_accents="unicode",
                    min_df=1,
                ),
            ),
        ]
    )
    matrix = vectorizer.fit_transform([prompt, *documents])
    scores = cosine_similarity(matrix[0], matrix[1:]).flatten()
    return {movie.id: float(scores[index]) for index, movie in enumerate(movies)}


async def get_semantic_scores(
    db: AsyncSession,
    movies: list[Movie],
    prompt: str,
) -> tuple[dict[int, float], str]:
    if not movies:
        return {}, "none"
    if settings.GEMINI_API_KEY and settings.GEMINI_EMBEDDING_MODEL:
        try:
            return await _api_semantic_scores(db, movies, prompt), "gemini_embedding"
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Gemini API unavailable, using local fallback: %s", exc)
    return _local_semantic_scores(movies, prompt), "local_tfidf_fallback"
