from pathlib import Path

import yaml

_CLIENTS_FILE = Path(__file__).parent / "clients.yaml"


def _load_clients() -> dict:
    data = yaml.safe_load(_CLIENTS_FILE.read_text()) or {}
    return data.get("clients", {})


def get_client(client_id: str) -> dict | None:
    return _load_clients().get(client_id)


def redirect_uri_is_registered(client_id: str, redirect_uri: str) -> bool:
    client = get_client(client_id)
    if not client:
        return False
    return redirect_uri in client.get("redirect_uris", [])


def verify_client_secret(client_id: str, client_secret: str) -> bool:
    client = get_client(client_id)
    if not client:
        return False
    return client.get("client_secret") == client_secret
