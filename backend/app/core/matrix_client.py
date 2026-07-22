from __future__ import annotations

import hashlib
import hmac
import uuid

import requests

from app.config import settings


class MatrixError(RuntimeError):
    pass


class MatrixClient:
    """Synapse'in Client-Server ve Admin API'lerine konuşan ince bir sarmalayıcı.

    Kullanıcı hesapları ve odalar, Core API tarafından bu client üzerinden arka
    planda yönetilir; kullanıcı Matrix'in varlığını hissetmez (bkz. ARCHITECTURE.md).
    """

    def __init__(self, base_url: str | None = None, shared_secret: str | None = None):
        self.base_url = (base_url or settings.matrix_homeserver_url).rstrip("/")
        self.shared_secret = shared_secret or settings.matrix_registration_shared_secret

    def _get_registration_nonce(self) -> str:
        response = requests.get(f"{self.base_url}/_synapse/admin/v1/register")
        response.raise_for_status()
        return response.json()["nonce"]

    def register_user(self, username: str, password: str, admin: bool = False) -> dict:
        """Shared-secret admin registration algoritmasıyla bir Matrix hesabı oluşturur.

        bkz. https://element-hq.github.io/synapse/latest/admin_api/register_api.html
        Döner: {"user_id", "access_token", "home_server", "device_id"}
        """
        nonce = self._get_registration_nonce()
        admin_flag = "admin" if admin else "notadmin"
        message = "\x00".join([nonce, username, password, admin_flag]).encode("utf-8")
        mac = hmac.new(self.shared_secret.encode("utf-8"), message, hashlib.sha1).hexdigest()

        response = requests.post(
            f"{self.base_url}/_synapse/admin/v1/register",
            json={
                "nonce": nonce,
                "username": username,
                "password": password,
                "admin": admin,
                "mac": mac,
            },
        )
        if not response.ok:
            raise MatrixError(f"Matrix kullanıcı kaydı başarısız: {response.status_code} {response.text}")
        return response.json()

    def create_room(self, access_token: str, name: str) -> str:
        """Verilen erişim token'ıyla özel bir oda oluşturur, room_id döner."""
        response = requests.post(
            f"{self.base_url}/_matrix/client/v3/createRoom",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"name": name, "preset": "private_chat"},
        )
        if not response.ok:
            raise MatrixError(f"Matrix oda oluşturma başarısız: {response.status_code} {response.text}")
        return response.json()["room_id"]

    def invite_user(self, access_token: str, room_id: str, matrix_user_id: str) -> None:
        """Odaya davet eder (odaya girebilmek için önce davet, sonra join gerekir)."""
        response = requests.post(
            f"{self.base_url}/_matrix/client/v3/rooms/{room_id}/invite",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"user_id": matrix_user_id},
        )
        if not response.ok:
            raise MatrixError(f"Kullanıcı odaya davet edilemedi: {response.status_code} {response.text}")

    def join_room(self, access_token: str, room_id: str) -> None:
        """Davet edilen kullanıcı, kendi token'ıyla odaya katılır."""
        response = requests.post(
            f"{self.base_url}/_matrix/client/v3/rooms/{room_id}/join",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if not response.ok:
            raise MatrixError(f"Odaya katılınamadı: {response.status_code} {response.text}")

    def send_message(self, access_token: str, room_id: str, content: str, txn_id: str | None = None) -> str:
        """Odaya metin mesajı gönderir, event_id döner.

        Worker retries can pass a stable transaction ID so Matrix de-duplicates a request that
        timed out after the homeserver accepted it.
        """
        txn_id = txn_id or uuid.uuid4().hex
        response = requests.put(
            f"{self.base_url}/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"msgtype": "m.text", "body": content},
        )
        if not response.ok:
            raise MatrixError(f"Mesaj gönderilemedi: {response.status_code} {response.text}")
        return response.json()["event_id"]

    def get_messages(self, access_token: str, room_id: str, limit: int = 50) -> list[dict]:
        """Odadaki en son mesajları (yeniden eskiye) döner."""
        response = requests.get(
            f"{self.base_url}/_matrix/client/v3/rooms/{room_id}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"dir": "b", "limit": limit},
        )
        if not response.ok:
            raise MatrixError(f"Mesajlar alınamadı: {response.status_code} {response.text}")
        events = response.json().get("chunk", [])
        return [
            {
                "event_id": event["event_id"],
                "sender": event["sender"],
                "content": event.get("content", {}).get("body", ""),
                "origin_server_ts": event["origin_server_ts"],
            }
            for event in events
            if event.get("type") == "m.room.message"
        ]

    def redact_message(self, access_token: str, room_id: str, event_id: str, reason: str | None = None) -> str:
        """Bir mesajı siler (redact). Kendi mesajını herkes silebilir; başkasının mesajını
        silmek odada yeterli power level (ör. oda sahibi/admin) gerektirir - Matrix bunu
        sunucu tarafında zaten uyguluyor, biz sadece isteği iletiyoruz."""
        txn_id = uuid.uuid4().hex
        body = {"reason": reason} if reason else {}
        response = requests.put(
            f"{self.base_url}/_matrix/client/v3/rooms/{room_id}/redact/{event_id}/{txn_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            json=body,
        )
        if not response.ok:
            raise MatrixError(f"Mesaj silinemedi: {response.status_code} {response.text}")
        return response.json()["event_id"]


matrix_client = MatrixClient()
