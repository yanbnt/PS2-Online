"""Lado do HOST: captura a tela do PCSX2, transmite vídeo/áudio e cria controles virtuais."""
import collections
import fractions
import hmac
import json
import socket
import threading
import time

import av
import mss
import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

import pcsx2
from protocol import (AUDIO, BYE, CODEC_H264, CODEC_JPEG, HELLO, INPUT, KEYREQ, PAD, PING, PING_S, PONG,
                      REJECT, RUMBLE, RUMBLE_S, VERSION, VIDEO, VIDEO_HDR, WELCOME, Conn)

MAX_FAILS = 5          # tentativas erradas antes de bloquear o IP
BAN_SECONDS = 600
MAX_PENDING = 16       # conexões ainda sem login ao mesmo tempo
MAX_INBOUND = 4096     # convidado só envia mensagens pequenas (controle/ping)

ENCODERS = {
    "libx264": ("H.264 – CPU (funciona em qualquer PC)", {"preset": "ultrafast", "tune": "zerolatency"}),
    "h264_nvenc": ("H.264 – placa NVIDIA", {"preset": "p1", "tune": "ull", "zerolatency": "1", "delay": "0"}),
    "h264_amf": ("H.264 – placa AMD", {"usage": "ultralowlatency", "quality": "speed"}),
    "h264_qsv": ("H.264 – Intel QuickSync", {"preset": "veryfast", "async_depth": "1"}),
    "jpeg": ("JPEG (sem compressão entre quadros, usa muita banda)", {}),
}


def _jpeg(src: av.VideoFrame, w, h, quality) -> bytes:
    arr = src.reformat(width=w, height=h, format="rgb24", interpolation="AREA").to_ndarray()
    img = QImage(arr.data, w, h, arr.strides[0], QImage.Format.Format_RGB888)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "JPG", quality)
    buf.close()
    return bytes(ba.data())


