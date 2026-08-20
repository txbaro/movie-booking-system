"""Canonicalize movies across ingestion providers.

Revision ID: 20260820_0006
Revises: 20260820_0005
Create Date: 2026-08-20
"""

import re
import unicodedata
from typing import Any, Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0006"
down_revision: str | Sequence[str] | None = "20260820_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RATING_SUFFIX_PATTERN = re.compile(
    r"(?:\s+(?:lt|rerun))?\s*\((?:t\d+|c\d+|p|k)\)\s*$",
    re.IGNORECASE,
)
TRAILING_VARIANT_PATTERN = re.compile(r"\s+(?:lt|rerun)\s*$", re.IGNORECASE)
SOURCE_PRIORITY = {None: 50, "galaxy": 40, "lotte": 30, "cinestar": 20}


def _clean_title(title: str) -> str:
    result = RATING_SUFFIX_PATTERN.sub("", title.strip())
    result = TRAILING_VARIANT_PATTERN.sub("", result)
    return result.strip(" -–—:")


def _normalize_title(title: str) -> str:
    cleaned = _clean_title(title).replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFKD", cleaned)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return "".join(
        character for character in without_accents.lower() if character.isalnum()
    )


def _priority(row: dict[str, Any]) -> int:
    if row.get("tmdb_id") is not None:
        return 100
    return SOURCE_PRIORITY.get(row.get("source"), 10)


def _meaningful(value: Any, placeholders: set[str]) -> bool:
    return bool(value and str(value).strip().lower() not in placeholders)


def _best_value(
    rows: list[dict[str, Any]], field: str, placeholders: set[str]
) -> Any:
    candidates = [row for row in rows if _meaningful(row.get(field), placeholders)]
    if not candidates:
        return rows[0].get(field)
    return max(candidates, key=_priority).get(field)


