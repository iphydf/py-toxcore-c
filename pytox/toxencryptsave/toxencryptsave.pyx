# cython: language_level=3, linetrace=True
from enum import IntEnum
from pytox import common
from types import TracebackType
from typing import Optional
from typing import TypeVar
T = TypeVar("T")


class ApiException(common.ApiException):
    pass

class DecryptionError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_DECRYPTION_NULL),
        ("INVALID_LENGTH", TOX_ERR_DECRYPTION_INVALID_LENGTH),
        ("BAD_FORMAT", TOX_ERR_DECRYPTION_BAD_FORMAT),
        ("KEY_DERIVATION_FAILED", TOX_ERR_DECRYPTION_KEY_DERIVATION_FAILED),
        ("FAILED", TOX_ERR_DECRYPTION_FAILED),
    ], module=__name__, qualname="DecryptionError.Code")

class EncryptionError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_ENCRYPTION_NULL),
        ("KEY_DERIVATION_FAILED", TOX_ERR_ENCRYPTION_KEY_DERIVATION_FAILED),
        ("FAILED", TOX_ERR_ENCRYPTION_FAILED),
    ], module=__name__, qualname="EncryptionError.Code")

class GetSaltError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_GET_SALT_NULL),
        ("BAD_FORMAT", TOX_ERR_GET_SALT_BAD_FORMAT),
    ], module=__name__, qualname="GetSaltError.Code")

class KeyDerivationError(ApiException):
    Code = IntEnum("Code", [
        ("NULL", TOX_ERR_KEY_DERIVATION_NULL),
        ("FAILED", TOX_ERR_KEY_DERIVATION_FAILED),
    ], module=__name__, qualname="KeyDerivationError.Code")


cdef class PassKey:
    cdef Tox_Pass_Key* _get(self) except *:
        if self._ptr is NULL:
            raise common.UseAfterFreeException()
        return self._ptr

    cdef void _close(self) except *:
        cdef Tox_Pass_Key* ptr = self._ptr
        self._ptr = NULL
        if ptr is not NULL:
            tox_pass_key_free(ptr)

    def __dealloc__(self) -> None:
        self._close()

    def __enter__(self: T) -> T:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None:
        self._close()

    cdef Tox_Pass_Key* _derive(self, bytes passphrase):
        cdef const uint8_t* passphrase_ptr = passphrase
        cdef size_t passphrase_len = len(passphrase)
        cdef Tox_Err_Key_Derivation error = TOX_ERR_KEY_DERIVATION_OK
        cdef Tox_Pass_Key* ptr
        with nogil:
            ptr = tox_pass_key_derive(passphrase_ptr, passphrase_len, &error)
        if error:
            raise KeyDerivationError(KeyDerivationError.Code(error))
        return ptr

    cdef Tox_Pass_Key* _derive_with_salt(self, bytes passphrase, bytes salt):
        common.check_exact_len("salt", salt, tox_pass_salt_length())
        cdef const uint8_t* passphrase_ptr = passphrase
        cdef size_t passphrase_len = len(passphrase)
        cdef const uint8_t* salt_ptr = salt
        cdef Tox_Err_Key_Derivation error = TOX_ERR_KEY_DERIVATION_OK
        cdef Tox_Pass_Key* ptr
        with nogil:
            ptr = tox_pass_key_derive_with_salt(passphrase_ptr, passphrase_len, salt_ptr, &error)
        if error:
            raise KeyDerivationError(KeyDerivationError.Code(error))
        return ptr

    def __init__(self, passphrase: bytes, salt: Optional[bytes] = None) -> None:
        if self._ptr is not NULL:
            raise RuntimeError("PassKey can't be initialised twice")
        if salt is not None:
            self._ptr = self._derive_with_salt(passphrase, salt)
        else:
            self._ptr = self._derive(passphrase)

    def encrypt(self, plaintext: bytes) -> bytes:
        cdef Tox_Err_Encryption err = TOX_ERR_ENCRYPTION_OK
        cdef size_t size = len(plaintext) + tox_pass_encryption_extra_length()
        cdef uint8_t* buf = <uint8_t*> malloc(max(size, 1) * sizeof(uint8_t))
        if buf is NULL:
            raise MemoryError()
        try:
            tox_pass_key_encrypt(self._get(), plaintext, len(plaintext), buf, &err)
            if err:
                raise EncryptionError(EncryptionError.Code(err))
            return buf[:size]
        finally:
            free(buf)

    def decrypt(self, ciphertext: bytes) -> bytes:
        cdef Tox_Err_Decryption err = TOX_ERR_DECRYPTION_OK
        cdef size_t size = max(0, len(ciphertext) - <Py_ssize_t> tox_pass_encryption_extra_length())
        cdef uint8_t* buf = <uint8_t*> malloc(max(size, 1) * sizeof(uint8_t))
        if buf is NULL:
            raise MemoryError()
        try:
            tox_pass_key_decrypt(self._get(), ciphertext, len(ciphertext), buf, &err)
            if err:
                raise DecryptionError(DecryptionError.Code(err))
            return buf[:size]
        finally:
            free(buf)
