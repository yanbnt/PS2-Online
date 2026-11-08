"""Protocolo de rede do PS2 Online (TCP, mensagens com cabeçalho tipo+tamanho)."""
import json
import socket
import struct
import threading

VERSION = 1
DEFAULT_PORT = 27900
MAX_MSG = 8 * 1024 * 1024

# Tipos de mensagem
HELLO = 1      # convidado -> host  (json)
WELCOME = 2    # host -> convidado  (json)
REJECT = 3     # host -> convidado  (texto)
VIDEO = 4      # host -> convidado  (codec, keyframe, dados)
AUDIO = 5      # host -> convidado  (PCM 16-bit)
INPUT = 6      # convidado -> host  (estado do controle)
PING = 7       # convidado -> host  (double t, float rtt_ms)
PONG = 8       # host -> convidado  (eco)
RUMBLE = 9     # host -> convidado  (motor grande, motor pequeno)
KEYREQ = 10    # convidado -> host  (pede keyframe)
BYE = 11

CODEC_H264 = 1
CODEC_JPEG = 2

HDR = struct.Struct("<BI")
# Mesmo layout do XINPUT_GAMEPAD / XUSB_REPORT
PAD = struct.Struct("<HBBhhhh")
VIDEO_HDR = struct.Struct("<BB")
PING_S = struct.Struct("<df")
RUMBLE_S = struct.Struct("<BB")


class Conn:
    """Envolve um socket com envio thread-safe e leitura de mensagens."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.lock = threading.Lock()
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def send(self, mtype: int, payload: bytes = b""):
        data = HDR.pack(mtype, len(payload)) + payload
        with self.lock:
            self.sock.sendall(data)

    def send_json(self, mtype: int, obj):
        self.send(mtype, json.dumps(obj).encode("utf-8"))

    def _recv_exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("conexão encerrada")
            buf += chunk
        return bytes(buf)

    def recv(self, max_size: int = MAX_MSG):
        mtype, size = HDR.unpack(self._recv_exact(HDR.size))
        if size > max_size:
            raise ConnectionError("mensagem grande demais")
        return mtype, (self._recv_exact(size) if size else b"")

    def close(self):
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
