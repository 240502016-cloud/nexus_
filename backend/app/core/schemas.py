from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.models import ChannelType
from app.core.permissions import Permission


# ---- User ----


class UserBase(BaseModel):
    username: str
    email: EmailStr
    display_name: str | None = None
    avatar_url: str | None = None


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    matrix_user_id: str | None = None
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """Kullanıcının kendi profilinde düzenleyebileceği alanlar."""

    display_name: str | None = Field(default=None, max_length=64)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)


# ---- Server Member ----


class MemberRead(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    joined_at: datetime


# ---- Server ----


class ServerBase(BaseModel):
    name: str
    description: str | None = None
    icon_url: str | None = None


class ServerCreate(ServerBase):
    pass


class ServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class ServerRead(ServerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_at: datetime


# ---- Channel ----


class ChannelBase(BaseModel):
    name: str
    type: ChannelType = ChannelType.TEXT
    topic: str | None = None
    position: int = 0


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    topic: str | None = None


class ChannelRead(ChannelBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    server_id: int
    matrix_room_id: str | None = None
    created_at: datetime


# ---- Role ----


class RoleBase(BaseModel):
    name: str
    color: str | None = None
    position: int = 0
    permissions: int = int(Permission.default())
    is_default: bool = False


class RoleCreate(RoleBase):
    pass


class RoleRead(RoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    server_id: int
    created_at: datetime


# ---- Message ----
# Mesajlar Postgres'te değil, Matrix odalarında yaşar; bu yüzden ORM modeli yok.


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    # İstemcinin iyimser mesajını Matrix event'iyle güvenle eşleştirir ve aynı isteğin
    # ağ hatasında yinelenmesi halinde Matrix transaction de-duplication anahtarı olur.
    client_id: str | None = Field(default=None, min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class MessageRead(BaseModel):
    event_id: str
    sender: str
    content: str
    origin_server_ts: int | None = None
    client_id: str | None = None
    is_bot: bool = False
    # Özel bot komutları (örn. gizli oyun hamlesi) Matrix'e yazılmaz. İstemci bu yanıtı
    # alınca iyimser komut balonunu kaldırır.
    hidden: bool = False


# ---- Plugin ----
# plugins/<isim>/plugin.json dosya sisteminde yaşar; installed/enabled durumu Postgres'te.


class PluginManifestRead(BaseModel):
    name: str
    version: str
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    installed: bool = False
    enabled: bool = False
    requires_bot_link: bool = False


class PluginCommandRequest(BaseModel):
    command: str
    args: str = ""


class PluginCommandResult(BaseModel):
    plugin: str
    command: str
    output: str


# ---- Bot ----


class BotCreate(BaseModel):
    name: str
    command_prefix: str = "/"


class BotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    command_prefix: str
    matrix_user_id: str | None = None
    is_active: bool
    created_at: datetime
    plugin_names: list[str] = Field(default_factory=list)
