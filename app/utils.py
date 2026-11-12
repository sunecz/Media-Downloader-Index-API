import base64
import msgspec
from urllib.parse import quote, unquote


def encode_cursor(cursor: msgspec.Struct) -> str:
    return quote(base64.urlsafe_b64encode(msgspec.json.encode(cursor)).decode("utf-8"))


def decode_cursor[T](cursor: str, cursor_type: type[T]) -> T:
    """Raises ValueError or msgspec.DecodeError if malformed."""
    return msgspec.json.decode(
        base64.urlsafe_b64decode(unquote(cursor)),
        type=cursor_type,
    )
