import hashlib
import secrets
from typing import Dict

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

def gen(fp: str) -> tuple[str, str]:
    helper = h("helper", fp)
    secret = h("theta", fp)
    return helper, secret

def rep(fp_star: str, helper: str) -> str:
    return h("theta", fp_star, helper)

# ECC point simulation (use hash as deterministic stand-in)
def ecc_point_mult(scalar: str, point: str) -> str:
    return h("ecc_mult", scalar, point)

def ecc_pubkey(secret: str) -> str:
    return h("ecc_pub", secret)

# Simulated ECC-based encryption (for demo, just hash)
def ecc_encrypt(pubkey: str, plaintext: str) -> str:
    return h("ecc_enc", pubkey, plaintext)

def ecc_decrypt(secret: str, ciphertext: str) -> str:
    return h("ecc_dec", secret, ciphertext)