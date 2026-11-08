"""Lado do CONVIDADO: recebe vídeo/áudio do host e envia o controle."""
import json
import socket
import threading
import time

import av
import numpy as np
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage

import xinput as xi
from protocol import (AUDIO, BYE, CODEC_H264, HELLO, INPUT, KEYREQ, PAD, PING, PING_S, PONG, REJECT,
                      RUMBLE, RUMBLE_S, VERSION, VIDEO, VIDEO_HDR, WELCOME, Conn)

K = Qt.Key
# Teclado -> botões do controle (layout Xbox; o PCSX2 converte para DualShock 2)
KEY_BUTTONS = {
    K.Key_Up: xi.DPAD_UP, K.Key_Down: xi.DPAD_DOWN, K.Key_Left: xi.DPAD_LEFT, K.Key_Right: xi.DPAD_RIGHT,
    K.Key_K: xi.A,      # X (Cross)
    K.Key_L: xi.B,      # Bola (Circle)
    K.Key_J: xi.X,      # Quadrado
    K.Key_I: xi.Y,      # Triângulo
    K.Key_Q: xi.LB,     # L1
    K.Key_E: xi.RB,     # R1
    K.Key_Return: xi.START, K.Key_Enter: xi.START,
    K.Key_Backspace: xi.BACK,
    K.Key_F: xi.LTHUMB, K.Key_H: xi.RTHUMB,
}
KEY_LT, KEY_RT = K.Key_Z, K.Key_C   # L2 / R2
STICK_L = {K.Key_W: (0, 1), K.Key_S: (0, -1), K.Key_A: (-1, 0), K.Key_D: (1, 0)}
STICK_R = {K.Key_8: (0, 1), K.Key_5: (0, -1), K.Key_4: (-1, 0), K.Key_6: (1, 0)}

KEYBOARD_HELP = (
    "Setas = D-pad   •   W A S D = analógico esquerdo   •   Teclado num. 8 4 5 6 = analógico direito\n"
    "K = ✕   L = ◯   J = ▢   I = △   •   Q = L1   E = R1   Z = L2   C = R2   •   F = L3   H = R3\n"
    "Enter = Start   Backspace = Select   •   F11 = tela cheia   F1 = estatísticas"
)


def _stick(keys, mapping):
    x = y = 0
    for k, (dx, dy) in mapping.items():
        if k in keys:
            x += dx
            y += dy
    return max(-1, min(1, x)) * 32767, max(-1, min(1, y)) * 32767


