"""Chamada de voz do PS2 Online.

Microfone -> 48 kHz mono, quadros de 20 ms -> detecção de voz / apertar-para-falar -> Opus -> rede
Rede -> Opus -> fila por pessoa -> mixagem -> alto-falante

Quem fala é identificado por um número: 0 = host, 1 = Jogador 2, 2 = Jogador 3, 3 = Jogador 4.
"""
import collections
import threading
import time

import av
import numpy as np

RATE = 48000
FRAME = 960          # 20 ms
BYTES_MS = RATE * 2 / 1000

# teclas para "apertar para falar" (códigos virtuais do Windows)
PTT_KEYS = {
    "CapsLock": 0x14, "V": 0x56, "T": 0x54, "B": 0x42,
    "Botão lateral do mouse 1": 0x05, "Botão lateral do mouse 2": 0x06, "Alt esquerdo": 0xA4,
}
MUTE_KEY = 0x78      # F9 alterna mudo

_user32 = None


def key_down(vk) -> bool:
    """Tecla pressionada agora (funciona mesmo com outra janela em foco, ex.: o PCSX2)."""
    global _user32
    if _user32 is None:
        import ctypes
        _user32 = ctypes.WinDLL("user32")
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


def input_devices():
    """Lista [(índice, nome)] dos microfones (WASAPI)."""
    import pyaudiowpatch as pyaudio
    p = pyaudio.PyAudio()
    try:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        out = []
        for i in range(p.get_device_count()):
            d = p.get_device_info_by_index(i)
            if d["hostApi"] == wasapi and d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice"):
                out.append((i, d["name"]))
        return out
    finally:
        p.terminate()


class OpusEncoder:
    def __init__(self, bitrate=32000):
        c = av.CodecContext.create("libopus", "w")
        c.sample_rate, c.layout, c.format, c.bit_rate = RATE, "mono", "s16", bitrate
        c.options = {"application": "voip", "frame_duration": "20"}
        self.c = c
        self.pts = 0

    def encode(self, pcm: np.ndarray):
        f = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
        f.sample_rate = RATE
        f.pts = self.pts
        self.pts += len(pcm)
        return [bytes(p) for p in self.c.encode(f)]


class OpusDecoder:
    def __init__(self):
        c = av.CodecContext.create("libopus", "r")
        c.sample_rate, c.layout = RATE, "mono"
        self.c = c

    def decode(self, data: bytes) -> bytes:
        out = b""
        for f in self.c.decode(av.Packet(data)):
            a = f.to_ndarray()
            if a.dtype != np.int16:
                a = (np.clip(a, -1, 1) * 32767).astype(np.int16)
            out += np.ascontiguousarray(a.reshape(-1)[: f.samples]).tobytes()
        return out


def _db(pcm: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2))) + 1e-9
    return 20 * np.log10(rms / 32768)


