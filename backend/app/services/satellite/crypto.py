"""Encryption utilities for satellite data."""
from cryptography.fernet import Fernet
import os


def encrypt_file(filepath: str, key_path: str = "fernet.key") -> bool:
    if not os.path.exists(key_path):
        key = Fernet.generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
    with open(key_path, "rb") as f:
        cipher = Fernet(f.read())
    with open(filepath, "rb") as f:
        encrypted = cipher.encrypt(f.read())
    with open(filepath + ".enc", "wb") as f:
        f.write(encrypted)
    return True