class AudioPlayer:
    def __init__(self, rate, channels):
        import pyaudiowpatch as pyaudio

        self.rate, self.ch = rate, channels
        self.bytes_per_ms = rate * channels * 2 / 1000
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.volume = 1.0
        self.primed = False
        self.pa = pyaudio.PyAudio()
        self._cont = pyaudio.paContinue
        self.stream = self.pa.open(format=pyaudio.paInt16, channels=channels, rate=rate, output=True,
                                   frames_per_buffer=rate // 100, stream_callback=self._cb)
        self.stream.start_stream()

    def _align(self, n):
        return int(n) // (self.ch * 2) * (self.ch * 2)

    def push(self, data):
        with self.lock:
            self.buf += data
            if len(self.buf) > self.bytes_per_ms * 160:   # atraso acumulado: descarta
                del self.buf[: len(self.buf) - self._align(self.bytes_per_ms * 50)]

    def _cb(self, in_data, frame_count, time_info, status):
        need = frame_count * self.ch * 2
        with self.lock:
            if not self.primed and len(self.buf) >= self.bytes_per_ms * 40:
                self.primed = True
            if self.primed and len(self.buf) >= need:
                out = bytes(self.buf[:need])
                del self.buf[:need]
            else:
                if self.primed and len(self.buf) < need:
                    self.primed = False
                out = b"\x00" * need
        if self.volume != 1.0:
            arr = (np.frombuffer(out, np.int16).astype(np.float32) * self.volume)
            out = np.clip(arr, -32768, 32767).astype(np.int16).tobytes()
        return (out, self._cont)

    def close(self):
        try:
            self.stream.stop_stream()
            self.stream.close()
        except Exception:
            pass
        self.pa.terminate()


class GuestClient(QObject):
    frame = Signal(QImage)
    welcome = Signal(dict)
    failed = Signal(str)
    disconnected = Signal(str)
    stats = Signal(dict)

    def __init__(self, host, port, name, password, pad_index=-1, volume=1.0):
        super().__init__()
        self.host, self.port, self.name, self.password = host, port, name, password
        self.pad_index = pad_index      # -1 = automático, -2 = só teclado, 0..3 = XInput fixo
        self.volume = volume
        self.keys = frozenset()
        self.running = False
        self.conn = None
        self.audio = None
        self.rtt = 0.0
        self._active_pad = None
        self._frames = 0
        self._bytes = 0
        self._last_keyreq = 0.0

    # ------------------------------------------------------------- API usada pela interface
    def start(self):
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        if not self.running:
            return
        self.running = False
        try:
            if self.conn:
                self.conn.send(BYE)
        except Exception:
            pass
        if self.conn:
            self.conn.close()

    def set_keys(self, keys):
        self.keys = frozenset(keys)

    def set_volume(self, v):
        self.volume = v
        if self.audio:
            self.audio.volume = v

    # ------------------------------------------------------------- threads
    def _run(self):
        reason = "Desconectado."
        try:
            sock = socket.create_connection((self.host, self.port), timeout=8)
            self.conn = Conn(sock)
            self.conn.send_json(HELLO, {"version": VERSION, "name": self.name, "password": self.password})
            mtype, payload = self.conn.recv()
            if mtype == REJECT:
                self.running = False
                self.failed.emit(payload.decode("utf-8", "replace"))
                self.conn.close()
                return
            if mtype != WELCOME:
                raise ConnectionError("resposta inesperada do host")
            info = json.loads(payload.decode("utf-8"))
            sock.settimeout(None)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
            if info.get("audio"):
                try:
                    self.audio = AudioPlayer(info["audio"]["rate"], info["audio"]["channels"])
                    self.audio.volume = self.volume
                except Exception as e:
                    info["audio_error"] = str(e)
            self.welcome.emit(info)
            threading.Thread(target=self._input_loop, daemon=True).start()
            self._recv_loop()
        except socket.timeout:
            reason = "Tempo esgotado: o host não respondeu. Confira IP, porta e firewall."
            if not self.conn or not self.running:
                self.failed.emit(reason)
                self.running = False
                return
        except (OSError, ConnectionError) as e:
            if self.conn is None:
                self.running = False
                self.failed.emit(f"Não foi possível conectar: {e}")
                return
            reason = "A conexão com o host caiu." if self.running else "Desconectado."
        finally:
            self.running = False
            if self.audio:
                self.audio.close()
                self.audio = None
            if self._active_pad is not None:
                xi.set_vibration(self._active_pad, 0, 0)
        self.disconnected.emit(reason)

    def _recv_loop(self):
        decoder = av.CodecContext.create("h264", "r")
        decoder.thread_type = "SLICE"
        stat_t = time.perf_counter()
        while self.running:
            mtype, payload = self.conn.recv()
            self._bytes += len(payload)
            if mtype == VIDEO:
                codec, key = VIDEO_HDR.unpack_from(payload)
                data = payload[VIDEO_HDR.size:]
                img = None
                if codec == CODEC_H264:
                    try:
                        for fr in decoder.decode(av.Packet(data)):
                            arr = fr.to_ndarray(format="rgb24")
                            h, w = arr.shape[:2]
                            img = QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
                    except Exception:
                        now = time.perf_counter()
                        if now - self._last_keyreq > 0.5:
                            self._last_keyreq = now
                            self.conn.send(KEYREQ)
                else:
                    img = QImage.fromData(data, "JPG")
                if img is not None and not img.isNull():
                    self._frames += 1
                    self.frame.emit(img)
            elif mtype == AUDIO:
                if self.audio:
                    self.audio.push(payload)
            elif mtype == PONG:
                t0, _ = PING_S.unpack(payload)
                self.rtt = (time.perf_counter() - t0) * 1000
            elif mtype == RUMBLE:
                large, small = RUMBLE_S.unpack(payload)
                if self._active_pad is not None:
                    xi.set_vibration(self._active_pad, large, small)
            elif mtype == BYE:
                break
            now = time.perf_counter()
            if now - stat_t >= 1.0:
                dt = now - stat_t
                self.stats.emit({"fps": self._frames / dt, "kbps": self._bytes * 8 / 1000 / dt,
                                 "rtt": self.rtt, "pad": self._active_pad})
                self._frames = self._bytes = 0
                stat_t = now

    def _pick_pad(self):
        if self.pad_index == -2:
            return None
        if self.pad_index >= 0:
            return self.pad_index if xi.get_state(self.pad_index) is not None else None
        c = xi.connected()
        return c[0] if c else None

    def _input_loop(self):
        last, last_send, last_ping, last_scan = None, 0.0, 0.0, 0.0
        while self.running:
            now = time.perf_counter()
            if now - last_scan > 1.0 and (self._active_pad is None or self.pad_index != -1):
                self._active_pad = self._pick_pad()
                last_scan = now
            st = xi.get_state(self._active_pad) if self._active_pad is not None else None
            if st is None:
                if self._active_pad is not None:
                    self._active_pad = None
                st = (0, 0, 0, 0, 0, 0, 0)
            b, lt, rt, lx, ly, rx, ry = st

            keys = self.keys
            if keys:
                for k, bit in KEY_BUTTONS.items():
                    if k in keys:
                        b |= bit
                if KEY_LT in keys:
                    lt = 255
                if KEY_RT in keys:
                    rt = 255
                kx, ky = _stick(keys, STICK_L)
                if kx or ky:
                    lx, ly = kx, ky
                kx, ky = _stick(keys, STICK_R)
                if kx or ky:
                    rx, ry = kx, ky

            state = (b, lt, rt, lx, ly, rx, ry)
            try:
                if state != last or now - last_send > 0.05:
                    self.conn.send(INPUT, PAD.pack(*state))
                    last, last_send = state, now
                if now - last_ping > 1.0:
                    self.conn.send(PING, PING_S.pack(now, self.rtt))
                    last_ping = now
            except (OSError, ConnectionError):
                break
            time.sleep(0.004)
