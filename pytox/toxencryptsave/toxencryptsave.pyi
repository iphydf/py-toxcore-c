from pytox import common
from types import TracebackType
from typing import Optional
from typing import Self
import enum

class DecryptionError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        INVALID_LENGTH = 2
        BAD_FORMAT = 3
        KEY_DERIVATION_FAILED = 4
        FAILED = 5
    code: DecryptionError.Code

class EncryptionError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        KEY_DERIVATION_FAILED = 2
        FAILED = 3
    code: EncryptionError.Code

class GetSaltError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        BAD_FORMAT = 2
    code: GetSaltError.Code

class KeyDerivationError(ApiException):
    class Code(enum.IntEnum):
        NULL = 1
        FAILED = 2
    code: KeyDerivationError.Code

class ApiException(common.ApiException): ...

class PassKey:
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None: ...
    def __init__(self, passphrase: bytes, salt: Optional[bytes] = ...) -> None: ...
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...
PASS_SALT_LENGTH: int
PASS_KEY_LENGTH: int
PASS_ENCRYPTION_EXTRA_LENGTH: int

def pass_encrypt(plaintext: bytes, passphrase: bytes) -> bytes: ...

def pass_decrypt(ciphertext: bytes, passphrase: bytes) -> bytes: ...

def get_salt(ciphertext: bytes) -> bytes: ...

def is_data_encrypted(data: bytes) -> bool: ...
