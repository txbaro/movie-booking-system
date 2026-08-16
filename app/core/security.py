"""
Xử lý bảo mật: hash password và tạo/giải mã JWT token.
Tách riêng khỏi route để dễ test độc lập và tái sử dụng ở nhiều nơi.
"""
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt: thuật toán hash password tiêu chuẩn, tự động thêm "salt" ngẫu nhiên
# cho mỗi password -> 2 user cùng password vẫn ra hash khác nhau, chống
# rainbow table attack.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    """
    Tạo JWT chứa `data` (thường là {"sub": user_id}) + thời gian hết hạn.
    "sub" (subject) là tên field chuẩn trong JWT để chỉ định "token này của ai".
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """
    Giải mã token, trả về None nếu token không hợp lệ hoặc đã hết hạn
    (thay vì raise exception) — để nơi gọi tự quyết định xử lý ra sao.
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None