class Mic:
    """Captura o microfone e entrega pacotes Opus via on_packet(bytes)."""

    def __init__(self, on_packet, device_index=None):
        self.on_packet = on_packet
        self.device_index = device_index
        self.muted = False
        self.ptt_mode = False
        self.ptt_down = False
        self.threshold_db = -45.0
        self.level = 0.0          # 0..1 para o medidor
        self.talking = False      # está transmitindo agora
        self._hang = 0.0
        self._enc = OpusEncoder()
        self._buf = np.zeros(0, np.int16)
        self._pa = self._stream = None
        self.device_name = ""

    def start(self):
        import pyaudiowpatch as pyaudio
        self._pa = pyaudio.PyAudio()
        if self.device_index is None:
            wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            self.device_index = wasapi["defaultInputDevice"]
        d = self._pa.get_device_info_by_index(self.device_index)
        self.device_name = d["name"]
        ch = max(1, min(2, int(d["maxInputChannels"])))
        rate = int(d["defaultSampleRate"])
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        self._in_layout = "mono" if ch == 1 else "stereo"
        self._in_rate = rate

        def cb(in_data, frames, info, status):
            try:
                self._feed(in_data, ch)
            except Exception:
                pass
            return (None, pyaudio.paContinue)

        self._stream = self._pa.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                                     input_device_index=self.device_index, frames_per_buffer=rate // 100,
                                     stream_callback=cb)
        self._stream.start_stream()

    def _feed(self, data, ch):
        a = np.frombuffer(data, np.int16)
        f = av.AudioFrame.from_ndarray(a.reshape(1, -1), format="s16", layout=self._in_layout)
        f.sample_rate = self._in_rate
        for r in self._resampler.resample(f):
            self._buf = np.concatenate([self._buf, r.to_ndarray().reshape(-1).astype(np.int16)])
        while len(self._buf) >= FRAME:
            frame, self._buf = self._buf[:FRAME], self._buf[FRAME:]
            self.process_frame(frame)

    def process_frame(self, frame: np.ndarray):
        """Recebe 20 ms de áudio 48 kHz mono (também usado nos testes)."""
        db = _db(frame)
        self.level = max(0.0, min(1.0, (db + 60) / 50))
        now = time.time()
        if db > self.threshold_db:
            self._hang = now + 0.35
        if self.muted:
            send = False
        elif self.ptt_mode:
            send = self.ptt_down
        else:
            send = now < self._hang
        self.talking = send
        if send:
            for pkt in self._enc.encode(frame):
                self.on_packet(pkt)

    def stop(self):
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        if self._pa:
            self._pa.terminate()
        self._stream = self._pa = None


class VoiceMixer:
    """Toca as vozes de todos, cada uma com sua fila (jitter buffer) e decodificador."""

    def __init__(self, volume=1.0):
        self.volume = volume
        self._lock = threading.Lock()
        self._bufs = collections.defaultdict(bytearray)
        self._primed = collections.defaultdict(bool)
        self._dec = {}
        self._last_talk = {}
        self._pa = self._stream = None

    def start(self):
        import pyaudiowpatch as pyaudio
        self._pa = pyaudio.PyAudio()
        self._cont = pyaudio.paContinue
        self._stream = self._pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, output=True,
                                     frames_per_buffer=RATE // 100, stream_callback=self._cb)
        self._stream.start_stream()

    def push(self, speaker: int, data: bytes):
        dec = self._dec.get(speaker)
        if dec is None:
            dec = self._dec[speaker] = OpusDecoder()
        try:
            pcm = dec.decode(data)
        except Exception:
            return
        if pcm and _db(np.frombuffer(pcm, np.int16)) > -50:
            self._last_talk[speaker] = time.time()
        with self._lock:
            b = self._bufs[speaker]
            b += pcm
            if len(b) > BYTES_MS * 220:                      # atrasou demais: descarta o excesso
                del b[: len(b) - int(BYTES_MS * 60) // 2 * 2]

    def speaking(self, speaker: int) -> bool:
        return time.time() - self._last_talk.get(speaker, 0) < 0.35

    def pull(self, frames: int) -> bytes:
        """Mistura `frames` amostras de todas as vozes (usado pela placa de som e nos testes)."""
        need = frames * 2
        mix = np.zeros(frames, np.int32)
        with self._lock:
            for spk, b in self._bufs.items():
                if not self._primed[spk]:
                    if len(b) >= BYTES_MS * 60:
                        self._primed[spk] = True
                    else:
                        continue
                if len(b) < need:
                    self._primed[spk] = False
                    take = bytes(b[: len(b) // 2 * 2])
                    del b[: len(take)]
                else:
                    take = bytes(b[:need])
                    del b[:need]
                a = np.frombuffer(take, np.int16)
                mix[: len(a)] += a
        if self.volume != 1.0:
            mix = (mix * self.volume).astype(np.int32)
        return np.clip(mix, -32768, 32767).astype(np.int16).tobytes()

    def _cb(self, in_data, frames, info, status):
        try:
            return (self.pull(frames), self._cont)
        except Exception:
            return (b"\x00" * frames * 2, self._cont)

    def stop(self):
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        if self._pa:
            self._pa.terminate()
        self._stream = self._pa = None
