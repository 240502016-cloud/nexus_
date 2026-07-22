"""Minecraft Server List Ping (SLP) protokolünün ham socket implementasyonu.

Üçüncü parti bir kütüphane veya API kullanmaz; Minecraft'ın "status" el sıkışmasını
(handshake + status request + JSON response) doğrudan TCP soketi üzerinden konuşur.
Protokol: https://minecraft.wiki/w/Java_Edition_protocol/Server_List_Ping
"""

import json
import socket
import struct


def _write_varint(value: int) -> bytes:
    data = b""
    value &= 0xFFFFFFFF
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            data += struct.pack("B", byte | 0x80)
        else:
            data += struct.pack("B", byte)
            return data


def _read_varint(sock: socket.socket) -> int:
    value = 0
    position = 0
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise ConnectionError("bağlantı beklenmedik şekilde kapandı")
        current = chunk[0]
        value |= (current & 0x7F) << position
        if not (current & 0x80):
            return value
        position += 7


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buffer = b""
    while len(buffer) < size:
        chunk = sock.recv(size - len(buffer))
        if not chunk:
            raise ConnectionError("bağlantı beklenmedik şekilde kapandı")
        buffer += chunk
    return buffer


def query_minecraft_server(host: str, port: int, timeout: float = 5.0) -> dict:
    """Sunucuya bağlanır, status handshake yapar, sunucunun döndürdüğü JSON'ı döner."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        host_bytes = host.encode("utf-8")
        handshake = (
            _write_varint(0x00)
            + _write_varint(-1)  # protocol version: herhangi biri kabul edilir
            + _write_varint(len(host_bytes))
            + host_bytes
            + struct.pack(">H", port)
            + _write_varint(1)  # next state: 1 = status
        )
        sock.sendall(_write_varint(len(handshake)) + handshake)

        status_request = _write_varint(0x00)  # boş status request paketi
        sock.sendall(_write_varint(len(status_request)) + status_request)

        _packet_length = _read_varint(sock)
        _packet_id = _read_varint(sock)
        json_length = _read_varint(sock)
        payload = _recv_exact(sock, json_length)
        return json.loads(payload.decode("utf-8"))


def handle_command(context):
    """plugin.json'daki entry_point ('main:handle_command') tarafından çağrılır."""
    target = (context.args or "").strip()
    if not target:
        return "Kullanım: /oyun-durumu <host[:port]> (örn: play.example.com:25565)"

    host, _, port_text = target.partition(":")
    try:
        port = int(port_text) if port_text else 25565
    except ValueError:
        return f"Geçersiz port: {port_text!r}"

    try:
        info = query_minecraft_server(host, port)
    except Exception as exc:
        return f"{target} -> erişilemiyor ({exc})"

    version = info.get("version", {}).get("name", "?")
    players = info.get("players", {})
    online = players.get("online", "?")
    max_players = players.get("max", "?")
    return f"{target} -> Online! Sürüm: {version}, Oyuncular: {online}/{max_players}"
