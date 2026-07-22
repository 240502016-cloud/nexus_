from enum import IntFlag, auto


class Permission(IntFlag):
    """Role.permissions kolonunda saklanan bitmask. Discord'daki permission
    flag mantığına benzer: her bit tek bir yetkiyi temsil eder."""

    VIEW_CHANNELS = auto()
    SEND_MESSAGES = auto()
    MANAGE_MESSAGES = auto()
    CONNECT = auto()
    SPEAK = auto()
    SHARE_SCREEN = auto()
    ATTACH_FILES = auto()
    MANAGE_CHANNELS = auto()
    MANAGE_ROLES = auto()
    KICK_MEMBERS = auto()
    BAN_MEMBERS = auto()
    MANAGE_SERVER = auto()
    MANAGE_PLUGINS = auto()
    MANAGE_BOTS = auto()
    ADMINISTRATOR = auto()

    @classmethod
    def default(cls) -> "Permission":
        """Yeni oluşturulan @everyone benzeri varsayılan rol için temel yetkiler."""
        return cls.VIEW_CHANNELS | cls.SEND_MESSAGES | cls.CONNECT | cls.SPEAK
