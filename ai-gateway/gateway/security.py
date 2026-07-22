from __future__ import annotations

import hmac
from ipaddress import IPv4Address, IPv6Address, ip_address

from fastapi import Request

from gateway.config import Network, Settings

Address = IPv4Address | IPv6Address


def address_in_networks(address: Address, networks: tuple[Network, ...]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def resolve_client_ip(request: Request, trusted_proxies: tuple[Network, ...]) -> Address | None:
    """Resolve the caller without blindly trusting spoofable forwarding headers.

    X-Forwarded-For is honored only when the direct peer is in TRUSTED_PROXIES.
    The first value is the original client according to the proxy convention.
    """
    if request.client is None:
        return None
    try:
        direct_peer = ip_address(request.client.host)
    except ValueError:
        return None

    if address_in_networks(direct_peer, trusted_proxies):
        forwarded_for = request.headers.get("x-forwarded-for", "")
        first_hop = forwarded_for.split(",", 1)[0].strip()
        if first_hop:
            try:
                return ip_address(first_hop)
            except ValueError:
                return None
    return direct_peer


def extract_api_key(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() == "bearer" and credential.strip():
        return credential.strip()

    api_key = request.headers.get("x-api-key")
    return api_key.strip() if api_key and api_key.strip() else None


def api_key_is_valid(candidate: str | None, settings: Settings) -> bool:
    if candidate is None:
        return False
    expected = settings.ai_gateway_api_key.get_secret_value()
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))

