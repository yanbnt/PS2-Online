"""Som do jogo: com o PCSX2 aberto PELO app (processo-filho), o som dele precisa chegar aos amigos
e o som do próprio app (a voz da chamada) não."""
import os, runpy, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pcsx2, procloop
import host as hostmod

TONE = Path(sys.argv[1])  # script que toca um seno: tone.py <freq> <segundos>

def analisa(buf):
    a = np.frombuffer(bytes(buf), np.int16).reshape(-1, 2)[:, 0].astype(np.float32)
    if len(a) < 4800:
        return 0, 0
    spec = np.abs(np.fft.rfft(a)); fr = np.fft.rfftfreq(len(a), 1 / 48000); ruido = np.median(spec) + 1e-9
    pico = lambda f: spec[(fr > f - 20) & (fr < f + 20)].max() / ruido
    return pico(1000), pico(3000)

def rodada(modo):
    buf = bytearray()
    jogo = subprocess.Popen([sys.executable, str(TONE), "1000", "3"])      # "PCSX2": filho deste processo
    def voz():
        sys.argv = ["tone.py", "3000", "3"]; runpy.run_path(str(TONE), run_name="__main__")
    if modo == "antigo (tudo menos o app)":
        cap = procloop.ProcessLoopback(os.getpid(), exclude=True, callback=buf.extend); cap.start()
        threading.Thread(target=voz, daemon=True).start(); time.sleep(3.3); cap.stop()
    else:
        pcsx2.find_pids = lambda name="pcsx2": {jogo.pid}
        srv = hostmod.HostServer({"port": 27944, "password": "", "mode": "off", "codec": "libx264", "height": 480,
                                  "fps": 30, "bitrate": 2000, "jpeg_quality": 70, "audio": True,
                                  "game_area_only": True}, lambda m: print("   host:", m))
        srv._broadcast_audio = buf.extend
        srv.start(); threading.Thread(target=voz, daemon=True).start(); time.sleep(3.3); srv.stop()
    jogo.wait()
    j, v = analisa(buf)
    print(f"{modo:28s} jogo (1000 Hz): {j:>9,.0f}x   voz do app (3000 Hz): {v:>7,.0f}x")
    return j, v

# Obs.: com o PCSX2 real aberto pelo app, o modo antigo deu silêncio (-96.7 dBFS) e o novo -26.5 dBFS.
j_new, v_new = rodada("novo (só o PCSX2)")
ok = j_new > 1000 and v_new < j_new / 100
print("RESULT:", "OK" if ok else "FAIL")
