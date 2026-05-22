"""
AES-256-GCM Cipher - Cifrado autenticado para datos sensibles militares.
Cumple estándares: AES-256-GCM, IV 12 bytes, sin padding.
"""
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import os
import json
from typing import Dict, Any, Optional


class AESCipher:
    """Cifrado AES-256-GCM con gestión de claves."""

    def __init__(self, key: bytes):
        """Inicializa con clave de 32 bytes (256 bits)."""
        if len(key) not in [16, 24, 32]:
            raise ValueError("Clave AES debe ser 16, 24 o 32 bytes")
        self.key = key

    @classmethod
    def from_hex(cls, hex_key: str) -> "AESCipher":
        """Crea instancia desde clave hexadecimal (64 chars = 32 bytes)."""
        return cls(bytes.fromhex(hex_key))

    def encrypt(self, data: Dict[str, Any]) -> str:
        """
        Cifra diccionario JSON.
        Retorna: JSON string con [iv_hex, ciphertext_hex, tag_hex]
        """
        iv = os.urandom(12)  # GCM recomienda 12 bytes IV
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        # Retornar IV + ciphertext + tag
        return json.dumps([
            iv.hex(),
            ciphertext.hex(),
            encryptor.tag.hex()
        ])

    def decrypt(self, encrypted: str) -> Dict[str, Any]:
        """
        Descifra datos cifrados con encrypt().
        Formato esperado: JSON string con [iv_hex, ciphertext_hex, tag_hex]
        """
        try:
            iv_hex, ct_hex, tag_hex = json.loads(encrypted)
            iv = bytes.fromhex(iv_hex)
            ciphertext = bytes.fromhex(ct_hex)
            tag = bytes.fromhex(tag_hex)

            cipher = Cipher(
                algorithms.AES(self.key),
                modes.GCM(iv, tag),
                backend=default_backend()
            )
            decryptor = cipher.decryptor()
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            return json.loads(plaintext.decode("utf-8"))
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            raise ValueError(f"Error descifrando: {e}")

    def encrypt_bytes(self, data: bytes) -> tuple[bytes, bytes, bytes]:
        """Cifra bytes crudos. Retorna (iv, ciphertext, tag)."""
        iv = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data) + encryptor.finalize()
        return iv, ciphertext, encryptor.tag

    def decrypt_bytes(self, iv: bytes, ciphertext: bytes, tag: bytes) -> bytes:
        """Descifra bytes crudos."""
        cipher = Cipher(
            algorithms.AES(self.key),
            modes.GCM(iv, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()


def generate_aes_key() -> bytes:
    """Genera clave AES-256 aleatoria (32 bytes)."""
    return os.urandom(32)


def generate_aes_key_hex() -> str:
    """Genera clave AES-256 en hexadecimal (64 chars)."""
    return generate_aes_key().hex()
