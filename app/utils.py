import base64
import msgspec
from urllib.parse import quote, unquote


def encode_cursor(cursor: dict) -> str:
    return quote(base64.urlsafe_b64encode(msgspec.json.encode(cursor)).decode("utf-8"))


def decode_cursor(cursor: str) -> dict:
    return msgspec.json.decode(base64.urlsafe_b64decode(unquote(cursor)))
