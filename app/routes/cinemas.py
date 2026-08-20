import string

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.cinema import Cinema
from app.models.cinema_room import CinemaRoom
from app.models.seat import Seat
from app.models.showtime import Showtime
from app.schemas.cinema import (
    CinemaCreate,
    CinemaDetail,
    CinemaRead,
    CinemaRoomCreate,
    CinemaRoomDetail,
    CinemaRoomRead,
    CinemaRoomUpdate,
    CinemaUpdate,
    PhysicalSeatRead,
)
from app.services.discovery import distance_km, utc_now

router = APIRouter(tags=["cinemas"])


def _room_read(room: CinemaRoom, seat_count: int) -> CinemaRoomRead:
    return CinemaRoomRead(
        id=room.id,
        cinema_id=room.cinema_id,
        name=room.name,
        seat_count=seat_count,
        source=room.source,
        external_id=room.external_id,
        last_synced_at=room.last_synced_at,
    )


@router.post("/cinemas", response_model=CinemaRead, status_code=status.HTTP_201_CREATED)
async def create_cinema(payload: CinemaCreate, db: AsyncSession = Depends(get_db)):
    cinema = Cinema(**payload.model_dump())
    db.add(cinema)
    await db.commit()
    await db.refresh(cinema)
    return cinema


@router.get("/cinemas", response_model=list[CinemaRead])
async def list_cinemas(
    city: str | None = None,
    source: str | None = None,
    has_upcoming_showtimes: bool = False,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float | None = Query(default=None, gt=0, le=500),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=422, detail="latitude và longitude phải được gửi cùng nhau"
        )
    if radius_km is not None and latitude is None:
        raise HTTPException(
            status_code=422, detail="radius_km yêu cầu latitude và longitude"
        )

    query = select(Cinema)
    if city:
        query = query.where(Cinema.city.ilike(f"%{city}%"))
    if source:
        query = query.where(Cinema.source == source)
    if has_upcoming_showtimes:
        query = query.where(
            select(Showtime.id)
            .where(
                Showtime.cinema_id == Cinema.id,
                Showtime.start_time >= utc_now(),
            )
            .exists()
        )

    cinemas = list((await db.execute(query)).scalars().all())
    items: list[CinemaRead] = []
    for cinema in cinemas:
        item = CinemaRead.model_validate(cinema)
        if latitude is not None and cinema.latitude is not None:
            item.distance_km = round(
                distance_km(
                    latitude,
                    longitude,
                    float(cinema.latitude),
                    float(cinema.longitude),
                ),
                2,
            )
        if radius_km is None or (
            item.distance_km is not None and item.distance_km <= radius_km
        ):
            items.append(item)

    if latitude is not None:
        items.sort(
            key=lambda item: (
                item.distance_km is None,
                item.distance_km if item.distance_km is not None else float("inf"),
                item.name,
            )
        )
    else:
        items.sort(key=lambda item: (item.city, item.name))
    return items[skip : skip + limit]


@router.get("/cinemas/{cinema_id}", response_model=CinemaDetail)
async def get_cinema(cinema_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Cinema)
        .where(Cinema.id == cinema_id)
        .options(selectinload(Cinema.rooms).selectinload(CinemaRoom.seats))
    )
    cinema = result.scalar_one_or_none()
    if cinema is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy rạp")
    return CinemaDetail(
        id=cinema.id,
        name=cinema.name,
        address=cinema.address,
        city=cinema.city,
        latitude=cinema.latitude,
        longitude=cinema.longitude,
        source=cinema.source,
        external_id=cinema.external_id,
        last_synced_at=cinema.last_synced_at,
        rooms=[_room_read(room, len(room.seats)) for room in cinema.rooms],
    )


@router.patch("/cinemas/{cinema_id}", response_model=CinemaRead)
async def update_cinema(
    cinema_id: int,
    payload: CinemaUpdate,
    db: AsyncSession = Depends(get_db),
):
    cinema = await db.get(Cinema, cinema_id)
    if cinema is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy rạp")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cinema, field, value)
    await db.commit()
    await db.refresh(cinema)
    return cinema


@router.delete("/cinemas/{cinema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cinema(cinema_id: int, db: AsyncSession = Depends(get_db)):
    cinema = await db.get(Cinema, cinema_id)
    if cinema is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy rạp")
    showtime_count = await db.scalar(
        select(func.count(Showtime.id)).where(Showtime.cinema_id == cinema_id)
    )
    if showtime_count:
        raise HTTPException(status_code=409, detail="Rạp đang có suất chiếu")
    await db.delete(cinema)
    await db.commit()


@router.post(
    "/cinemas/{cinema_id}/rooms",
    response_model=CinemaRoomDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_room(
    cinema_id: int,
    payload: CinemaRoomCreate,
    db: AsyncSession = Depends(get_db),
):
    if await db.get(Cinema, cinema_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy rạp")
    room = CinemaRoom(cinema_id=cinema_id, name=payload.name)
    db.add(room)
    try:
        await db.flush()
        seats = [
            Seat(
                room_id=room.id,
                showtime_id=None,
                seat_label=f"{string.ascii_uppercase[row]}{column}",
                row_label=string.ascii_uppercase[row],
                col_number=column,
            )
            for row in range(payload.rows)
            for column in range(1, payload.cols + 1)
        ]
        db.add_all(seats)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tên phòng đã tồn tại") from exc
    await db.refresh(room)
    return CinemaRoomDetail(
        **_room_read(room, len(seats)).model_dump(),
        seats=[PhysicalSeatRead.model_validate(seat) for seat in seats],
    )


@router.get("/cinemas/{cinema_id}/rooms", response_model=list[CinemaRoomRead])
async def list_rooms(cinema_id: int, db: AsyncSession = Depends(get_db)):
    if await db.get(Cinema, cinema_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy rạp")
    result = await db.execute(
        select(CinemaRoom, func.count(Seat.id))
        .outerjoin(Seat, Seat.room_id == CinemaRoom.id)
        .where(CinemaRoom.cinema_id == cinema_id)
        .group_by(CinemaRoom.id)
        .order_by(CinemaRoom.name)
    )
    return [_room_read(room, count) for room, count in result.all()]


@router.get("/rooms/{room_id}", response_model=CinemaRoomDetail)
async def get_room(room_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CinemaRoom)
        .where(CinemaRoom.id == room_id)
        .options(selectinload(CinemaRoom.seats))
    )
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng")
    seats = sorted(room.seats, key=lambda seat: (seat.row_label, seat.col_number))
    return CinemaRoomDetail(
        **_room_read(room, len(seats)).model_dump(),
        seats=[PhysicalSeatRead.model_validate(seat) for seat in seats],
    )


@router.patch("/rooms/{room_id}", response_model=CinemaRoomRead)
async def update_room(
    room_id: int,
    payload: CinemaRoomUpdate,
    db: AsyncSession = Depends(get_db),
):
    room = await db.get(CinemaRoom, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng")
    room.name = payload.name
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Tên phòng đã tồn tại") from exc
    seat_count = await db.scalar(select(func.count(Seat.id)).where(Seat.room_id == room_id))
    return _room_read(room, seat_count or 0)


@router.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(room_id: int, db: AsyncSession = Depends(get_db)):
    room = await db.get(CinemaRoom, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phòng")
    showtime_count = await db.scalar(
        select(func.count(Showtime.id)).where(Showtime.room_id == room_id)
    )
    if showtime_count:
        raise HTTPException(status_code=409, detail="Phòng đang có suất chiếu")
    await db.delete(room)
    await db.commit()
