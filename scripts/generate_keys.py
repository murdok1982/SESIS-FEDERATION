from cryptography.fernet import Fernet
key = Fernet.generate_key()
with open("fernet.key", "wb") as f:
    f.write(key)
print(f"Fernet key generated: {key.decode()}")
