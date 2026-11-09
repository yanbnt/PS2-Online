"""Teste da chamada de voz: host + 2 convidados no mesmo PC, com microfones simulados."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PySide6.QtCore import QCoreApplication
import pcsx2, voice
import host as hostmod
from guest import GuestClient

voice.Mic.start = lambda self: None          # sem microfone/caixa de som de verdade
voice.Mic.stop = lambda self: None
voice.VoiceMixer.start = lambda self: None
voice.VoiceMixer.stop = lambda self: None
pcsx2.find_game_area = lambda game_area_only=True: ({"left": 0, "top": 0, "width": 640, "height": 480}, None)

app = QCoreApplication([])
logs = []
srv = hostmod.HostServer({"port": 27931, "password": "", "mode": "port1", "codec": "libx264", "height": 480, "fps": 30,
                          "bitrate": 2000, "jpeg_quality": 70, "audio": True, "game_area_only": True,
                          "voice": True, "host_name": "Host"}, logs.append)
host_mix = voice.VoiceMixer()
srv.on_voice = host_mix.push
srv.start()
host_mic = voice.Mic(srv.send_voice)
cfg = {"device": None, "ptt": False, "threshold": -45.0, "volume": 1.0}
g1 = GuestClient("127.0.0.1", 27931, "Primo", "", -2, voice_cfg=cfg)
g2 = GuestClient("127.0.0.1", 27931, "Carlos", "", -2, voice_cfg=cfg)
g1.start(); time.sleep(0.6); g2.start()
t0 = time.time()
while time.time() - t0 < 4 and not (g1.mic and g2.mic and len(srv.snapshot()) == 2):
    app.processEvents(); time.sleep(0.05)
time.sleep(0.5); app.processEvents()

t = np.arange(voice.FRAME) / voice.RATE
fala = (np.sin(2 * np.pi * 300 * t) * 6000).astype(np.int16)
def falar(mic, n=8):
    for _ in range(n):
        mic.process_frame(fala); time.sleep(0.02)
    time.sleep(0.3); app.processEvents()

ok = True
def check(nome, cond):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FALHA") + " " + nome)

check("som do jogo sem eco (só o PCSX2)", any("só o som do PCSX2" in l for l in logs))
falar(g1.mic)
check("host ouve o Primo", host_mix.speaking(1))
check("Carlos ouve o Primo", g2.voice and g2.voice.speaking(1))
check("Primo NÃO recebe a própria voz", g1.voice and not g1.voice.speaking(1))
falar(host_mic)
check("Primo ouve o host", g1.voice.speaking(0))
check("Carlos ouve o host", g2.voice.speaking(0))
falar(g2.mic)
check("Primo ouve o Carlos", g1.voice.speaking(2))
check("lista da chamada no Carlos", g2.roster == {0: "Host", 1: "Primo", 2: "Carlos"})
check("Carlos sabe o próprio número", g2.my_id == 2)
g1.stop(); time.sleep(0.8); app.processEvents()
check("lista atualiza quando o Primo sai", g2.roster == {0: "Host", 2: "Carlos"})
g2.stop(); srv.stop()
print("RESULT:", "OK" if ok else "FAIL")
