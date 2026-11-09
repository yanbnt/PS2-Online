"""Teste ponta-a-ponta: host + convidado no mesmo PC (sem PCSX2: captura um pedaço da tela)."""
import sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
codec = sys.argv[1] if len(sys.argv) > 1 else "libx264"   # libx264, h264_nvenc, h264_qsv, jpeg...

from PySide6.QtCore import QCoreApplication, QTimer, Qt
import pcsx2, xinput
import host as hostmod
from guest import GuestClient

W, H = (int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "800x600").split("x"))
pcsx2.find_game_area = lambda game_area_only=True: ({"left": 0, "top": 0, "width": W, "height": H}, None)

app = QCoreApplication([])
logs = []
before = set(xinput.connected())
srv = hostmod.HostServer({"port": 27911, "password": "abc", "mode": "off", "codec": codec, "height": 480,
                          "fps": 60, "bitrate": 4000, "jpeg_quality": 75, "audio": True,
                          "game_area_only": True}, lambda m: (logs.append(m), print("HOST:", m)))
srv.start()
time.sleep(0.5)
vpad = sorted(set(xinput.connected()) - before)
print("virtual xinput slots:", vpad)

res = {"frames": 0, "size": None, "welcome": None, "fail": None}
g = GuestClient("127.0.0.1", 27911, "Tester", "abc", pad_index=-2)
g.welcome.connect(lambda i: res.__setitem__("welcome", i))
g.failed.connect(lambda m: res.__setitem__("fail", m))
def on_frame(img):
    res["frames"] += 1; res["size"] = (img.width(), img.height())
g.frame.connect(on_frame)
g.stats.connect(lambda s: print("STATS:", {k: round(v, 1) if isinstance(v, float) else v for k, v in s.items()}))
g.start()

def press():
    g.set_keys({Qt.Key.Key_K, Qt.Key.Key_W})
def check():
    st = xinput.get_state(vpad[0]) if vpad else None
    print("virtual pad state while K+W pressed:", st)
    res["pad"] = st
    g.set_keys(set())
QTimer.singleShot(1500, press)
QTimer.singleShot(2000, check)
QTimer.singleShot(3500, app.quit)
app.exec()

print("welcome:", res["welcome"], "fail:", res["fail"])
print("frames:", res["frames"], "size:", res["size"], "snapshot:", srv.snapshot())
# senha errada
bad = {"m": None}
g2 = GuestClient("127.0.0.1", 27911, "X", "errada", pad_index=-2)
g2.failed.connect(lambda m: bad.__setitem__("m", m))
g2.start(); t = time.time()
while bad["m"] is None and time.time() - t < 3:
    app.processEvents(); time.sleep(0.05)
print("wrong password ->", bad["m"])
g.stop(); time.sleep(0.3)
srv.stop()
ok = res["frames"] > 60 and res["pad"] and res["pad"][0] & xinput.A and res["pad"][4] > 30000 and bad["m"]
print("RESULT:", "OK" if ok else "FAIL")
