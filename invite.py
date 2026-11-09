"""Código de convite: IP/porta/senha/nome do host num texto curto tipo "PS2-ABCD-EFGH-...".

Atenção: é só codificado (base32), não criptografado — quem tem o código tem a senha.
"""
import base64
import binascii
import ipaddress
import re
import struct

PREFIX = "PS2-"
VERSION = 1
_PATTERN = re.compile(r"PS2-[A-Z2-7\-]{16,}", re.IGNORECASE)


def _pack_str(s: str) -> bytes:
    b = s.encode("utf-8")[:255]
    return bytes([len(b)]) + b


def encode(host: str, port: int, password: str = "", name: str = "") -> str:
    try:
        ip = ipaddress.IPv4Address(host)
        addr = b"\x00" + ip.packed                  # 0 = IPv4
    except ValueError:
        addr = b"\x01" + _pack_str(host)           # 1 = nome (ex.: meupc.tail1234.ts.net)
    body = bytes([VERSION]) + addr + struct.pack(">H", port) + _pack_str(password) + _pack_str(name)
    body += struct.pack(">H", binascii.crc_hqx(body, 0xFFFF))
    code = base64.b32encode(body).decode().rstrip("=")
    return PREFIX + "-".join(code[i:i + 4] for i in range(0, len(code), 4))


def decode(text: str):
    """Acha e lê um convite dentro de qualquer texto. Retorna dict ou None."""
    if not text:
        return None
    m = _PATTERN.search(text.strip())
    if not m:
        return None
    raw = m.group(0)[len(PREFIX):].replace("-", "").upper()
    try:
        body = base64.b32decode(raw + "=" * (-len(raw) % 8))
        data, crc = body[:-2], struct.unpack(">H", body[-2:])[0]
        if binascii.crc_hqx(data, 0xFFFF) != crc or data[0] != VERSION:
            return None
        i = 1
        if data[i] == 0:
            host = str(ipaddress.IPv4Address(data[i + 1:i + 5]))
            i += 5
        else:
            n = data[i + 1]
            host = data[i + 2:i + 2 + n].decode("utf-8")
            i += 2 + n
        port = struct.unpack(">H", data[i:i + 2])[0]
        i += 2
        out = []
        for _ in range(2):
            n = data[i]
            out.append(data[i + 1:i + 1 + n].decode("utf-8"))
            i += 1 + n
        return {"host": host, "port": port, "password": out[0], "name": out[1], "code": m.group(0).upper()}
    except (binascii.Error, IndexError, ValueError, struct.error, UnicodeDecodeError):
        return None
