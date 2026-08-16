from pydantic import BaseModel

from app.schemas.movie import MovieRead


class RecommendedMovie(BaseModel):
    movie: MovieRead
    similarity_score: float