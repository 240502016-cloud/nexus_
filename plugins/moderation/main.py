from app.core.matrix_client import MatrixError, matrix_client
from app.core.models import Server
from app.database import SessionLocal


def handle_command(context):
    """plugin.json'daki entry_point ('main:handle_command') tarafından çağrılır.

    "/sil <event_id>" - sadece sunucu sahibi kullanabilir. Silme, sahibin kendi Matrix
    hesabıyla yapılır; oda sahibi olduğu için Matrix'te yeterli yetkiye zaten sahiptir.
    """
    event_id = (context.args or "").strip()
    if not event_id:
        return "Kullanım: /sil <mesaj_event_id>"
    if not context.server_id or not context.matrix_room_id:
        return "Bu komut bir sunucu kanalında çalıştırılmalı"

    db = SessionLocal()
    try:
        server = db.get(Server, context.server_id)
        if not server:
            return "Sunucu bulunamadı"
        if server.owner_id != context.user_id:
            return "Bu komutu sadece sunucu sahibi kullanabilir"

        owner = server.owner
        if not owner.matrix_access_token:
            return "Sunucu sahibinin Matrix hesabı yok"

        try:
            matrix_client.redact_message(
                owner.matrix_access_token, context.matrix_room_id, event_id, reason="moderasyon"
            )
        except MatrixError as exc:
            return f"Mesaj silinemedi: {exc}"

        return f"Mesaj silindi (event_id={event_id})"
    finally:
        db.close()
