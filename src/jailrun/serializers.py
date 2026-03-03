from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import orjson


def orjson_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)

    raise TypeError(f"Type {type(obj)} is not serializable")


def dumps(obj: Any) -> str:
    return orjson.dumps(obj, default=orjson_default).decode()


def loads(obj: Any) -> Any:
    return orjson.loads(obj) if obj else {}
