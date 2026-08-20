from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.movie import Movie
from app.models.showtime import BookingMode, Showtime
from app.models.user import User
from app.models.user_event import UserEvent
from app.schemas.event import TrackEventResponse, UserEventCreate, UserEventRead
from app.services.discovery import utc_now

router = APIRouter(prefix="/events", tags=["behavior events"])

DEDUPLICATION_WINDOW = timedelta(minutes=2)


@router.post(
    "",
    response_model=TrackEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def track_event(
    payload: UserEventCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    movie_id = payload.movie_id
    cinema_id = None
    showtime_id = payload.showtime_id
    source = None
    search_query = payload.search_query.strip() if payload.search_query else None
    context_id = payload.context_id

    if showtime_id is not None:
        showtime = await db.get(Showtime, showtime_id)
        if showtime is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy suất chiếu")
        if (
            payload.event_type == "external_booking_clicked"
            and showtime.booking_mode != BookingMode.EXTERNAL_REDIRECT.value
        ):
            raise HTTPException(
                status_code=409,
                detail="Event external chỉ áp dụng cho suất đặt tại website rạp",
            )
        movie_id = showtime.movie_id
        cinema_id = showtime.cinema_id
        source = showtime.source
    elif movie_id is not None and await db.get(Movie, movie_id) is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phim")

    filters = [
        UserEvent.user_id == current_user.id,
        UserEvent.event_type == payload.event_type,
        UserEvent.occurred_at >= utc_now() - DEDUPLICATION_WINDOW,
        UserEvent.movie_id == movie_id if movie_id is not None else UserEvent.movie_id.is_(None),
        UserEvent.showtime_id == showtime_id
        if showtime_id is not None
        else UserEvent.showtime_id.is_(None),
        UserEvent.search_query == search_query
        if search_query is not None
        else UserEvent.search_query.is_(None),
        UserEvent.context_id == context_id
        if context_id is not None
        else UserEvent.context_id.is_(None),
    ]
    existing = await db.scalar(
        select(UserEvent).where(*filters).order_by(UserEvent.occurred_at.desc())
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return TrackEventResponse(event=existing, deduplicated=True)

    event = UserEvent(
        user_id=current_user.id,
        event_type=payload.event_type,
        movie_id=movie_id,
        cinema_id=cinema_id,
        showtime_id=showtime_id,
        source=source,
        search_query=search_query,
        context_id=context_id,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return TrackEventResponse(event=event, deduplicated=False)


@router.get("/me", response_model=list[UserEventRead])
async def list_my_events(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserEvent)
        .where(UserEvent.user_id == current_user.id)
        .order_by(UserEvent.occurred_at.desc())
        .limit(limit)
    )
    return list(result.scalars())
