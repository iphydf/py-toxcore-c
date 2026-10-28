import enum
from typing import Sized


class PytoxException(Exception):
    pass


class ApiException(PytoxException):
    code: enum.Enum

    def __init__(self, err: enum.Enum):
        super().__init__(err.name)
        self.code = err


class LengthException(PytoxException):
    pass


class UseAfterFreeException(PytoxException):
    def __init__(self) -> None:
        super().__init__(
            "object used after it was killed/freed (or it was never initialised)"
        )


def check_len(name: str, data: Sized, expected_length: int) -> None:
    """Require ``data`` to have at least ``expected_length`` elements."""
    if len(data) < expected_length:
        raise LengthException(
            f"parameter '{name}' received {type(data).__name__} of invalid "
            f"length {len(data)}, expected at least {expected_length}"
        )


def check_exact_len(name: str, data: Sized, expected_length: int) -> None:
    """Require fixed-size keys/hashes/IDs to match ``expected_length`` exactly."""
    if len(data) != expected_length:
        raise LengthException(
            f"parameter '{name}' received {type(data).__name__} of invalid "
            f"length {len(data)}, expected {expected_length}"
        )


def encode_cstr(name: str, value: str) -> bytes:
    """Encode a Python ``str`` to UTF-8 for a C ``const char*`` parameter."""
    encoded = value.encode("utf-8")
    if b"\x00" in encoded:
        raise ValueError(f"parameter '{name}' must not contain NUL bytes")
    return encoded


def count_of(name: str, data: Sized, per: int) -> int:
    """How many groups of ``per`` elements ``data`` holds, all of them whole."""
    if per <= 0 or len(data) % per != 0:
        raise LengthException(
            f"parameter '{name}' received {type(data).__name__} of invalid "
            f"length {len(data)}, expected a multiple of {per}"
        )
    return len(data) // per
