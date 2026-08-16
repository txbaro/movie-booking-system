from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "access_token"


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    # Kiểm tra email đã tồn tại chưa — tránh lỗi IntegrityError mơ hồ từ DB,
    # trả lỗi rõ ràng cho client thay vì lỗi 500.
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email đã được đăng ký")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=UserRead)
async def login(payload: UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Cố ý dùng CHUNG 1 thông báo lỗi cho cả 2 trường hợp "email không tồn tại"
    # và "sai password" — tránh lộ thông tin email nào đã đăng ký hay chưa
    # (kẻ tấn công dò email không nên biết được email đó "có tồn tại").
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")

    token = create_access_token(data={"sub": str(user.id)})

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,       # JavaScript không đọc được cookie này -> chống XSS
        samesite="lax",      # chống CSRF cơ bản, vẫn cho phép link từ ngoài vào hoạt động
        secure=False,        # ĐỔI THÀNH True khi deploy thật với HTTPS
        max_age=60 * 60,     # 1 giờ, tính bằng giây — nên khớp ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return user


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Đã đăng xuất"}


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    """Endpoint tiện để TEST xem cookie/JWT có hoạt động đúng không."""
    return current_user