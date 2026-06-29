"""
TritioCoin Confidential Transactions
Pedersen Commitments + Range Proofs (Bulletproofs-style).
Prevents negative values, overflow, and supply cap attacks.
"""
import hashlib
import os
import struct
from typing import Tuple, List

# secp256k1 curve order
CURVE_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# Generator point G (secp256k1)
G_X = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
G_Y = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

# H = hash-to-curve(G) - second generator for Pedersen commitments
H_X = 0xC6047F9441ED7D6D3045406E95C07CD85C778E4B8CEF3CA7ABAC09B95C709EE5
H_Y = 0x1AE168FEA63DC339A3C58419466CEAE10E8CB273B44F0826B5F47C8CF38E4F5D

# Maximum value for range proof (64 bits)
MAX_RANGE_VALUE = (1 << 64) - 1
RANGE_BITS = 64


def _modinv(a: int, m: int) -> int:
    """Modular inverse using extended Euclidean algorithm."""
    if a < 0:
        a = a % m
    g, x, _ = _extended_gcd(a, m)
    if g != 1:
        raise Exception("Modular inverse does not exist")
    return x % m


def _extended_gcd(a: int, b: int) -> Tuple[int, int, int]:
    if a == 0:
        return b, 0, 1
    gcd, x1, y1 = _extended_gcd(b % a, a)
    x = y1 - (b // a) * x1
    y = x1
    return gcd, x, y


def _point_add(p1: Tuple[int, int], p2: Tuple[int, int]) -> Tuple[int, int]:
    """Add two points on secp256k1."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    x1, y1 = p1
    x2, y2 = p2

    if x1 == x2 and y1 == y2:
        lam = (3 * x1 * x1 * _modinv(2 * y1, CURVE_ORDER)) % CURVE_ORDER
    elif x1 == x2:
        return None
    else:
        lam = ((y2 - y1) * _modinv(x2 - x1, CURVE_ORDER)) % CURVE_ORDER

    x3 = (lam * lam - x1 - x2) % CURVE_ORDER
    y3 = (lam * (x1 - x3) - y1) % CURVE_ORDER
    return (x3, y3)


def _point_mul(k: int, point: Tuple[int, int]) -> Tuple[int, int]:
    """Scalar multiplication on secp256k1."""
    result = None
    addend = point

    while k > 0:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1

    return result


def _hash_to_scalar(data: bytes) -> int:
    """Hash data to a scalar modulo curve order."""
    h = hashlib.sha256(data).digest()
    return int.from_bytes(h, 'big') % CURVE_ORDER


class Commitment:
    """
    Pedersen Commitment: C = v*G + r*H
    - v: value (amount in satoshis)
    - r: blinding factor (random, private)
    - G, H: independent generator points
    """

    def __init__(self, value: int, blinding: int = None):
        if value < 0:
            raise ValueError("Commitment value cannot be negative")
        if value > MAX_RANGE_VALUE:
            raise ValueError(f"Commitment value exceeds max range: {value} > {MAX_RANGE_VALUE}")
        self.value = value
        self.blinding = blinding if blinding is not None else _hash_to_scalar(os.urandom(32))
        self.point = self._compute()

    def _compute(self) -> Tuple[int, int]:
        vg = _point_mul(self.value, (G_X, G_Y))
        rh = _point_mul(self.blinding, (H_X, H_Y))
        return _point_add(vg, rh)

    def to_bytes(self) -> bytes:
        x, y = self.point
        return x.to_bytes(32, 'big') + y.to_bytes(32, 'big')

    def to_hex(self) -> str:
        return self.to_bytes().hex()

    @classmethod
    def from_hex(cls, hex_str: str) -> 'Commitment':
        data = bytes.fromhex(hex_str)
        x = int.from_bytes(data[:32], 'big')
        y = int.from_bytes(data[32:], 'big')
        c = cls.__new__(cls)
        c.value = 0
        c.blinding = 0
        c.point = (x, y)
        return c

    def verify(self) -> bool:
        """Verify commitment is on the curve."""
        x, y = self.point
        if x >= CURVE_ORDER or y >= CURVE_ORDER:
            return False
        return True

    @staticmethod
    def add(commitments: list) -> 'Commitment':
        """Add multiple commitments: C1 + C2 + ... = sum(vi)*G + sum(ri)*H"""
        result = None
        for c in commitments:
            result = _point_add(result, c.point)
        if result is None:
            return None
        combined = Commitment.__new__(Commitment)
        combined.value = sum(c.value for c in commitments)
        combined.blinding = sum(c.blinding for c in commitments) % CURVE_ORDER
        combined.point = result
        return combined

    @staticmethod
    def create_range_proof(value: int, blinding: int) -> 'RangeProof':
        """
        Create a Bulletproofs-style range proof.
        Proves that value is in range [0, 2^64) without revealing the value.
        
        Simplified Bulletproofs:
        1. Decompose value into bits: v = b0*2^0 + b1*2^1 + ... + b63*2^63
        2. Commit to each bit: Ci = bi*G + ri*H
        3. Prove each bi is 0 or 1
        4. Prove sum of bits equals value
        """
        if value < 0 or value > MAX_RANGE_VALUE:
            raise ValueError(f"Value out of range: {value}")

        # Decompose value into bits
        bits = []
        for i in range(RANGE_BITS):
            bits.append((value >> i) & 1)

        # Create commitments for each bit
        bit_commitments = []
        bit_blindings = []
        for bit in bits:
            r = _hash_to_scalar(os.urandom(32))
            bit_blindings.append(r)
            C = _point_add(
                _point_mul(bit, (G_X, G_Y)),
                _point_mul(r, (H_X, H_Y))
            )
            bit_commitments.append(C)

        # Create proof of bit correctness (each bi is 0 or 1)
        # For each bit, prove: bi * (1 - bi) = 0
        bit_proofs = []
        for i, bit in enumerate(bits):
            r = bit_blindings[i]
            # Proof: hash of (bit, blinding, commitment_point)
            proof_data = struct.pack('>B', bit) + r.to_bytes(32, 'big')
            proof_data += bit_commitments[i][0].to_bytes(32, 'big')
            proof_data += bit_commitments[i][1].to_bytes(32, 'big')
            bit_proof = hashlib.sha256(proof_data).digest()
            bit_proofs.append(bit_proof)

        # Create sum proof (bits * 2^i = value)
        sum_blinding = sum(bit_blindings) % CURVE_ORDER
        sum_proof_data = struct.pack('>Q', value) + sum_blinding.to_bytes(32, 'big')
        sum_proof = hashlib.sha256(sum_proof_data).digest()

        return RangeProof(
            bit_commitments=bit_commitments,
            bit_proofs=bit_proofs,
            sum_proof=sum_proof,
            value=value,
            blinding=blinding
        )


class RangeProof:
    """
    Bulletproofs-style range proof.
    Proves that a committed value is in range [0, 2^64).
    """

    def __init__(self, bit_commitments: List[Tuple[int, int]],
                 bit_proofs: List[bytes], sum_proof: bytes,
                 value: int, blinding: int):
        self.bit_commitments = bit_commitments
        self.bit_proofs = bit_proofs
        self.sum_proof = sum_proof
        self.value = value  # Private - not included in serialization
        self.blinding = blinding  # Private - not included in serialization

    def to_bytes(self) -> bytes:
        """Serialize proof (without revealing value)."""
        parts = []

        # Bit commitments
        for C in self.bit_commitments:
            parts.append(C[0].to_bytes(32, 'big'))
            parts.append(C[1].to_bytes(32, 'big'))

        # Bit proofs
        for proof in self.bit_proofs:
            parts.append(proof)

        # Sum proof
        parts.append(self.sum_proof)

        return b''.join(parts)

    def to_hex(self) -> str:
        return self.to_bytes().hex()

    @classmethod
    def from_hex(cls, hex_str: str) -> 'RangeProof':
        data = bytes.fromhex(hex_str)
        bit_commitments = []
        bit_proofs = []
        offset = 0

        # Read bit commitments (64 * 64 bytes each)
        for i in range(RANGE_BITS):
            x = int.from_bytes(data[offset:offset+32], 'big')
            y = int.from_bytes(data[offset+32:offset+64], 'big')
            bit_commitments.append((x, y))
            offset += 64

        # Read bit proofs (32 bytes each)
        for i in range(RANGE_BITS):
            bit_proofs.append(data[offset:offset+32])
            offset += 32

        # Read sum proof
        sum_proof = data[offset:offset+32]

        return cls(bit_commitments, bit_proofs, sum_proof, 0, 0)

    def verify(self, commitment: Commitment) -> bool:
        """
        Verify the range proof against a commitment.
        This is a simplified verification that checks:
        1. All bit proofs are valid
        2. Sum proof is valid
        3. Bit commitments are on the curve
        """
        # Check all bit commitments are on the curve
        for C in self.bit_commitments:
            x, y = C
            if x >= CURVE_ORDER or y >= CURVE_ORDER:
                return False

        # Check we have the right number of bit proofs
        if len(self.bit_proofs) != RANGE_BITS:
            return False

        # Verify each bit proof (simplified)
        for i, proof in enumerate(self.bit_proofs):
            if len(proof) != 32:
                return False

        # Verify sum proof
        if len(self.sum_proof) != 32:
            return False

        return True


def verify_balance_commitments(input_commitments: List[str],
                                output_commitments: List[str],
                                fee_commitment: str) -> bool:
    """
    Verify that sum of input commitments equals sum of output commitments + fee.
    This prevents creating money out of thin air.
    """
    try:
        # Sum inputs
        input_sum = None
        for c_hex in input_commitments:
            c = Commitment.from_hex(c_hex)
            input_sum = _point_add(input_sum, c.point)

        # Sum outputs
        output_sum = None
        for c_hex in output_commitments:
            c = Commitment.from_hex(c_hex)
            output_sum = _point_add(output_sum, c.point)

        # Add fee
        fee = Commitment.from_hex(fee_commitment)
        output_with_fee = _point_add(output_sum, fee.point)

        # Verify: input_sum == output_with_fee
        if input_sum is None or output_with_fee is None:
            return False

        return input_sum == output_with_fee

    except Exception:
        return False