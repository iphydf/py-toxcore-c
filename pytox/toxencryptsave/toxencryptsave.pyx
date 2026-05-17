# cython: language_level=3, linetrace=True
from array import array
from pytox import common
from types import TracebackType
from typing import Optional
from typing import TypeVar
T = TypeVar("T")


class ApiException(common.ApiException):
    pass


cdef class Tox_Pass_Key_Ptr:
    cdef Tox_Pass_Key* _get(self) except *:
        if self._ptr is NULL:
            raise common.UseAfterFreeException()
        return self._ptr

    def __del__(self) -> None:
        self.__exit__(None, None, None)

    def __enter__(self: T) -> T:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: TracebackType | None) -> None:
        tox_pass_key_free(self._ptr)
        self._ptr = NULL

    cdef Tox_Pass_Key* _derive(self, bytes passphrase):
        cdef Tox_Err_Key_Derivation error = TOX_ERR_KEY_DERIVATION_OK
        cdef Tox_Pass_Key* ptr = tox_pass_key_derive(passphrase, len(passphrase), &error)
        if error:
            raise ApiException(Tox_Err_Key_Derivation(error))
        return ptr

    cdef Tox_Pass_Key* _derive_with_salt(self, bytes passphrase, bytes salt):
        common.check_len("salt", salt, tox_pass_salt_length())
        cdef Tox_Err_Key_Derivation error = TOX_ERR_KEY_DERIVATION_OK
        cdef Tox_Pass_Key* ptr = tox_pass_key_derive_with_salt(passphrase, len(passphrase), salt, &error)
        if error:
            raise ApiException(Tox_Err_Key_Derivation(error))
        return ptr

    def __init__(self, passphrase: bytes, salt: Optional[bytes] = None) -> None:
        """Create new Tox_Pass_Key object."""
        if salt is not None:
            self._ptr = self._derive_with_salt(passphrase, salt)
        if salt is None:
            self._ptr = self._derive(passphrase)

    def encrypt(self, plaintext: bytes) -> bytes:
        cdef Tox_Err_Encryption err = TOX_ERR_ENCRYPTION_OK
        cdef size_t size = len(plaintext) + tox_pass_encryption_extra_length()
        cdef uint8_t* buf = <uint8_t*> malloc(size * sizeof(uint8_t))
        try:
            tox_pass_key_encrypt(self._get(), plaintext, len(plaintext), buf, &err)
            if err:
                raise ApiException(Tox_Err_Encryption(err))
            return buf[:size]
        finally:
            free(buf)

    def decrypt(self, ciphertext: bytes) -> bytes:
        cdef Tox_Err_Decryption err = TOX_ERR_DECRYPTION_OK
        cdef size_t size = len(ciphertext) - tox_pass_encryption_extra_length()
        cdef uint8_t* buf = <uint8_t*> malloc(size * sizeof(uint8_t))
        try:
            tox_pass_key_decrypt(self._get(), ciphertext, len(ciphertext), buf, &err)
            if err:
                raise ApiException(Tox_Err_Decryption(err))
            return buf[:size]
        finally:
            free(buf)
PASS_SALT_LENGTH: int = tox_pass_salt_length()
PASS_KEY_LENGTH: int = tox_pass_key_length()
PASS_ENCRYPTION_EXTRA_LENGTH: int = tox_pass_encryption_extra_length()


def pass_encrypt(plaintext: bytes, passphrase: bytes) -> bytes:
    cdef Tox_Err_Encryption err = TOX_ERR_ENCRYPTION_OK
    cdef size_t size = len(plaintext) + tox_pass_encryption_extra_length()
    cdef uint8_t* buf = <uint8_t*> malloc(size * sizeof(uint8_t))
    try:
        tox_pass_encrypt(plaintext, len(plaintext), passphrase, len(passphrase), buf, &err)
        if err:
            raise ApiException(Tox_Err_Encryption(err))
        return buf[:size]
    finally:
        free(buf)


def pass_decrypt(ciphertext: bytes, passphrase: bytes) -> bytes:
    cdef Tox_Err_Decryption err = TOX_ERR_DECRYPTION_OK
    cdef size_t size = len(ciphertext) - tox_pass_encryption_extra_length()
    cdef uint8_t* buf = <uint8_t*> malloc(size * sizeof(uint8_t))
    try:
        tox_pass_decrypt(ciphertext, len(ciphertext), passphrase, len(passphrase), buf, &err)
        if err:
            raise ApiException(Tox_Err_Decryption(err))
        return buf[:size]
    finally:
        free(buf)


def get_salt(ciphertext: bytes) -> bytes:
    common.check_len("ciphertext", ciphertext, tox_pass_encryption_extra_length())
    cdef Tox_Err_Get_Salt err = TOX_ERR_GET_SALT_OK
    cdef size_t size = tox_pass_salt_length()
    cdef uint8_t* buf = <uint8_t*> malloc(size * sizeof(uint8_t))
    try:
        tox_get_salt(ciphertext, buf, &err)
        if err:
            raise ApiException(Tox_Err_Get_Salt(err))
        return buf[:size]
    finally:
        free(buf)


def is_data_encrypted(data: bytes) -> bool:
    common.check_len("data", data, tox_pass_encryption_extra_length())
    return tox_is_data_encrypted(data)