class H264Encoder:
    def __init__(self, name, w, h, fps, bitrate_kbps, log):
        self.w, self.h = w, h
        self.pts = 0
        try:
            self.ctx = self._make(name, w, h, fps, bitrate_kbps)
            self.name = name
        except Exception as e:  # codec de hardware indisponível -> CPU
            if name != "libx264":
                log(f"Codificador {name} indisponível ({e}); usando libx264 (CPU).")
            self.ctx = self._make("libx264", w, h, fps, bitrate_kbps)
            self.name = "libx264"
        self.pix_fmt = self.ctx.pix_fmt

    @staticmethod
    def _make(name, w, h, fps, bitrate_kbps):
        ctx = av.CodecContext.create(name, "w")
        ctx.width, ctx.height = w, h
        ctx.pix_fmt = "nv12" if name == "h264_qsv" else "yuv420p"
        ctx.time_base = fractions.Fraction(1, fps)
        ctx.framerate = fractions.Fraction(fps, 1)
        ctx.bit_rate = bitrate_kbps * 1000
        ctx.gop_size = fps * 2
        ctx.max_b_frames = 0
        opts = dict(ENCODERS[name][1])
        if name == "libx264":
            opts["vbv-maxrate"] = str(bitrate_kbps)
            opts["vbv-bufsize"] = str(max(1, bitrate_kbps // fps * 2))
        ctx.options = opts
        ctx.open()
        return ctx

    def encode(self, src: av.VideoFrame, force_key):
        frame = src.reformat(width=self.w, height=self.h, format=self.pix_fmt, interpolation="AREA")
        frame.pts = self.pts
        self.pts += 1
        if force_key:
            frame.pict_type = av.video.frame.PictureType.I
        return [(bytes(p), bool(p.is_keyframe)) for p in self.ctx.encode(frame)]


class Client:
    def __init__(self, conn, addr, name, slot_idx):
        self.conn = conn
        self.addr = addr
        self.name = name
        self.slot_idx = slot_idx
        self.cond = threading.Condition()
        self.video_q = collections.deque()
        self.jpeg_latest = None
        self.audio_q = collections.deque(maxlen=40)
        self.need_key = True
        self.alive = True
        self.rtt = 0.0
        self.bytes_sent = 0
        self.connected_at = time.time()


class HostServer:
    def __init__(self, cfg: dict, log):
        """cfg: port, password, mode, codec, height, fps, bitrate, jpeg_quality, audio, game_area_only"""
        self.cfg = cfg
        self.log = log
        self.slots = pcsx2.MULTITAP_MODES[cfg["mode"]]["slots"]
        self.running = False
        self.clients: dict[int, Client] = {}
        self.clients_lock = threading.Lock()
        self.pads = []
        self._notif_refs = []
        self.force_key = True
        self.audio_fmt = None
        self.capture_status = "aguardando"
        self.capture_fps = 0.0
        self._pa = None
        self._astream = None
        self._fails = {}
        self._fail_lock = threading.Lock()
        self._pending = 0

    # ------------------------------------------------------------- ciclo de vida
    def start(self):
        import vgamepad as vg

        self.pads = []
        for i in range(len(self.slots)):
            pad = vg.VX360Gamepad()
            pad.reset()
            pad.update()

            def on_rumble(client, target, large_motor, small_motor, led_number, user_data, _i=i):
                self._send_rumble(_i, large_motor, small_motor)

            pad.register_notification(callback_function=on_rumble)
            self._notif_refs.append(on_rumble)
            self.pads.append(pad)
        self.log(f"{len(self.pads)} controle(s) virtual(is) criado(s).")

        if self.cfg.get("audio"):
            try:
                self._start_audio()
            except Exception as e:
                self.audio_fmt = None
                self.log(f"Áudio desativado: {e}")

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.cfg["port"]))
        self.sock.listen(8)
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        threading.Thread(target=self._capture_loop, daemon=True).start()
        self.log(f"Servidor aberto na porta TCP {self.cfg['port']}.")

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except Exception:
            pass
        with self.clients_lock:
            clients = list(self.clients.values())
        for c in clients:
            self._drop(c)
        if self._astream:
            try:
                self._astream.stop_stream()
                self._astream.close()
            except Exception:
                pass
        if self._pa:
            self._pa.terminate()
        self._astream = self._pa = None
        for pad in self.pads:
            try:
                pad.unregister_notification()
                pad.reset()
                pad.update()
            except Exception:
                pass
        self.pads = []
        self._notif_refs = []
        self.log("Servidor parado.")

    def kick(self, slot_idx):
        with self.clients_lock:
            c = self.clients.get(slot_idx)
        if c:
            self.log(f"{c.name} foi removido da sala.")
            self._drop(c)

    def snapshot(self):
        with self.clients_lock:
            return [
                {"slot_idx": c.slot_idx, "name": c.name, "addr": c.addr[0], "rtt": c.rtt,
                 "bytes": c.bytes_sent, "since": c.connected_at}
                for c in self.clients.values()
            ]

    # ------------------------------------------------------------- áudio
    def _start_audio(self):
        import pyaudiowpatch as pyaudio

        self._pa = pyaudio.PyAudio()
        wasapi = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        dev = self._pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if not dev.get("isLoopbackDevice"):
            for lb in self._pa.get_loopback_device_info_generator():
                if dev["name"] in lb["name"]:
                    dev = lb
                    break
            else:
                raise RuntimeError("dispositivo de loopback não encontrado")
        ch = int(dev["maxInputChannels"])
        rate = int(dev["defaultSampleRate"])
        out_ch = min(2, ch)
        self.audio_fmt = {"rate": rate, "channels": out_ch}

        def cb(in_data, frame_count, time_info, status):
            if ch > 2:
                arr = np.frombuffer(in_data, np.int16).reshape(-1, ch)[:, :2]
                in_data = arr.tobytes()
            self._broadcast_audio(in_data)
            return (None, pyaudio.paContinue)

        self._astream = self._pa.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                                      input_device_index=dev["index"], frames_per_buffer=rate // 100,
                                      stream_callback=cb)
        self._astream.start_stream()
        self.log(f"Capturando áudio de: {dev['name']} ({rate} Hz)")

    def _broadcast_audio(self, data):
        with self.clients_lock:
            clients = list(self.clients.values())
        for c in clients:
            with c.cond:
                c.audio_q.append(data)
                c.cond.notify()

    # ------------------------------------------------------------- rede
    def _accept_loop(self):
        while self.running:
            try:
                sock, addr = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(sock, addr), daemon=True).start()

    def _is_banned(self, ip):
        with self._fail_lock:
            count, until = self._fails.get(ip, (0, 0.0))
            return time.time() < until

    def _register_fail(self, ip):
        with self._fail_lock:
            count, until = self._fails.get(ip, (0, 0.0))
            count += 1
            until = time.time() + BAN_SECONDS if count >= MAX_FAILS else 0.0
            self._fails[ip] = (0 if until else count, until)
            return bool(until)

    def _handle(self, sock, addr):
        conn = Conn(sock)
        client = None
        if self._is_banned(addr[0]) or self._pending >= MAX_PENDING:
            conn.close()
            return
        self._pending += 1
        try:
            sock.settimeout(5)
            try:
                mtype, payload = conn.recv(max_size=2048)   # antes do login: só mensagens pequenas
            finally:
                self._pending -= 1
            if mtype != HELLO:
                self._register_fail(addr[0])
                return
            hello = json.loads(payload.decode("utf-8"))
            if hello.get("version") != VERSION:
                conn.send(REJECT, "Versão diferente do PS2 Online. Usem a mesma versão.".encode())
                return
            if self.cfg["password"] and not hmac.compare_digest(str(hello.get("password", "")).encode(),
                                                               self.cfg["password"].encode()):
                conn.send(REJECT, "Senha incorreta.".encode())
                banned = self._register_fail(addr[0])
                self.log(f"Senha incorreta de {addr[0]}." +
                         (f" IP bloqueado por {BAN_SECONDS // 60} min." if banned else ""))
                return
            name = str(hello.get("name") or "Convidado")[:24]
            with self.clients_lock:
                free = [i for i in range(len(self.slots)) if i not in self.clients]
                if not free:
                    conn.send(REJECT, "A sala está cheia.".encode())
                    return
                client = Client(conn, addr, name, free[0])
                self.clients[client.slot_idx] = client
            sock.settimeout(None)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 256 * 1024)
            slot_name = self.slots[client.slot_idx]
            player_no = client.slot_idx + 2
            conn.send_json(WELCOME, {
                "player": player_no,
                "slot": pcsx2.SLOT_NAMES.get(slot_name, slot_name),
                "audio": self.audio_fmt,
                "codec": "jpeg" if self.cfg["codec"] == "jpeg" else "h264",
            })
            self.force_key = True
            self.log(f"{name} ({addr[0]}) entrou como Jogador {player_no}.")
            threading.Thread(target=self._sender, args=(client,), daemon=True).start()

            pad = self.pads[client.slot_idx]
            while self.running and client.alive:
                mtype, payload = conn.recv(max_size=MAX_INBOUND)
                if mtype == INPUT and len(payload) == PAD.size:
                    b, lt, rt, lx, ly, rx, ry = PAD.unpack(payload)
                    r = pad.report
                    r.wButtons, r.bLeftTrigger, r.bRightTrigger = b, lt, rt
                    r.sThumbLX, r.sThumbLY, r.sThumbRX, r.sThumbRY = lx, ly, rx, ry
                    pad.update()
                elif mtype == PING:
                    conn.send(PONG, payload)
                    if len(payload) == PING_S.size:
                        client.rtt = PING_S.unpack(payload)[1]
                elif mtype == KEYREQ:
                    with client.cond:
                        client.video_q.clear()
                        client.need_key = True
                    self.force_key = True
                elif mtype == BYE:
                    break
        except (OSError, ConnectionError, ValueError, json.JSONDecodeError):
            pass
        finally:
            if client:
                if client.alive:
                    self.log(f"{client.name} saiu.")
                self._drop(client)
            else:
                conn.close()

    def _drop(self, c: Client):
        c.alive = False
        with c.cond:
            c.cond.notify_all()
        with self.clients_lock:
            if self.clients.get(c.slot_idx) is c:
                del self.clients[c.slot_idx]
                if c.slot_idx < len(self.pads):
                    try:
                        self.pads[c.slot_idx].reset()
                        self.pads[c.slot_idx].update()
                    except Exception:
                        pass
        c.conn.close()

    def _sender(self, c: Client):
        try:
            while c.alive and self.running:
                with c.cond:
                    while c.alive and not (c.video_q or c.audio_q or c.jpeg_latest):
                        c.cond.wait(0.5)
                    audio = list(c.audio_q)
                    c.audio_q.clear()
                    vids = list(c.video_q)
                    c.video_q.clear()
                    jpg, c.jpeg_latest = c.jpeg_latest, None
                for a in audio:
                    c.conn.send(AUDIO, a)
                    c.bytes_sent += len(a)
                for data, key in vids:
                    c.conn.send(VIDEO, VIDEO_HDR.pack(CODEC_H264, key) + data)
                    c.bytes_sent += len(data)
                if jpg is not None:
                    c.conn.send(VIDEO, VIDEO_HDR.pack(CODEC_JPEG, 1) + jpg)
                    c.bytes_sent += len(jpg)
        except (OSError, ConnectionError):
            pass
        finally:
            self._drop(c)

    def _send_rumble(self, slot_idx, large, small):
        with self.clients_lock:
            c = self.clients.get(slot_idx)
        if c:
            try:
                c.conn.send(RUMBLE, RUMBLE_S.pack(large & 255, small & 255))
            except Exception:
                pass

    # ------------------------------------------------------------- captura
    def _capture_loop(self):
        fps = self.cfg["fps"]
        interval = 1.0 / fps
        encoder = None
        rect, hwnd, last_find = None, None, 0.0
        frames, fps_t = 0, time.perf_counter()
        max_backlog = max(3, fps // 4)  # ~250 ms de atraso -> descarta e pede keyframe
        with mss.mss() as sct:
            next_t = time.perf_counter()
            while self.running:
                now = time.perf_counter()
                if now - fps_t >= 1.0:
                    self.capture_fps = frames / (now - fps_t)
                    frames, fps_t = 0, now
                with self.clients_lock:
                    clients = list(self.clients.values())
                if not clients:
                    self.capture_status = "sem jogadores conectados"
                    time.sleep(0.1)
                    next_t = time.perf_counter()
                    continue
                if now - last_find > 1.0 or rect is None:
                    rect, hwnd = pcsx2.find_game_area(self.cfg.get("game_area_only", True))
                    last_find = now
                if rect is None:
                    self.capture_status = "janela do PCSX2 não encontrada (ou minimizada)"
                    time.sleep(0.5)
                    continue
                try:
                    shot = np.asarray(sct.grab(rect))   # BGRA
                except Exception:
                    rect = None
                    continue

                src_h, src_w = shot.shape[:2]
                out_h = min(self.cfg["height"], src_h) // 2 * 2
                out_w = max(2, int(round(out_h * src_w / src_h / 2)) * 2)
                img = av.VideoFrame.from_ndarray(np.ascontiguousarray(shot), format="bgra")
                self.capture_status = f"transmitindo {out_w}x{out_h}"

                if self.cfg["codec"] == "jpeg":
                    data = _jpeg(img, out_w, out_h, self.cfg["jpeg_quality"])
                    if data:
                        for c in clients:
                            with c.cond:
                                c.jpeg_latest = data
                                c.cond.notify()
                else:
                    if encoder is None or (encoder.w, encoder.h) != (out_w, out_h):
                        encoder = H264Encoder(self.cfg["codec"], out_w, out_h, fps, self.cfg["bitrate"], self.log)
                        self.log(f"Codificando {out_w}x{out_h} @ {fps} fps com {encoder.name}.")
                        self.force_key = True
                    force, self.force_key = self.force_key, False
                    try:
                        packets = encoder.encode(img, force)
                    except Exception as e:
                        self.log(f"Erro no codificador: {e}")
                        encoder = None
                        continue
                    need_key = False
                    for c in clients:
                        with c.cond:
                            for data, key in packets:
                                if c.need_key:
                                    if not key:
                                        continue
                                    c.need_key = False
                                c.video_q.append((data, key))
                            if len(c.video_q) > max_backlog:
                                c.video_q.clear()
                                c.need_key = True
                            need_key |= c.need_key
                            c.cond.notify()
                    if need_key:
                        self.force_key = True
                frames += 1

                next_t += interval
                delay = next_t - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                elif delay < -interval * 2:
                    next_t = time.perf_counter()
