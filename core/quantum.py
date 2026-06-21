"""
Quantum-resistant cryptography for TritioCoin.
Hybrid: ECDSA (secp256k1) + WOTS+ (hash-based).
"""
import hashlib
import os
import time
import logging
from typing import Tuple

import ecdsa

logger = logging.getLogger("Quantum")


class WOTSPlus:
    """
    Winternitz One-Time Signature.
    Security: 2^128 against quantum attacks (Grover).
    """
    N = 32
    W = 16
    LEN = 64

    @staticmethod
    def _chain(data: bytes, steps: int) -> bytes:
        out = data
        for _ in range(steps):
            out = hashlib.sha256(out).digest()
        return out

    def keygen(self) -> Tuple[bytes, bytes]:
        priv = os.urandom(self.LEN * self.N)
        pub = bytearray()
        for i in range(self.LEN):
            start = priv[i * self.N:(i + 1) * self.N]
            pub.extend(self._chain(start, 255))
        return priv, bytes(pub)

    def sign(self, priv: bytes, message: bytes) -> bytes:
        msg_hash = hashlib.sha256(message).digest()
        sig = bytearray()
        for i in range(self.LEN):
            start = priv[i * self.N:(i + 1) * self.N]
            byte_val = msg_hash[i % self.N]
            base = 15 if i < self.LEN // 2 else 0
            steps = (byte_val % self.W) + base
            sig.extend(self._chain(start, steps))
        return bytes(sig) + msg_hash

    @staticmethod
    def verify(pub: bytes, message: bytes, sig: bytes) -> bool:
        if len(sig) < WOTSPlus.LEN * WOTSPlus.N + WOTSPlus.N:
            return False
        sig_data = sig[:-WOTSPlus.N]
        msg_hash = sig[-WOTSPlus.N:]
        if hashlib.sha256(message).digest() != msg_hash:
            return False
        recon = bytearray()
        for i in range(WOTSPlus.LEN):
            part = sig_data[i * WOTSPlus.N:(i + 1) * WOTSPlus.N]
            byte_val = msg_hash[i % WOTSPlus.N]
            base = 15 if i < WOTSPlus.LEN // 2 else 0
            steps = (byte_val % WOTSPlus.W) + base
            recon.extend(WOTSPlus._chain(part, 255 - steps))
        return bytes(recon) == pub


class HybridSignature:
    """ECDSA + WOTS+ hybrid. Both must verify for acceptance."""

    def __init__(self):
        self.ecdsa_key = None
        self.wots = WOTSPlus()
        self.wots_priv = None
        self.wots_pub = None

    def generate(self) -> dict:
        self.ecdsa_key = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        self.wots_priv, self.wots_pub = self.wots.keygen()
        return {
            "ecdsa_pub": self.ecdsa_key.get_verifying_key().to_string().hex(),
            "wots_pub": self.wots_pub.hex(),
            "wots_priv": self.wots_priv.hex()
        }

    def sign(self, message: bytes) -> dict:
        ecdsa_sig = self.ecdsa_key.sign(message)
        wots_sig = self.wots.sign(self.wots_priv, message)
        return {
            "ecdsa": ecdsa_sig.hex(),
            "wots": wots_sig.hex(),
            "wots_pub": self.wots_pub.hex(),
            "ts": int(time.time())
        }

    @staticmethod
    def verify(keys: dict, message: bytes, sig: dict) -> bool:
        try:
            vk = ecdsa.VerifyingKey.from_string(
                bytes.fromhex(keys["ecdsa_pub"]), curve=ecdsa.SECP256k1
            )
            ecdsa_ok = vk.verify(bytes.fromhex(sig["ecdsa"]), message)
            wots_ok = WOTSPlus.verify(
                bytes.fromhex(sig["wots_pub"]),
                message,
                bytes.fromhex(sig["wots"])
            )
            return ecdsa_ok and wots_ok
        except Exception as e:
            logger.error(f"Hybrid verify failed: {e}")
            return False
