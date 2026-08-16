"""
Dependency dùng trong route để lấy user hiện tại từ JWT trong cookie.
Cách dùng: current_user: User = Depends(get_current_user)
FastAPI sẽ tự chạy hàm này trước khi vào route, và raise 401 nếu chưa đăng nhập.
"""
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Chưa đăng nhập hoặc phiên đăng nhập đã hết hạn",
)


async def get_current_user(
    access_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Cookie(default=None): FastAPI tự đọc cookie tên "access_token" từ request
    (tên này phải KHỚP với tên cookie được set lúc login — xem app/routes/auth.py)
    """
    if access_token is None:
        raise CREDENTIALS_EXCEPTION

    payload = decode_access_token(access_token)
    if payload is None:
        raise CREDENTIALS_EXCEPTION

    user_id = payload.get("sub")
    if user_id is None:
        raise CREDENTIALS_EXCEPTION

    user = await db.get(User, int(user_id))
    if user is None:
        raise CREDENTIALS_EXCEPTION

    return user