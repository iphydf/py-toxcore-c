import unittest

from pytox import common
from pytox.toxencryptsave import toxencryptsave as c


class ToxencryptsaveTest(unittest.TestCase):

    def test_encrypt_decrypt(self) -> None:
        with c.PassKey(b"hello") as pk:
            self.assertNotEqual(pk.encrypt(b"hello world"), b"hello world")
            self.assertEqual(pk.decrypt(pk.encrypt(b"hello world")),
                             b"hello world")

    def test_encrypt_decrypt_with_correct_salt(self) -> None:
        with c.PassKey(b"hello", b"a" * 32) as pk1:
            with c.PassKey(b"hello", b"a" * 32) as pk2:
                self.assertEqual(pk2.decrypt(pk1.encrypt(b"hello world")),
                                 b"hello world")

    def test_encrypt_decrypt_with_wrong_salt(self) -> None:
        with c.PassKey(passphrase=b"hello", salt=b"a" * 32) as pk1:
            with c.PassKey(b"hello", b"b" * 32) as pk2:
                with self.assertRaises(c.DecryptionError) as ex:
                    pk2.decrypt(pk1.encrypt(b"hello world"))
                self.assertEqual(ex.exception.code,
                                 c.DecryptionError.Code.FAILED)

    def test_salt_too_small(self) -> None:
        with self.assertRaises(common.LengthException):
            c.PassKey(b"hello", b"world")

    def test_pass_encrypt_decrypt(self) -> None:
        self.assertNotEqual(c.pass_encrypt(b"hello world", b"hunter2"),
                            b"hello world")
        self.assertEqual(
            c.pass_decrypt(c.pass_encrypt(b"hello world", b"hunter2"),
                           b"hunter2"),
            b"hello world",
        )
        # wrong password should raise c.DecryptionError
        with self.assertRaises(c.DecryptionError) as ex:
            c.pass_decrypt(c.pass_encrypt(b"hello world", b"hunter2"),
                           b"hunter3")
        self.assertEqual(ex.exception.code,
                         c.DecryptionError.Code.FAILED)

    def test_get_salt(self) -> None:
        salt = c.get_salt(c.pass_encrypt(b"hello world", b"hunter2"))
        self.assertEqual(len(salt), 32)
        with self.assertRaises(c.GetSaltError) as ex:
            c.get_salt(b"hello world" * 10)
        self.assertEqual(ex.exception.code,
                         c.GetSaltError.Code.BAD_FORMAT)
        with self.assertRaises(common.LengthException):
            c.get_salt(c.pass_encrypt(b"hello world", b"hunter2")[:79])

    def test_short_ciphertext_decrypt_fails_cleanly(self) -> None:
        with c.PassKey(b"hello") as pk:
            with self.assertRaises(c.DecryptionError) as ex:
                pk.decrypt(b"short")
            self.assertEqual(
                ex.exception.code,
                c.DecryptionError.Code.INVALID_LENGTH,
            )
        with self.assertRaises(c.DecryptionError) as ex2:
            c.pass_decrypt(b"short", b"hunter2")
        self.assertEqual(
            ex2.exception.code,
            c.DecryptionError.Code.INVALID_LENGTH,
        )

    def test_salt_wrong_length_rejected(self) -> None:
        with self.assertRaises(common.LengthException):
            c.PassKey(b"hello", b"a" * 33)


if __name__ == "__main__":
    unittest.main()
