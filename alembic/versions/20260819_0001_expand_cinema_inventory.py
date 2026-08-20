"""Expand cinema inventory schema and backfill legacy booking data.

Revision ID: 20260819_0001
Revises: None
Create Date: 2026-08-19
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260819_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return _inspector().has_table(name)


def _has_column(table: str, column: str) -> bool:
    return any(item["name"] == column for item in _inspector().get_columns(table))


def _has_index(table: str, name: str) -> bool:
    return any(item["name"] == name for item in _inspector().get_indexes(table))


def _has_unique(table: str, name: str) -> bool:
    return any(
        item["name"] == name for item in _inspector().get_unique_constraints(table)
    )


def _create_legacy_schema_if_missing() -> None:
    """Make the first revision usable for both empty and legacy databases."""
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("hashed_password", sa.String(255), nullable=False),
            sa.Column("full_name", sa.String(255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not _has_table("movies"):
        op.create_table(
            "movies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("genres", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("duration_minutes", sa.Integer(), nullable=False),
            sa.Column("rating", sa.Float(), nullable=False),
            sa.Column("poster_url", sa.String(500), nullable=True),
            sa.Column("tmdb_id", sa.Integer(), nullable=True),
            sa.UniqueConstraint("tmdb_id", name="uq_movies_tmdb_id"),
        )
        op.create_index("ix_movies_title", "movies", ["title"], unique=False)

    if not _has_table("showtimes"):
        op.create_table(
            "showtimes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("movie_id", sa.Integer(), nullable=False),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("room_rows", sa.Integer(), nullable=False),
            sa.Column("room_cols", sa.Integer(), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        )

    if not _has_table("seats"):
        postgresql.ENUM("AVAILABLE", "BOOKED", name="seatstatus").create(
            op.get_bind(), checkfirst=True
        )
        seat_status = postgresql.ENUM(
            "AVAILABLE", "BOOKED", name="seatstatus", create_type=False
        )
        op.create_table(
            "seats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("showtime_id", sa.Integer(), nullable=False),
            sa.Column("seat_label", sa.String(10), nullable=False),
            sa.Column("row_label", sa.String(5), nullable=False),
            sa.Column("col_number", sa.Integer(), nullable=False),
            sa.Column("status", seat_status, nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["showtime_id"], ["showtimes.id"]),
            sa.UniqueConstraint(
                "showtime_id", "seat_label", name="uq_showtime_seat"
            ),
        )

    if not _has_table("bookings"):
        op.create_table(
            "bookings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("showtime_id", sa.Integer(), nullable=False),
            sa.Column("seat_id", sa.Integer(), nullable=False),
            sa.Column(
                "booked_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["showtime_id"], ["showtimes.id"]),
            sa.ForeignKeyConstraint(["seat_id"], ["seats.id"]),
            sa.UniqueConstraint("seat_id", name="uq_bookings_seat_id"),
        )


def _expand_schema() -> None:
    if not _has_table("cinemas"):
        op.create_table(
            "cinemas",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("address", sa.Text(), nullable=False),
            sa.Column("city", sa.String(100), nullable=False),
        )

    if not _has_table("cinema_rooms"):
        op.create_table(
            "cinema_rooms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("cinema_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.ForeignKeyConstraint(
                ["cinema_id"], ["cinemas.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint("cinema_id", "name", name="uq_cinema_room_name"),
        )
    elif not _has_unique("cinema_rooms", "uq_cinema_room_name"):
        op.create_unique_constraint(
            "uq_cinema_room_name", "cinema_rooms", ["cinema_id", "name"]
        )

    if not _has_column("seats", "room_id"):
        op.add_column("seats", sa.Column("room_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_seats_room_id_cinema_rooms",
            "seats",
            "cinema_rooms",
            ["room_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _has_index("seats", "ix_seats_room_id"):
        op.create_index("ix_seats_room_id", "seats", ["room_id"])

    if not _has_column("showtimes", "room_id"):
        op.add_column("showtimes", sa.Column("room_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_showtimes_room_id_cinema_rooms",
            "showtimes",
            "cinema_rooms",
            ["room_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _has_index("showtimes", "ix_showtimes_room_id"):
        op.create_index("ix_showtimes_room_id", "showtimes", ["room_id"])

    seat_status = postgresql.ENUM(
        "AVAILABLE", "BOOKED", name="seatstatus", create_type=False
    )
    if not _has_table("showtime_seats"):
        op.create_table(
            "showtime_seats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("showtime_id", sa.Integer(), nullable=False),
            sa.Column("seat_id", sa.Integer(), nullable=False),
            sa.Column("status", seat_status, nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["showtime_id"], ["showtimes.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["seat_id"], ["seats.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "showtime_id", "seat_id", name="uq_showtime_seat_inventory"
            ),
        )
    if not _has_index("showtime_seats", "ix_showtime_seats_showtime_id"):
        op.create_index(
            "ix_showtime_seats_showtime_id", "showtime_seats", ["showtime_id"]
        )
    if not _has_index("showtime_seats", "ix_showtime_seats_seat_id"):
        op.create_index("ix_showtime_seats_seat_id", "showtime_seats", ["seat_id"])

    if not _has_table("booking_seats"):
        op.create_table(
            "booking_seats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("booking_id", sa.Integer(), nullable=False),
            sa.Column("showtime_seat_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(
                ["booking_id"], ["bookings.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["showtime_seat_id"], ["showtime_seats.id"], ondelete="RESTRICT"
            ),
            sa.UniqueConstraint(
                "showtime_seat_id", name="uq_booking_showtime_seat"
            ),
        )
    if not _has_index("booking_seats", "ix_booking_seats_booking_id"):
        op.create_index("ix_booking_seats_booking_id", "booking_seats", ["booking_id"])
    if not _has_index("booking_seats", "ix_booking_seats_showtime_seat_id"):
        op.create_index(
            "ix_booking_seats_showtime_seat_id",
            "booking_seats",
            ["showtime_seat_id"],
        )

    seat_id_column = next(
        column
        for column in _inspector().get_columns("bookings")
        if column["name"] == "seat_id"
    )
    if not seat_id_column["nullable"]:
        op.alter_column(
            "bookings", "seat_id", existing_type=sa.Integer(), nullable=True
        )


def _backfill_data() -> None:
    bind = op.get_bind()
    cinema_id = bind.execute(
        sa.text("SELECT id FROM cinemas WHERE name = :name ORDER BY id LIMIT 1"),
        {"name": "Legacy Cinema"},
    ).scalar_one_or_none()
    if cinema_id is None:
        cinema_id = bind.execute(
            sa.text(
                """
                INSERT INTO cinemas (name, address, city)
                VALUES (:name, :address, :city)
                RETURNING id
                """
            ),
            {
                "name": "Legacy Cinema",
                "address": "Imported from legacy showtimes",
                "city": "Unknown",
            },
        ).scalar_one()

    showtime_ids = bind.execute(
        sa.text("SELECT id FROM showtimes WHERE room_id IS NULL ORDER BY id")
    ).scalars()
    for showtime_id in showtime_ids:
        room_name = f"Legacy Room {showtime_id}"
        room_id = bind.execute(
            sa.text(
                """
                SELECT id FROM cinema_rooms
                WHERE cinema_id = :cinema_id AND name = :name
                """
            ),
            {"cinema_id": cinema_id, "name": room_name},
        ).scalar_one_or_none()
        if room_id is None:
            room_id = bind.execute(
                sa.text(
                    """
                    INSERT INTO cinema_rooms (cinema_id, name)
                    VALUES (:cinema_id, :name)
                    RETURNING id
                    """
                ),
                {"cinema_id": cinema_id, "name": room_name},
            ).scalar_one()
        bind.execute(
            sa.text("UPDATE showtimes SET room_id = :room_id WHERE id = :id"),
            {"room_id": room_id, "id": showtime_id},
        )

    bind.execute(
        sa.text(
            """
            UPDATE seats AS seat
            SET room_id = showtime.room_id
            FROM showtimes AS showtime
            WHERE seat.showtime_id = showtime.id AND seat.room_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO showtime_seats (showtime_id, seat_id, status, version)
            SELECT showtime_id, id, status, version FROM seats
            ON CONFLICT (showtime_id, seat_id) DO NOTHING
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO booking_seats (booking_id, showtime_seat_id)
            SELECT booking.id, inventory.id
            FROM bookings AS booking
            JOIN showtime_seats AS inventory
              ON inventory.showtime_id = booking.showtime_id
             AND inventory.seat_id = booking.seat_id
            WHERE booking.seat_id IS NOT NULL
            ON CONFLICT (showtime_seat_id) DO NOTHING
            """
        )
    )


def _assert_integrity() -> None:
    bind = op.get_bind()
    checks = {
        "showtimes without room": "SELECT count(*) FROM showtimes WHERE room_id IS NULL",
        "seats without room": "SELECT count(*) FROM seats WHERE room_id IS NULL",
        "seats without inventory": """
            SELECT count(*) FROM seats AS seat
            LEFT JOIN showtime_seats AS inventory
              ON inventory.showtime_id = seat.showtime_id
             AND inventory.seat_id = seat.id
            WHERE inventory.id IS NULL
        """,
        "legacy bookings without booking seat": """
            SELECT count(*) FROM bookings AS booking
            LEFT JOIN booking_seats AS item ON item.booking_id = booking.id
            WHERE booking.seat_id IS NOT NULL AND item.id IS NULL
        """,
    }
    failures = {
        name: bind.execute(sa.text(query)).scalar_one()
        for name, query in checks.items()
    }
    failures = {name: count for name, count in failures.items() if count}
    if failures:
        details = ", ".join(f"{name}={count}" for name, count in failures.items())
        raise RuntimeError(f"Cinema inventory backfill failed integrity checks: {details}")


def upgrade() -> None:
    _create_legacy_schema_if_missing()
    _expand_schema()
    _backfill_data()
    _assert_integrity()


def downgrade() -> None:
    if _has_table("booking_seats"):
        op.drop_table("booking_seats")
    if _has_table("showtime_seats"):
        op.drop_table("showtime_seats")
    if _has_column("showtimes", "room_id"):
        op.drop_index("ix_showtimes_room_id", table_name="showtimes")
        op.drop_column("showtimes", "room_id")
    if _has_column("seats", "room_id"):
        op.drop_index("ix_seats_room_id", table_name="seats")
        op.drop_column("seats", "room_id")
    if _has_table("cinema_rooms"):
        op.drop_table("cinema_rooms")
    if _has_table("cinemas"):
        op.drop_table("cinemas")

    null_bookings = op.get_bind().execute(
        sa.text("SELECT count(*) FROM bookings WHERE seat_id IS NULL")
    ).scalar_one()
    if null_bookings:
        raise RuntimeError("Cannot restore bookings.seat_id NOT NULL while NULL rows exist")
    op.alter_column("bookings", "seat_id", existing_type=sa.Integer(), nullable=False)
