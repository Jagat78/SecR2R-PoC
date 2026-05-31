from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64
# ECC Point Multiplication (ECDH shared secret)
def derive_session_key(shared_secret: bytes, salt: bytes = b"secr2r", info: bytes = b"session key") -> bytes:
    """
    Derive a 256-bit session key from the ECDH shared secret using HKDF-SHA256.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    )
    return hkdf.derive(shared_secret)

# AES-GCM encryption using the session key
def aesgcm_encrypt(key: bytes, plaintext: bytes, associated_data: bytes = None) -> str:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext, associated_data)
    # Return base64(nonce + ciphertext)
    return base64.b64encode(nonce + ct).decode()

# AES-GCM decryption using the session key
def aesgcm_decrypt(key: bytes, b64_ciphertext: str, associated_data: bytes = None) -> bytes:
    data = base64.b64decode(b64_ciphertext)
    nonce = data[:12]
    ct = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, associated_data)
import hashlib
import secrets
from typing import Dict, Tuple
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.concatkdf import ConcatKDFHash
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

def h(*parts: str) -> str:
    material = "||".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()

def fresh_nonce(nbytes: int = 16) -> str:
    return secrets.token_hex(nbytes)

def now_ts() -> int:
    import time
    return int(time.time())

def xor_hex(a: str, b: str) -> str:
    # XOR two hex strings of equal length
    return hex(int(a, 16) ^ int(b, 16))[2:].zfill(len(a))

def fake_puf(attributes: Dict[str, str]) -> str:
    items = [f"{k}={v}" for k, v in sorted(attributes.items())]
    return h(*items)

def gen(fp: str) -> Tuple[str, str]:
    helper = h("helper", fp)
    secret = h("theta", fp)
    return helper, secret

def rep(fp_star: str, helper: str) -> str:
    return h("theta", fp_star, helper)

# ECC Key Generation
def generate_ecc_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key

# ECC Point Multiplication (ECDH shared secret)
def ecc_point_mult(private_key, peer_public_key):
    shared_key = private_key.exchange(ec.ECDH(), peer_public_key)
    return shared_key

# ECC Public Key Serialization
def serialize_pubkey(pubkey) -> bytes:
    return pubkey.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

def deserialize_pubkey(pubkey_bytes: bytes):
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pubkey_bytes)

# ECC-based Encryption (ECIES-like)
def ecc_encrypt(pubkey, plaintext: bytes) -> bytes:
    ephemeral_private, ephemeral_public = generate_ecc_keypair()
    shared_key = ephemeral_private.exchange(ec.ECDH(), pubkey)
    kdf = ConcatKDFHash(algorithm=hashes.SHA256(), length=32, otherinfo=None)
    aes_key = kdf.derive(shared_key)
    aesgcm = AESGCM(aes_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return serialize_pubkey(ephemeral_public) + nonce + ciphertext

def ecc_decrypt(private_key, data: bytes) -> bytes:
    ephemeral_public_bytes = data[:65]
    nonce = data[65:77]
    ciphertext = data[77:]
    ephemeral_public = deserialize_pubkey(ephemeral_public_bytes)
    shared_key = private_key.exchange(ec.ECDH(), ephemeral_public)
    kdf = ConcatKDFHash(algorithm=hashes.SHA256(), length=32, otherinfo=None)
    aes_key = kdf.derive(shared_key)
    aesgcm = AESGCM(aes_key)
    return aesgcm.decrypt(nonce, ciphertext, None)