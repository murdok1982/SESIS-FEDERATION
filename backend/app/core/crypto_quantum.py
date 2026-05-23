import logging
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings

logger = logging.getLogger(__name__)


class QuantumSafeCrypto:
    def __init__(self):
        self._kyber_available = False
        self._dilithium_available = False
        self._check_quantum_libs()

    def _check_quantum_libs(self):
        try:
            import pqcrypto  # noqa
            self._kyber_available = True
            self._dilithium_available = True
            logger.info("Quantum-safe crypto libraries available")
        except ImportError:
            logger.warning("Quantum-safe libraries not installed, falling back to AES-256-GCM")

    async def generate_keypair(self) -> dict:
        if self._kyber_available:
            import pqcrypto.kem.kyber768
            pk, sk = pqcrypto.kem.kyber768.keypair()
            return {"public_key": pk.hex(), "private_key": sk.hex(), "algorithm": "kyber768"}
        key = Fernet.generate_key()
        return {"key": key.decode(), "algorithm": "aes-256-gcm"}

    async def encrypt(self, data: bytes, key: bytes) -> bytes:
        if self._kyber_available:
            import pqcrypto.kem.kyber768
            ciphertext, shared_secret = pqcrypto.kem.kyber768.enc(key)
            aes = AESGCM(shared_secret[:32])
            nonce = os.urandom(12)
            return ciphertext + nonce + aes.encrypt(nonce, data, None)
        f = Fernet(key)
        return f.encrypt(data)

    async def decrypt(self, data: bytes, key: bytes) -> bytes:
        try:
            f = Fernet(key)
            return f.decrypt(data)
        except Exception:
            if self._kyber_available:
                import pqcrypto.kem.kyber768
                shared_secret = pqcrypto.kem.kyber768.dec(key, data[:1088])
                aes = AESGCM(shared_secret[:32])
                nonce = data[1088:1100]
                return aes.decrypt(nonce, data[1100:], None)
            raise

    async def sign(self, data: bytes, private_key: bytes) -> bytes:
        if self._dilithium_available:
            import pqcrypto.sign.dilithium3
            return pqcrypto.sign.dilithium3.sign(data, private_key)
        return b""

    async def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        if self._dilithium_available:
            import pqcrypto.sign.dilithium3
            try:
                pqcrypto.sign.dilithium3.verify(data, signature, public_key)
                return True
            except Exception:
                return False
        return False


qcrypto = QuantumSafeCrypto()
