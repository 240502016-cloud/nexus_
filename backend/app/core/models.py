from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
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


class Friendship(Base):
    """İki kullanıcı arasındaki tekil arkadaşlık/istek kaydı ve isteğe bağlı DM odası."""

    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("user_low_id", "user_high_id", name="uq_friendship_pair"),
        CheckConstraint("user_low_id < user_high_id", name="ck_friendship_order"),
        Index("ix_friendships_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_low_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    user_high_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    matrix_room_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    matrix_owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    low_user: Mapped["User"] = relationship(foreign_keys=[user_low_id])
    high_user: Mapped["User"] = relationship(foreign_keys=[user_high_id])
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_id])
    matrix_owner: Mapped["User | None"] = relationship(foreign_keys=[matrix_owner_id])

    def other_user(self, user_id: int) -> "User":
        return self.high_user if self.user_low_id == user_id else self.low_user


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


class ServerInvite(Base):
    """Bir arkadaşın sunucuya katılmadan önce kabul veya ret verebildiği kalıcı davet."""

    __tablename__ = "server_invites"
    __table_args__ = (
        UniqueConstraint("server_id", "invitee_id", name="uq_server_invite_target"),
        Index("ix_server_invites_invitee_status", "invitee_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    invitee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    server: Mapped["Server"] = relationship()
    inviter: Mapped["User"] = relationship(foreign_keys=[inviter_id])
    invitee: Mapped["User"] = relationship(foreign_keys=[invitee_id])


class ServerJoinCode(Base):
    """Arkadaşlık gerektirmeden bir sunucuya katılmayı sağlayan iptal edilebilir paylaşım kodu."""

    __tablename__ = "server_join_codes"
    __table_args__ = (Index("ix_server_join_codes_code", "code", unique=True),)

    server_id: Mapped[int] = mapped_column(
        ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True
    )
    code: Mapped[str] = mapped_column(String(32))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    server: Mapped["Server"] = relationship()
    created_by: Mapped["User"] = relationship()


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
    bot_links: Mapped[list["BotPluginLink"]] = relationship(
        back_populates="plugin", cascade="all, delete-orphan"
    )


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
    plugin_links: Mapped[list["BotPluginLink"]] = relationship(
        back_populates="bot", cascade="all, delete-orphan"
    )

    @property
    def plugin_names(self) -> list[str]:
        return sorted(link.plugin_name for link in self.plugin_links)


class BotServerLink(Base):
    """Bir botun hangi sunucuya eklendiği — bot yetki kontrolünün temeli: bir bot,
    eklenmediği bir sunucuda hiçbir komuta cevap vermez."""

    __tablename__ = "bot_server_links"

    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bot: Mapped["Bot"] = relationship(back_populates="server_links")
    server: Mapped["Server"] = relationship()


class BotPluginLink(Base):
    """Bota özel plugin bağı; şans oyunları gibi bot kimliği gerektiren pluginler içindir."""

    __tablename__ = "bot_plugin_links"

    bot_id: Mapped[int] = mapped_column(ForeignKey("bots.id", ondelete="CASCADE"), primary_key=True)
    plugin_name: Mapped[str] = mapped_column(
        ForeignKey("plugins.name", ondelete="CASCADE"), primary_key=True
    )
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    bot: Mapped["Bot"] = relationship(back_populates="plugin_links")
    plugin: Mapped["Plugin"] = relationship(back_populates="bot_links")


class ChanceGameSession(Base):
    """İki oyunculu şans oyunu daveti ve gizli hamlelerinin kalıcı durumu."""

    __tablename__ = "chance_game_sessions"
    __table_args__ = (
        Index("ix_chance_game_open", "server_id", "status"),
        Index("ix_chance_game_participants", "challenger_id", "opponent_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    game_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    challenger_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    opponent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    challenger_move: Mapped[str | None] = mapped_column(String(16), nullable=True)
    opponent_move: Mapped[str | None] = mapped_column(String(16), nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    challenger: Mapped["User"] = relationship(foreign_keys=[challenger_id])
    opponent: Mapped["User"] = relationship(foreign_keys=[opponent_id])
    server: Mapped["Server"] = relationship()
    channel: Mapped["Channel"] = relationship()


class ChanceWheel(Base):
    """Her kullanıcı ve kanal için ayrı, yeniden başlatmada kaybolmayan çark."""

    __tablename__ = "chance_wheels"
    __table_args__ = (
        UniqueConstraint("channel_id", "owner_id", name="uq_chance_wheel_channel_owner"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    server_id: Mapped[int] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    entries: Mapped[list[dict]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    owner: Mapped["User"] = relationship()
    server: Mapped["Server"] = relationship()
    channel: Mapped["Channel"] = relationship()
