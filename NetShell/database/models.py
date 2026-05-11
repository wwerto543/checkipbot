from sqlalchemy import BigInteger, String, Boolean, DateTime, func, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True) # Telegram ID
    username: Mapped[str] = mapped_column(String, nullable=True)
    reg_date: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Права и статусы
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Статистика
    requests_count: Mapped[int] = mapped_column(Integer, default=0)

class ProxyPool(Base):
    __tablename__ = "proxy_pool"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String, unique=True) # ip:port
    proxy_type: Mapped[str] = mapped_column(String) # socks5 / http
    country: Mapped[str] = mapped_column(String(10)) # RU, US и т.д.
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())