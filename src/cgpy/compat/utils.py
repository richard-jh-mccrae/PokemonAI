"""``cg.utils`` twin: the same dict->dataclass conversion, byte-for-byte semantics.

Copied from ``src/cg/utils.py`` (the competition-provided shim) so aliased consumers get
identical behavior without loading the native package.
"""
import json


def to_dataclass(dic: dict, cls: type):
    """Convert a dictionary to a dataclass instance recursively (cg.utils semantics)."""
    if dic is None:
        return None

    field_types = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    d = {}

    for key, value in dic.items():
        if key in field_types:
            if isinstance(value, dict):
                c = field_types[key]
                if hasattr(c, "__args__"):
                    c = c.__args__[0]
                d[key] = to_dataclass(value, c)
            elif isinstance(value, list):
                c = field_types[key].__args__[0]
                if hasattr(c, "__args__"):
                    c = c.__args__[0]
                    if hasattr(c, "__args__"):
                        c = c.__args__[0]
                if not hasattr(c, "__dataclass_fields__"):
                    d[key] = value
                else:
                    d[key] = [to_dataclass(v, c) for v in value]
            else:
                d[key] = value

    return cls(**d)


def json_to_dataclass(bs: bytes, cls: type):
    """Convert a JSON byte string to a dataclass instance (cg.utils semantics)."""
    js = bs.decode()
    dic = json.loads(js)
    return to_dataclass(dic, cls)
