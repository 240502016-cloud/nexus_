from __future__ import annotations

import os
from pathlib import Path

import yaml


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_config() -> dict:
    server_name = required("SYNAPSE_SERVER_NAME")
    config_dir = Path(os.environ.get("SYNAPSE_CONFIG_DIR", "/data"))
    data_dir = Path(os.environ.get("SYNAPSE_DATA_DIR", "/data"))

    return {
        "server_name": server_name,
        "public_baseurl": required("NEXUS_PUBLIC_BASEURL"),
        "pid_file": str(data_dir / "homeserver.pid"),
        "listeners": [
            {
                "port": 8008,
                "type": "http",
                "tls": False,
                "x_forwarded": True,
                "bind_addresses": ["0.0.0.0"],
                "resources": [{"names": ["client", "federation"], "compress": False}],
            }
        ],
        "database": {
            "name": "psycopg2",
            "args": {
                "host": required("SYNAPSE_POSTGRES_HOST"),
                "port": int(os.environ.get("SYNAPSE_POSTGRES_PORT", "5432")),
                "user": required("SYNAPSE_POSTGRES_USER"),
                "password": required("SYNAPSE_POSTGRES_PASSWORD"),
                "database": required("SYNAPSE_POSTGRES_DB"),
                "cp_min": 5,
                "cp_max": 10,
            },
        },
        "log_config": str(config_dir / f"{server_name}.log.config"),
        "media_store_path": str(data_dir / "media_store"),
        "registration_shared_secret": required("MATRIX_REGISTRATION_SHARED_SECRET"),
        "macaroon_secret_key": required("MATRIX_MACAROON_SECRET_KEY"),
        "form_secret": required("MATRIX_FORM_SECRET"),
        "signing_key_path": str(config_dir / f"{server_name}.signing.key"),
        "report_stats": False,
        "enable_registration": False,
        "trusted_key_servers": [{"server_name": "matrix.org"}],
    }


def main() -> None:
    destination = Path(os.environ.get("SYNAPSE_CONFIG_PATH", "/data/homeserver.yaml"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        yaml.safe_dump(build_config(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    temporary.replace(destination)


if __name__ == "__main__":
    main()

