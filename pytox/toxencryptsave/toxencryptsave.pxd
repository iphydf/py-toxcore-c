# cython: language_level=3, linetrace=True
from libcpp cimport bool
from libc.stdint cimport uint8_t, uint16_t, uint32_t, uint64_t, int16_t, int32_t, int64_t
from libc.stdlib cimport malloc, free
from typing import Optional


cdef extern from "tox/toxencryptsave.h":
    ctypedef enum Tox_Err_Decryption:
        TOX_ERR_DECRYPTION_OK
        TOX_ERR_DECRYPTION_NULL
        TOX_ERR_DECRYPTION_INVALID_LENGTH
        TOX_ERR_DECRYPTION_BAD_FORMAT
        TOX_ERR_DECRYPTION_KEY_DERIVATION_FAILED
        TOX_ERR_DECRYPTION_FAILED
    ctypedef enum Tox_Err_Encryption:
        TOX_ERR_ENCRYPTION_OK
        TOX_ERR_ENCRYPTION_NULL
        TOX_ERR_ENCRYPTION_KEY_DERIVATION_FAILED
        TOX_ERR_ENCRYPTION_FAILED
    ctypedef enum Tox_Err_Get_Salt:
        TOX_ERR_GET_SALT_OK
        TOX_ERR_GET_SALT_NULL
        TOX_ERR_GET_SALT_BAD_FORMAT
    ctypedef enum Tox_Err_Key_Derivation:
        TOX_ERR_KEY_DERIVATION_OK
        TOX_ERR_KEY_DERIVATION_NULL
        TOX_ERR_KEY_DERIVATION_FAILED
    ctypedef struct Tox_Pass_Key
    cdef uint32_t tox_pass_salt_length() noexcept nogil
    cdef uint32_t tox_pass_key_length() noexcept nogil
    cdef uint32_t tox_pass_encryption_extra_length() noexcept nogil
    cdef bool tox_pass_encrypt(const uint8_t* plaintext, size_t plaintext_len, const uint8_t* passphrase, size_t passphrase_len, uint8_t* ciphertext, Tox_Err_Encryption* error) noexcept nogil
    cdef bool tox_pass_decrypt(const uint8_t* ciphertext, size_t ciphertext_len, const uint8_t* passphrase, size_t passphrase_len, uint8_t* plaintext, Tox_Err_Decryption* error) noexcept nogil
    cdef void tox_pass_key_free(Tox_Pass_Key* self) noexcept nogil
    cdef Tox_Pass_Key* tox_pass_key_derive(const uint8_t* passphrase, size_t passphrase_len, Tox_Err_Key_Derivation* error) noexcept nogil
    cdef Tox_Pass_Key* tox_pass_key_derive_with_salt(const uint8_t* passphrase, size_t passphrase_len, const uint8_t* salt, Tox_Err_Key_Derivation* error) noexcept nogil
    cdef bool tox_pass_key_encrypt(const Tox_Pass_Key* self, const uint8_t* plaintext, size_t plaintext_len, uint8_t* ciphertext, Tox_Err_Encryption* error) noexcept nogil
    cdef bool tox_pass_key_decrypt(const Tox_Pass_Key* self, const uint8_t* ciphertext, size_t ciphertext_len, uint8_t* plaintext, Tox_Err_Decryption* error) noexcept nogil
    cdef bool tox_get_salt(const uint8_t* ciphertext, uint8_t* salt, Tox_Err_Get_Salt* error) noexcept nogil
    cdef bool tox_is_data_encrypted(const uint8_t* data) noexcept nogil


cdef class PassKey:
    cdef Tox_Pass_Key* _ptr
    cdef Tox_Pass_Key* _get(self) except *
    cdef void _close(self) except *
    cdef Tox_Pass_Key* _derive(self, bytes passphrase)
    cdef Tox_Pass_Key* _derive_with_salt(self, bytes passphrase, bytes salt)