def upgrade() -> None:
    op.add_column("movies", sa.Column("normalized_title", sa.String(255)))
    op.add_column("movies", sa.Column("metadata_source", sa.String(50)))
    op.create_index(
        "ix_movies_normalized_title", "movies", ["normalized_title"], unique=False
    )

    op.create_table(
        "provider_movies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "movie_id",
            sa.Integer(),
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("genres", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Float(), nullable=False, server_default="0"),
        sa.Column("poster_url", sa.String(500)),
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_provider_movies_movie_id", "provider_movies", ["movie_id"], unique=False
    )
    op.create_index(
        "uq_provider_movies_source_external_id",
        "provider_movies",
        ["source", "external_id"],
        unique=True,
    )
    op.add_column("showtimes", sa.Column("provider_movie_id", sa.Integer()))
    op.create_foreign_key(
        "fk_showtimes_provider_movie_id_provider_movies",
        "showtimes",
        "provider_movies",
        ["provider_movie_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_showtimes_provider_movie_id",
        "showtimes",
        ["provider_movie_id"],
        unique=False,
    )

    connection = op.get_bind()
    movie_rows = [
        dict(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT id, title, genres, description, duration_minutes, rating,
                       poster_url, tmdb_id, source, external_id, last_synced_at
                FROM movies
                ORDER BY id
                """
            )
        ).mappings()
    ]

    groups: list[dict[str, Any]] = []
    for row in movie_rows:
        normalized = _normalize_title(row["title"])
        group = next(
            (
                candidate
                for candidate in groups
                if candidate["normalized"] == normalized
                and abs(candidate["duration"] - row["duration_minutes"]) <= 10
            ),
            None,
        )
        if group is None:
            groups.append(
                {
                    "normalized": normalized,
                    "duration": row["duration_minutes"],
                    "rows": [row],
                }
            )
        else:
            group["rows"].append(row)

    duplicate_ids: list[int] = []
    for group in groups:
        rows = group["rows"]
        canonical_id = min(row["id"] for row in rows)
        best = max(rows, key=_priority)
        title = _clean_title(best["title"])
        poster_url = _best_value(rows, "poster_url", set())
        genres = _best_value(
            rows, "genres", {"chưa phân loại", "chua phan loai", "unknown"}
        )
        description = _best_value(
            rows,
            "description",
            {
                "chưa có mô tả",
                "thông tin phim từ galaxy cinema.",
                "thông tin phim từ lotte cinema.",
                "thong tin phim tu galaxy cinema.",
                "thong tin phim tu lotte cinema.",
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE movies
                SET title = :title,
                    normalized_title = :normalized_title,
                    genres = :genres,
                    description = :description,
                    duration_minutes = :duration_minutes,
                    rating = :rating,
                    poster_url = :poster_url,
                    metadata_source = :metadata_source
                WHERE id = :id
                """
            ),
            {
                "id": canonical_id,
                "title": title,
                "normalized_title": group["normalized"],
                "genres": genres or "Chưa phân loại",
                "description": description or "Chưa có mô tả",
                "duration_minutes": best["duration_minutes"],
                "rating": max(float(row["rating"] or 0) for row in rows),
                "poster_url": poster_url,
                "metadata_source": best["source"] or (
                    "tmdb" if best["tmdb_id"] is not None else None
                ),
            },
        )

        for row in rows:
            provider_movie_id = None
            if row["source"] and row["external_id"]:
                provider_movie_id = connection.execute(
                    sa.text(
                        """
                        INSERT INTO provider_movies (
                            movie_id, source, external_id, title, genres,
                            description, duration_minutes, rating, poster_url,
                            last_synced_at
                        ) VALUES (
                            :movie_id, :source, :external_id, :title, :genres,
                            :description, :duration_minutes, :rating, :poster_url,
                            :last_synced_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        **row,
                        "movie_id": canonical_id,
                    },
                ).scalar_one()
            connection.execute(
                sa.text(
                    """
                    UPDATE showtimes
                    SET movie_id = :canonical_id,
                        provider_movie_id = :provider_movie_id
                    WHERE movie_id = :old_movie_id
                    """
                ),
                {
                    "canonical_id": canonical_id,
                    "provider_movie_id": provider_movie_id,
                    "old_movie_id": row["id"],
                },
            )
            if row["id"] != canonical_id:
                duplicate_ids.append(row["id"])

    if duplicate_ids:
        connection.execute(
            sa.text("DELETE FROM movies WHERE id = ANY(:ids)"),
            {"ids": duplicate_ids},
        )

    op.alter_column("movies", "normalized_title", nullable=False)
    op.drop_index("uq_movies_source_external_id", table_name="movies")
    op.drop_column("movies", "last_synced_at")
    op.drop_column("movies", "external_id")
    op.drop_column("movies", "source")


def downgrade() -> None:
    op.add_column("movies", sa.Column("source", sa.String(50)))
    op.add_column("movies", sa.Column("external_id", sa.String(255)))
    op.add_column("movies", sa.Column("last_synced_at", sa.DateTime(timezone=True)))

    connection = op.get_bind()
    mappings = list(
        connection.execute(
            sa.text(
                """
                SELECT id, movie_id, source, external_id, title, genres,
                       description, duration_minutes, rating, poster_url,
                       last_synced_at
                FROM provider_movies
                ORDER BY movie_id, id
                """
            )
        ).mappings()
    )
    used_movies: set[int] = set()
    for mapping in mappings:
        if mapping["movie_id"] not in used_movies:
            provider_movie_id = mapping["movie_id"]
            used_movies.add(mapping["movie_id"])
            connection.execute(
                sa.text(
                    """
                    UPDATE movies
                    SET source=:source, external_id=:external_id,
                        last_synced_at=:last_synced_at, title=:title,
                        genres=:genres, description=:description,
                        duration_minutes=:duration_minutes, rating=:rating,
                        poster_url=:poster_url
                    WHERE id=:movie_id
                    """
                ),
                {**mapping, "movie_id": provider_movie_id},
            )
        else:
            provider_movie_id = connection.execute(
                sa.text(
                    """
                    INSERT INTO movies (
                        title, normalized_title, genres, description,
                        duration_minutes, rating, poster_url, tmdb_id,
                        metadata_source, source, external_id, last_synced_at
                    ) VALUES (
                        :title, '', :genres, :description, :duration_minutes,
                        :rating, :poster_url, NULL, :source, :source,
                        :external_id, :last_synced_at
                    ) RETURNING id
                    """
                ),
                mapping,
            ).scalar_one()
        connection.execute(
            sa.text(
                "UPDATE showtimes SET movie_id=:movie_id "
                "WHERE provider_movie_id=:provider_mapping_id"
            ),
            {
                "movie_id": provider_movie_id,
                "provider_mapping_id": mapping["id"],
            },
        )

    op.create_index(
        "uq_movies_source_external_id",
        "movies",
        ["source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.drop_index("ix_showtimes_provider_movie_id", table_name="showtimes")
    op.drop_constraint(
        "fk_showtimes_provider_movie_id_provider_movies",
        "showtimes",
        type_="foreignkey",
    )
    op.drop_column("showtimes", "provider_movie_id")
    op.drop_index("uq_provider_movies_source_external_id", table_name="provider_movies")
    op.drop_index("ix_provider_movies_movie_id", table_name="provider_movies")
    op.drop_table("provider_movies")
    op.drop_index("ix_movies_normalized_title", table_name="movies")
    op.drop_column("movies", "metadata_source")
    op.drop_column("movies", "normalized_title")
