from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import Permission
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class ChannelType(str, enum.Enum):
    TEXT = "text"
    VOICE = "voice"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    matrix_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    # Core API'nin bu kullanıcı adına Matrix'te oda/mesaj işlemi yapması için;
    # asla API şemalarında dışarı verilmez (bkz. schemas.UserRead).
    matrix_access_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owned_servers: Mapped[list["Server"]] = relationship(back_populates="owner")
    memberships: Mapped[list["ServerMember"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="members")


class Server(Base):
    __tablename__ = "servers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    owner: Mapped["User"] = relationship(back_populates="owned_servers")
    channels: Mapped[list["Channel"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )
    roles: Mapped[list["Role"]] = relationship(back_populates="server", cascade="all, delete-orphan")
    members: Mapped[list["ServerMember"]] = relationship(
        back_populates="server", cascade="all, delete-orphan"
    )


class ServerMember(Base):
    """Bir kullanıcının bir sunucudaki üyeliği (takma ad, katılma tarihi vb.).

    Roller doğrudan User<->Role ilişkisi üzerinden tutulur; bu tablo sadece
    sunucuya özgü üyelik bilgisini taşır.
    """

    __tablename__ = "server_members"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="memberships")
    server: Mapped["Server"] = relationship(back_populates="members")


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[ChannelType] = mapped_column(SAEnum(ChannelType), default=ChannelType.TEXT)
    topic: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    matrix_room_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    server: Mapped["Server"] = relationship(back_populates="channels")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # "#RRGGBB"
    position: Mapped[int] = mapped_column(Integer, default=0)
    permissions: Mapped[int] = mapped_column(Integer, default=int(Permission.default()))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)  # @everyone benzeri
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    server: Mapped["Server"] = relationship(back_populates="roles")
    members: Mapped[list["User"]] = relationship(secondary=user_roles, back_populates="roles")

    def has_permission(self, permission: Permission) -> bool:
        current = Permission(self.permissions)
        return bool(current & Permission.ADMINISTRATOR) or bool(current & permission)


class Plugin(Base):
    """`plugins/<name>/` altında keşfedilen bir plugin'in kurulum durumu.

    Dosya sistemindeki plugin.json ile eşleşir; burada sadece hangi plugin'lerin
    kurulu/etkin olduğu tutulur (bkz. app/plugins_engine/loader.py).
    """

    __tablename__ = "plugins"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Bot(Base):
    """Botlar normal kullanıcı değil, servistir: kendi Matrix hesabıyla kanallara
    mesaj yazabilir, ama sadece eklendiği sunucularda (bkz. BotServerLink) çalışır."""

    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    command_prefix: Mapped[str] = mapped_column(String(8), default="/")
    matrix_user_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    matrix_access_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    server_links: Mapped[list["BotServerLink"]] = relationship(
        back_populates="bot", cascade="all, delete-orphan"
    )


class BotServerLink(Base):
    """Bir botun hangi sunucuya eklendiği — bot yetki kontrolünün temeli: bir bot,
    eklenmediği bir sunucuda hiçbir komuta cevap vermez."""

    __tablename__ = "bot_server_links"

    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bot: Mapped["Bot"] = relationship(back_populates="server_links")
    server: Mapped["Server"] = relationship()