PASS_SALT_LENGTH: int = tox_pass_salt_length()
PASS_KEY_LENGTH: int = tox_pass_key_length()
PASS_ENCRYPTION_EXTRA_LENGTH: int = tox_pass_encryption_extra_length()


def pass_encrypt(plaintext: bytes, passphrase: bytes) -> bytes:
    cdef const uint8_t* plaintext_ptr = plaintext
    cdef size_t plaintext_len = len(plaintext)
    cdef const uint8_t* passphrase_ptr = passphrase
    cdef size_t passphrase_len = len(passphrase)
    cdef Tox_Err_Encryption err = TOX_ERR_ENCRYPTION_OK
    cdef size_t size = len(plaintext) + tox_pass_encryption_extra_length()
    cdef uint8_t* buf = <uint8_t*> malloc(max(size, 1) * sizeof(uint8_t))
    if buf is NULL:
        raise MemoryError()
    try:
        with nogil:
            tox_pass_encrypt(plaintext_ptr, plaintext_len, passphrase_ptr, passphrase_len, buf, &err)
        if err:
            raise EncryptionError(EncryptionError.Code(err))
        return buf[:size]
    finally:
        free(buf)


def pass_decrypt(ciphertext: bytes, passphrase: bytes) -> bytes:
    cdef const uint8_t* ciphertext_ptr = ciphertext
    cdef size_t ciphertext_len = len(ciphertext)
    cdef const uint8_t* passphrase_ptr = passphrase
    cdef size_t passphrase_len = len(passphrase)
    cdef Tox_Err_Decryption err = TOX_ERR_DECRYPTION_OK
    cdef size_t size = max(0, len(ciphertext) - <Py_ssize_t> tox_pass_encryption_extra_length())
    cdef uint8_t* buf = <uint8_t*> malloc(max(size, 1) * sizeof(uint8_t))
    if buf is NULL:
        raise MemoryError()
    try:
        with nogil:
            tox_pass_decrypt(ciphertext_ptr, ciphertext_len, passphrase_ptr, passphrase_len, buf, &err)
        if err:
            raise DecryptionError(DecryptionError.Code(err))
        return buf[:size]
    finally:
        free(buf)


def get_salt(ciphertext: bytes) -> bytes:
    common.check_len("ciphertext", ciphertext, tox_pass_encryption_extra_length())
    cdef const uint8_t* ciphertext_ptr = ciphertext
    cdef Tox_Err_Get_Salt err = TOX_ERR_GET_SALT_OK
    cdef size_t size = tox_pass_salt_length()
    cdef uint8_t* buf = <uint8_t*> malloc(max(size, 1) * sizeof(uint8_t))
    if buf is NULL:
        raise MemoryError()
    try:
        with nogil:
            tox_get_salt(ciphertext_ptr, buf, &err)
        if err:
            raise GetSaltError(GetSaltError.Code(err))
        return buf[:size]
    finally:
        free(buf)


def is_data_encrypted(data: bytes) -> bool:
    common.check_len("data", data, tox_pass_encryption_extra_length())
    cdef const uint8_t* data_ptr = data
    cdef bool res
    with nogil:
        res = tox_is_data_encrypted(data_ptr)
    return res
