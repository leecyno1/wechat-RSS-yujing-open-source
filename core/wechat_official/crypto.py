from __future__ import annotations

import base64
import hashlib
import os
import struct
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _as_str(v: Any) -> str:
    return str(v or "").strip()


def _sha1(parts: list[str]) -> str:
    raw = "".join(sorted([_as_str(p) for p in parts if _as_str(p)])).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def verify_signature(*, token: str, signature: str, timestamp: str, nonce: str) -> bool:
    sig = _as_str(signature)
    if not sig:
        return False
    expect = _sha1([token, timestamp, nonce])
    return sig == expect


def verify_msg_signature(*, token: str, msg_signature: str, timestamp: str, nonce: str, encrypted: str) -> bool:
    sig = _as_str(msg_signature)
    if not sig:
        return False
    expect = _sha1([token, timestamp, nonce, encrypted])
    return sig == expect


def _pkcs7_pad(data: bytes, block_size: int = 32) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    if pad_len == 0:
        pad_len = block_size
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 32:
        return data
    return data[:-pad_len]


@dataclass(frozen=True)
class WeChatCrypto:
    token: str
    encoding_aes_key: str
    appid: str

    def __post_init__(self):
        aes_key = _as_str(self.encoding_aes_key)
        if not aes_key:
            raise ValueError("encoding_aes_key is required")
        key = base64.b64decode(aes_key + "=")
        if len(key) != 32:
            raise ValueError("invalid encoding_aes_key length")
        object.__setattr__(self, "_key", key)
        object.__setattr__(self, "_iv", key[:16])

    def decrypt(self, encrypted: str) -> str:
        enc = _as_str(encrypted)
        if not enc:
            raise ValueError("encrypted is required")

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv))
        decryptor = cipher.decryptor()
        plain_padded = decryptor.update(base64.b64decode(enc)) + decryptor.finalize()
        plain = _pkcs7_unpad(plain_padded)
        if len(plain) < 20:
            raise ValueError("invalid plaintext length")

        msg_len = struct.unpack("!I", plain[16:20])[0]
        xml_bytes = plain[20 : 20 + msg_len]
        appid_bytes = plain[20 + msg_len :]

        appid = appid_bytes.decode("utf-8", errors="ignore").strip()
        if _as_str(self.appid) and appid != _as_str(self.appid):
            raise ValueError("appid mismatch")

        return xml_bytes.decode("utf-8", errors="ignore")

    def encrypt(self, plaintext_xml: str) -> str:
        xml_bytes = _as_str(plaintext_xml).encode("utf-8")
        appid_bytes = _as_str(self.appid).encode("utf-8")

        random16 = os.urandom(16)
        msg_len = struct.pack("!I", len(xml_bytes))
        plain = random16 + msg_len + xml_bytes + appid_bytes
        plain_padded = _pkcs7_pad(plain)

        cipher = Cipher(algorithms.AES(self._key), modes.CBC(self._iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(plain_padded) + encryptor.finalize()
        return base64.b64encode(encrypted).decode("utf-8")

