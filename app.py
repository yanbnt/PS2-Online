"""PS2 Online — jogue o multiplayer local do PCSX2 pela internet.

O host roda o PCSX2 normalmente; os convidados recebem a imagem e o som e
controlam os Jogadores 2, 3 e 4 por controles virtuais.
"""
import ipaddress
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSlider, QSpinBox, QStyle,
                               QSystemTrayIcon, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QAbstractItemView)

import pcsx2
import xinput
from protocol import DEFAULT_PORT

APP_NAME = "PS2 Online"

QUALITY_PRESETS = [
    ("Leve — 480p, 30 fps (internet fraca)", 480, 30, 2500),
    ("Padrão — 480p, 60 fps", 480, 60, 5000),
    ("Alta — 720p, 60 fps", 720, 60, 8000),
    ("Máxima — 1080p, 60 fps (só rede local)", 1080, 60, 15000),
]

STYLE = """
QWidget { background: #14161c; color: #e6e8ee; font-size: 10pt; }
QMainWindow, QTabWidget::pane { background: #14161c; }
QLabel, QCheckBox { background: transparent; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #4a5163; border-radius: 4px; background: #0f1116; }
QCheckBox::indicator:hover { border-color: #4c6ef5; }
QCheckBox::indicator:checked { background: #4c6ef5; border-color: #4c6ef5; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QMenu { background: #1c1f27; border: 1px solid #2f3442; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background: #3b5bdb; }
QMenu::item:disabled { color: #8c93a6; }
QMenu::separator { height: 1px; background: #2f3442; margin: 4px 8px; }
QTabWidget::pane { border: 1px solid #2a2e39; border-radius: 8px; top: -1px; }
QTabBar::tab { background: #1c1f27; color: #9aa1b2; padding: 9px 22px; border: 1px solid #2a2e39;
               border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 3px; }
QTabBar::tab:selected { background: #232734; color: #ffffff; }
QGroupBox { border: 1px solid #2a2e39; border-radius: 8px; margin-top: 14px; padding: 10px 10px 8px 10px;
            background: #191c23; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #7fa7ff; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTableWidget {
    background: #0f1116; border: 1px solid #2f3442; border-radius: 6px; padding: 5px 7px;
    selection-background-color: #3b5bdb; }
QComboBox QAbstractItemView { background: #0f1116; border: 1px solid #2f3442; }
QPushButton { background: #262b38; border: 1px solid #343a4a; border-radius: 6px; padding: 7px 14px; }
QPushButton:hover { background: #2f3546; }
QPushButton:disabled { color: #5d6375; background: #1d2029; }
QPushButton#primary { background: #3b5bdb; border-color: #4c6ef5; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #4c6ef5; }
QPushButton#danger { background: #c92a2a; border-color: #e03131; color: white; font-weight: 600; }
QHeaderView::section { background: #1c1f27; color: #9aa1b2; border: none; padding: 6px; }
QLabel#hint { color: #8c93a6; font-weight: normal; }
QLabel#big { font-size: 15pt; font-weight: 700; }
QSlider::groove:horizontal { height: 6px; background: #2f3442; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; border-radius: 8px; background: #4c6ef5; }
"""


def hint(text):
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


def describe_ip(ip: str) -> str:
    a = ipaddress.ip_address(ip)
    if ip.startswith("26."):
        return "Radmin VPN"
    if ip.startswith("25."):
        return "Hamachi"
    if a in ipaddress.ip_network("100.64.0.0/10"):
        return "Tailscale"
    if a.is_private:
        return "rede local / ZeroTier"
    return "internet"


BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def vigem_installed() -> bool:
    import winreg
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\ViGEmBus"))
        return True
    except OSError:
        return False


def vigem_msi():
    import importlib.util
    spec = importlib.util.find_spec("vgamepad")
    if not spec or not spec.submodule_search_locations:
        return None
    arch = "x64" if sys.maxsize > 2 ** 32 else "x86"
    msi = Path(list(spec.submodule_search_locations)[0]) / "win" / "vigem" / "install" / arch / f"ViGEmBusSetup_{arch}.msi"
    return msi if msi.exists() else None


def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254."))


class Bridge(QObject):
    log = Signal(str)
    text = Signal(str)


# =====================================================================  HOST
class HostTab(QWidget):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.s = settings
        self.server = None
        self.bridge = Bridge()
        self.bridge.log.connect(self._append_log)
        self.bridge.text.connect(lambda t: self.public_lbl.setText(t))

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        right = QVBoxLayout()
        root.addLayout(left, 5)
        root.addLayout(right, 4)

        # --- 1. jogo
        g1 = QGroupBox("1 · Jogo")
        f1 = QGridLayout(g1)
        self.exe = QLineEdit(self.s.value("host/exe", pcsx2.DEFAULT_EXE))
        b_exe = QPushButton("…")
        b_exe.setFixedWidth(36)
        b_exe.clicked.connect(self._browse_exe)
        self.games = QComboBox()
        self.games.setMinimumContentsLength(30)
        b_game = QPushButton("Procurar ISO…")
        b_game.clicked.connect(self._browse_game)
        b_ref = QPushButton()
        b_ref.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        b_ref.setFixedWidth(36)
        b_ref.setToolTip("Recarregar a lista de jogos do PCSX2")
        b_ref.clicked.connect(self._refresh_games)
        self.fullscreen = QCheckBox("Abrir em tela cheia")
        self.btn_launch = QPushButton("▶  Abrir jogo no PCSX2")
        self.btn_launch.clicked.connect(self._launch)
        f1.addWidget(QLabel("PCSX2:"), 0, 0)
        f1.addWidget(self.exe, 0, 1, 1, 2)
        f1.addWidget(b_exe, 0, 3)
        f1.addWidget(QLabel("Jogo:"), 1, 0)
        f1.addWidget(self.games, 1, 1)
        f1.addWidget(b_game, 1, 2)
        f1.addWidget(b_ref, 1, 3)
        f1.addWidget(self.fullscreen, 2, 1)
        f1.addWidget(self.btn_launch, 2, 2, 1, 2)
        left.addWidget(g1)

        # --- 2. controles
        g2 = QGroupBox("2 · Controles dos convidados")
        f2 = QFormLayout(g2)
        self.mode = QComboBox()
        for key, m in pcsx2.MULTITAP_MODES.items():
            self.mode.addItem(m["label"], key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.s.value("host/mode", "off"))))
        self.sdl_base = QSpinBox()
        self.sdl_base.setRange(0, 7)
        self.sdl_base.setValue(int(self.s.value("host/sdl_base", 1)))
        b_detect = QPushButton("Detectar")
        b_detect.clicked.connect(self._detect_pads)
        row = QHBoxLayout()
        row.addWidget(self.sdl_base)
        row.addWidget(b_detect)
        row.addStretch()
        self.btn_cfg = QPushButton("⚙  Configurar portas no PCSX2")
        self.btn_cfg.clicked.connect(self._configure_pcsx2)
        f2.addRow("Modo:", self.mode)
        f2.addRow("Nº SDL do 1º convidado:", row)
        f2.addRow(hint("= quantos controles físicos você (host) tem ligados. Com 1 controle seu, use 1. "
                       "Só teclado, use 0."))
        f2.addRow(self.btn_cfg)
        left.addWidget(g2)

        # --- 3. servidor
        g3 = QGroupBox("3 · Sala")
        f3 = QFormLayout(g3)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(self.s.value("host/port", DEFAULT_PORT)))
        self.password = QLineEdit(self.s.value("host/password", ""))
        self.password.setPlaceholderText("opcional")
        self.quality = QComboBox()
        for p in QUALITY_PRESETS:
            self.quality.addItem(p[0])
        self.quality.setCurrentIndex(int(self.s.value("host/quality", 1)))
        self.quality.currentIndexChanged.connect(lambda i: self.bitrate.setValue(QUALITY_PRESETS[i][3]))
        self.codec = QComboBox()
        from host import ENCODERS
        for key, (label, _) in ENCODERS.items():
            self.codec.addItem(label, key)
        self.codec.setCurrentIndex(max(0, self.codec.findData(self.s.value("host/codec", "libx264"))))
        self.bitrate = QSpinBox()
        self.bitrate.setRange(500, 50000)
        self.bitrate.setSingleStep(500)
        self.bitrate.setSuffix(" kbps")
        self.bitrate.setValue(int(self.s.value("host/bitrate", QUALITY_PRESETS[self.quality.currentIndex()][3])))
        self.audio = QCheckBox("Transmitir áudio do PC")
        self.audio.setChecked(self.s.value("host/audio", "true") == "true")
        self.area = QComboBox()
        self.area.addItems(["Só a imagem do jogo", "Janela inteira do PCSX2"])
        f3.addRow("Porta TCP:", self.port)
        f3.addRow("Senha:", self.password)
        f3.addRow("Qualidade:", self.quality)
        f3.addRow("Codificador:", self.codec)
        f3.addRow("Taxa de vídeo:", self.bitrate)
        f3.addRow("Captura:", self.area)
        f3.addRow("", self.audio)
        self.btn_start = QPushButton("Abrir sala")
        self.btn_start.setObjectName("primary")
        self.btn_start.setMinimumHeight(38)
        self.btn_start.clicked.connect(self._toggle_server)
        f3.addRow(self.btn_start)
        left.addWidget(g3)
        left.addStretch()

        # --- direita: endereço, jogadores, log
        g4 = QGroupBox("Endereço para os amigos")
        v4 = QVBoxLayout(g4)
        self.ips_lbl = QLabel()
        self.ips_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ips_lbl.setWordWrap(True)
        self.public_lbl = QLabel("")
        self.public_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        b_pub = QPushButton("Descobrir meu IP público")
        b_pub.clicked.connect(self._public_ip)
        v4.addWidget(self.ips_lbl)
        v4.addWidget(self.public_lbl)
        v4.addWidget(b_pub)
        v4.addWidget(hint("Mais fácil: todos entram na mesma rede do Radmin VPN, ZeroTier ou Tailscale e usam "
                          "o IP dessa rede. Pelo IP público é preciso abrir a porta TCP no roteador."))
        right.addWidget(g4)

        g5 = QGroupBox("Jogadores")
        v5 = QVBoxLayout(g5)
        self.status = QLabel("Sala fechada.")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Jogador", "Nome", "IP", "Ping", "Envio"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(130)
        b_kick = QPushButton("Remover selecionado")
        b_kick.clicked.connect(self._kick)
        v5.addWidget(self.status)
        v5.addWidget(self.table)
        v5.addWidget(b_kick, 0, Qt.AlignRight)
        right.addWidget(g5)

        g6 = QGroupBox("Registro")
        v6 = QVBoxLayout(g6)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        v6.addWidget(self.log)
        right.addWidget(g6, 1)

        self._refresh_games()
        self._update_ips()
        self._prev_bytes = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    # ------------------------------------------------------------- utilitários
    def _append_log(self, msg):
        self.log.appendPlainText(time.strftime("[%H:%M:%S] ") + msg)

    def logf(self, msg):
        self.bridge.log.emit(msg)

    def _update_ips(self):
        ips = local_ips()
        if not ips:
            self.ips_lbl.setText("Nenhum IP encontrado.")
            return
        port = self.port.value()
        self.ips_lbl.setText("<br>".join(f"<b>{ip}</b>:{port} &nbsp;<span style='color:#8c93a6'>"
                                         f"({describe_ip(ip)})</span>" for ip in ips))

    def _public_ip(self):
        self.public_lbl.setText("Consultando…")

        def work():
            try:
                ip = urllib.request.urlopen("https://api.ipify.org", timeout=6).read().decode().strip()
                self.bridge.text.emit(f"IP público: <b>{ip}</b>:{self.port.value()} (precisa abrir a porta no roteador)")
            except Exception as e:
                self.bridge.text.emit(f"Não consegui descobrir: {e}")

        threading.Thread(target=work, daemon=True).start()

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Localizar pcsx2-qt.exe", self.exe.text(), "PCSX2 (*.exe)")
        if path:
            self.exe.setText(path)
            self._refresh_games()

    def _refresh_games(self):
        cur = self.games.currentData() or self.s.value("host/game", "")
        extra = self.s.value("host/extra_games", []) or []
        if isinstance(extra, str):
            extra = [extra]
        games = pcsx2.scan_games(pcsx2.game_folders(self.exe.text()))
        for g in extra:
            if g not in games and Path(g).exists():
                games.append(g)
        self.games.clear()
        self.games.addItem("(abrir só o PCSX2)", "")
        for g in games:
            self.games.addItem(Path(g).stem, g)
        idx = self.games.findData(cur)
        self.games.setCurrentIndex(max(0, idx))

    def _browse_game(self):
        exts = " ".join("*" + e for e in sorted(pcsx2.GAME_EXTS))
        path, _ = QFileDialog.getOpenFileName(self, "Escolher jogo", "", f"Jogos de PS2 ({exts})")
        if path:
            path = str(Path(path))
            extra = self.s.value("host/extra_games", []) or []
            if isinstance(extra, str):
                extra = [extra]
            if path not in extra:
                extra.append(path)
                self.s.setValue("host/extra_games", extra)
            self.s.setValue("host/game", path)
            self._refresh_games()

    def _launch(self):
        exe = self.exe.text()
        if not Path(exe).exists():
            QMessageBox.warning(self, APP_NAME, "Não encontrei o pcsx2-qt.exe nesse caminho.")
            return
        game = self.games.currentData() or None
        self.s.setValue("host/game", game or "")
        pcsx2.launch(exe, game, self.fullscreen.isChecked())
        self.logf(f"Abrindo PCSX2{' com ' + Path(game).stem if game else ''}.")

    def _detect_pads(self):
        n = len(xinput.connected())
        if self.server:
            n = max(0, n - len(self.server.pads))
        self.sdl_base.setValue(n)
        self.logf(f"{n} controle(s) XInput físico(s) detectado(s). Controles PlayStation ligados direto "
                  f"não aparecem aqui — some 1 para cada um.")

    def _configure_pcsx2(self):
        exe = self.exe.text()
        if pcsx2.is_running():
            QMessageBox.warning(self, APP_NAME, "Feche o PCSX2 antes. Ele regrava a configuração ao sair e "
                                                "desfaria a alteração.")
            return
        mode = self.mode.currentData()
        n = len(pcsx2.MULTITAP_MODES[mode]["slots"])
        try:
            ini, backup, done = pcsx2.configure_guest_pads(exe, self.sdl_base.value(), mode, n)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, str(e))
            return
        lines = "\n".join(f"Jogador {i + 2} → porta {pcsx2.SLOT_NAMES[s]} → {d}" for i, (s, d) in enumerate(done))
        self.logf(f"PCSX2 configurado ({ini.name}); backup em {backup.name}.")
        QMessageBox.information(self, APP_NAME, f"Pronto! Portas configuradas:\n\n{lines}\n\n"
                                                f"Backup salvo em:\n{backup}")

    # ------------------------------------------------------------- servidor
    def _toggle_server(self):
        if self.server:
            self.server.stop()
            self.server = None
            self.btn_start.setText("Abrir sala")
            self.btn_start.setObjectName("primary")
            self.btn_start.setStyle(self.btn_start.style())
            self.status.setText("Sala fechada.")
            self.table.setRowCount(0)
            for w in self._locked():
                w.setEnabled(True)
            return
        if not vigem_installed():
            msi = vigem_msi()
            if msi is None:
                QMessageBox.warning(self, APP_NAME, "Para hospedar é preciso o driver ViGEmBus:\n"
                                                    "https://github.com/nefarius/ViGEmBus/releases")
                return
            ans = QMessageBox.question(
                self, APP_NAME,
                "Para hospedar é preciso o driver ViGEmBus (cria os controles virtuais dos convidados).\n\n"
                "Abrir o instalador agora? Depois de instalar, clique em Abrir sala de novo.")
            if ans == QMessageBox.Yes:
                import subprocess
                subprocess.Popen(["msiexec", "/i", str(msi)])
            return

        from host import HostServer

        q = QUALITY_PRESETS[self.quality.currentIndex()]
        cfg = {
            "port": self.port.value(), "password": self.password.text(), "mode": self.mode.currentData(),
            "codec": self.codec.currentData(), "height": q[1], "fps": q[2], "bitrate": self.bitrate.value(),
            "jpeg_quality": 75, "audio": self.audio.isChecked(), "game_area_only": self.area.currentIndex() == 0,
        }
        for k in ("port", "password", "mode", "codec", "bitrate"):
            self.s.setValue(f"host/{k}", cfg[k])
        self.s.setValue("host/quality", self.quality.currentIndex())
        self.s.setValue("host/audio", "true" if cfg["audio"] else "false")
        self.s.setValue("host/sdl_base", self.sdl_base.value())
        self.s.setValue("host/exe", self.exe.text())
        server = HostServer(cfg, self.logf)
        try:
            server.start()
        except Exception as e:
            msg = str(e)
            if "VIGEM" in msg.upper():
                msg += "\n\nInstale o driver ViGEmBus (veja a aba Ajuda)."
            elif isinstance(e, OSError) and getattr(e, "winerror", None) == 10048:
                msg = f"A porta {cfg['port']} já está em uso. Escolha outra."
            QMessageBox.critical(self, APP_NAME, f"Não foi possível abrir a sala:\n{msg}")
            try:
                server.stop()
            except Exception:
                pass
            return
        self.server = server
        self.btn_start.setText("Fechar sala")
        self.btn_start.setObjectName("danger")
        self.btn_start.setStyle(self.btn_start.style())
        for w in self._locked():
            w.setEnabled(False)
        self._update_ips()
        if not pcsx2.is_running():
            self.logf("Dica: abra o jogo no PCSX2 — os convidados verão a janela dele.")

    def _locked(self):
        return [self.port, self.password, self.mode, self.quality, self.codec, self.bitrate, self.audio, self.area,
                self.btn_cfg]

    def _kick(self):
        if not self.server:
            return
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        self.server.kick(item.data(Qt.UserRole))

    def _tick(self):
        if not self.server:
            return
        snap = sorted(self.server.snapshot(), key=lambda c: c["slot_idx"])
        self.table.setRowCount(len(snap))
        for r, c in enumerate(snap):
            prev = self._prev_bytes.get(c["slot_idx"], c["bytes"])
            kbps = max(0, c["bytes"] - prev) * 8 / 1000
            self._prev_bytes[c["slot_idx"]] = c["bytes"]
            slot = self.server.slots[c["slot_idx"]]
            vals = [f"P{c['slot_idx'] + 2} ({pcsx2.SLOT_NAMES[slot]})", c["name"], c["addr"],
                    f"{c['rtt']:.0f} ms", f"{kbps / 1000:.1f} Mbps"]
            for col, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if col == 0:
                    it.setData(Qt.UserRole, c["slot_idx"])
                self.table.setItem(r, col, it)
        total = len(self.server.slots)
        self.status.setText(f"<b>{len(snap)}/{total}</b> convidado(s) · captura: {self.server.capture_status}"
                            + (f" · {self.server.capture_fps:.0f} fps" if snap else ""))

    def shutdown(self):
        if self.server:
            self.server.stop()
            self.server = None


# =====================================================================  CONVIDADO
class VideoView(QWidget):
    def __init__(self):
        super().__init__()
        self.img = None
        self.overlay = ""
        self.show_stats = True
        self.message = "Conectando…"
        self.setAttribute(Qt.WA_OpaquePaintEvent)

    def set_frame(self, img: QImage):
        self.img = img
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), Qt.black)
        if self.img is not None:
            iw, ih = self.img.width(), self.img.height()
            scale = min(self.width() / iw, self.height() / ih)
            w, h = int(iw * scale), int(ih * scale)
            x, y = (self.width() - w) // 2, (self.height() - h) // 2
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawImage(QRect(x, y, w, h), self.img)
        else:
            p.setPen(QColor("#9aa1b2"))
            p.setFont(QFont("Segoe UI", 14))
            p.drawText(self.rect(), Qt.AlignCenter, self.message)
        if self.show_stats and self.overlay:
            p.setFont(QFont("Consolas", 10))
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(self.overlay) + 16
            p.fillRect(8, 8, w, fm.height() + 8, QColor(0, 0, 0, 160))
            p.setPen(QColor("#d0ffd6"))
            p.drawText(16, 8 + 4 + fm.ascent(), self.overlay)
        p.end()


class GameWindow(QWidget):
    closed = Signal()

    def __init__(self, client, title):
        super().__init__()
        self.client = client
        self.setWindowTitle(title)
        self.resize(1024, 768)
        self.view = VideoView()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self.setFocusPolicy(Qt.StrongFocus)
        self.keys = set()
        client.frame.connect(self.view.set_frame)
        client.stats.connect(self._stats)

    def _stats(self, s):
        pad = "teclado" if s.get("pad") is None else f"controle {s['pad'] + 1}"
        self.view.overlay = (f"ping {s['rtt']:.0f} ms · {s['fps']:.0f} fps · "
                             f"{s['kbps'] / 1000:.1f} Mbps · {pad}")
        self.view.update()

    def keyPressEvent(self, e):
        if e.isAutoRepeat():
            return
        k = e.key()
        if k == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif k == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
        elif k == Qt.Key_F1:
            self.view.show_stats = not self.view.show_stats
            self.view.update()
        else:
            self.keys.add(k)
            self.client.set_keys(self.keys)

    def keyReleaseEvent(self, e):
        if e.isAutoRepeat():
            return
        self.keys.discard(e.key())
        self.client.set_keys(self.keys)

    def focusOutEvent(self, e):
        self.keys.clear()
        self.client.set_keys(self.keys)
        super().focusOutEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def closeEvent(self, e):
        self.client.stop()
        self.closed.emit()
        super().closeEvent(e)


class GuestTab(QWidget):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.s = settings
        self.client = None
        self.window = None

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        root.addLayout(top)

        g1 = QGroupBox("Entrar numa sala")
        f1 = QFormLayout(g1)
        self.host = QLineEdit(self.s.value("guest/host", ""))
        self.host.setPlaceholderText("ex.: 26.12.34.56")
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(self.s.value("guest/port", DEFAULT_PORT)))
        self.name = QLineEdit(self.s.value("guest/name", socket.gethostname()[:20]))
        self.password = QLineEdit(self.s.value("guest/password", ""))
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("se o host definiu")
        self.pad = QComboBox()
        self.pad.addItem("Automático (primeiro controle encontrado)", -1)
        for i in range(4):
            self.pad.addItem(f"Controle XInput {i + 1}", i)
        self.pad.addItem("Somente teclado", -2)
        self.pad.setCurrentIndex(max(0, self.pad.findData(int(self.s.value("guest/pad", -1)))))
        self.pads_lbl = hint("")
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 150)
        self.volume.setValue(int(self.s.value("guest/volume", 100)))
        self.volume.valueChanged.connect(self._volume)
        f1.addRow("IP do host:", self.host)
        f1.addRow("Porta:", self.port)
        f1.addRow("Seu nome:", self.name)
        f1.addRow("Senha:", self.password)
        f1.addRow("Controle:", self.pad)
        f1.addRow("", self.pads_lbl)
        f1.addRow("Volume:", self.volume)
        self.btn = QPushButton("Conectar")
        self.btn.setObjectName("primary")
        self.btn.setMinimumHeight(38)
        self.btn.clicked.connect(self._toggle)
        f1.addRow(self.btn)
        top.addWidget(g1, 3)

        g2 = QGroupBox("Status")
        v2 = QVBoxLayout(g2)
        self.status = QLabel("Desconectado.")
        self.status.setObjectName("big")
        self.status.setWordWrap(True)
        self.detail = hint("Peça ao host o IP e a porta que aparecem na aba Hospedar dele.")
        v2.addWidget(self.status)
        v2.addWidget(self.detail)
        v2.addStretch()
        top.addWidget(g2, 2)

        g3 = QGroupBox("Teclado (com a janela do jogo em foco)")
        v3 = QVBoxLayout(g3)
        from guest import KEYBOARD_HELP
        v3.addWidget(hint(KEYBOARD_HELP))
        v3.addWidget(hint("Controle de PlayStation? Use o DS4Windows ou o Steam para ele aparecer como XInput."))
        root.addWidget(g3)
        root.addStretch()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._scan_pads)
        self.timer.start(2000)
        self._scan_pads()

    def _scan_pads(self):
        c = xinput.connected()
        self.pads_lbl.setText("Detectados: " + (", ".join(f"Controle {i + 1}" for i in c) if c else "nenhum"))

    def _volume(self, v):
        self.s.setValue("guest/volume", v)
        if self.client:
            self.client.set_volume(v / 100)

    def _toggle(self):
        if self.client:
            if self.window:
                self.window.close()
            else:
                self.client.stop()
            return
        host = self.host.text().strip()
        if not host:
            QMessageBox.warning(self, APP_NAME, "Digite o IP do host.")
            return
        for k, w in (("host", self.host), ("name", self.name), ("password", self.password)):
            self.s.setValue(f"guest/{k}", w.text())
        self.s.setValue("guest/port", self.port.value())
        self.s.setValue("guest/pad", self.pad.currentData())
        from guest import GuestClient

        self.client = GuestClient(host, self.port.value(), self.name.text().strip() or "Convidado",
                                  self.password.text(), self.pad.currentData(), self.volume.value() / 100)
        self.client.welcome.connect(self._on_welcome)
        self.client.failed.connect(self._on_failed)
        self.client.disconnected.connect(self._on_disconnected)
        self.status.setText("Conectando…")
        self.btn.setText("Cancelar")
        self.btn.setObjectName("danger")
        self.btn.setStyle(self.btn.style())
        self.client.start()

    def _on_welcome(self, info):
        self.status.setText(f"Conectado como Jogador {info['player']}")
        extra = "" if info.get("audio") else " · sem áudio"
        if info.get("audio_error"):
            extra = f" · áudio falhou: {info['audio_error']}"
        self.detail.setText(f"Porta {info['slot']} no PCSX2 do host · vídeo {info['codec'].upper()}{extra}")
        self.btn.setText("Desconectar")
        self.window = GameWindow(self.client, f"{APP_NAME} — Jogador {info['player']}")
        self.window.view.message = "Aguardando a imagem do host…"
        self.window.closed.connect(lambda: setattr(self, "window", None))
        self.window.show()
        self.window.activateWindow()

    def _on_failed(self, msg):
        self._reset()
        self.status.setText("Não conectou")
        self.detail.setText(msg)

    def _on_disconnected(self, reason):
        if self.window:
            w, self.window = self.window, None
            w.close()
        self._reset()
        self.status.setText("Desconectado.")
        self.detail.setText(reason)

    def _reset(self):
        self.client = None
        self.btn.setText("Conectar")
        self.btn.setObjectName("primary")
        self.btn.setStyle(self.btn.style())

    def shutdown(self):
        if self.client:
            self.client.stop()


# =====================================================================  AJUDA
HELP = """
<h2>Como funciona</h2>
<p>O <b>host</b> roda o PCSX2 no PC dele e joga como Jogador 1. O PS2 Online transmite a imagem e o som
para os <b>convidados</b>, e cada convidado vira um controle virtual de Xbox no PC do host
(Jogador 2, 3 ou 4). Para o jogo, é como se todos estivessem no mesmo sofá.</p>

<h2>Host — uma vez só</h2>
<ol>
<li>Instale o driver <b>ViGEmBus</b> (github.com/nefarius/ViGEmBus/releases) — ele cria os controles virtuais.</li>
<li>Feche o PCSX2, escolha o <b>Modo</b> (2 jogadores ou multitap para 4) e o <b>Nº SDL</b>
(quantos controles você mesmo tem ligados) e clique <b>Configurar portas no PCSX2</b>.
É feito backup do PCSX2.ini antes.</li>
<li>Na primeira vez que abrir a sala, o Windows pergunta sobre o firewall: permita em redes
<b>privadas</b> (e públicas, se usar VPN).</li>
</ol>

<h2>Host — para jogar</h2>
<ol>
<li>Clique <b>Abrir sala</b>.</li>
<li>Abra o jogo pelo botão <b>Abrir jogo no PCSX2</b> e deixe a janela dele visível (não minimize).</li>
<li>Passe para os amigos o IP e a porta mostrados.</li>
</ol>

<h2>Convidado</h2>
<ol>
<li>Digite IP, porta e senha do host e clique <b>Conectar</b>.</li>
<li>A janela do jogo abre. <b>F11</b> = tela cheia, <b>F1</b> = estatísticas.</li>
<li>Use um controle XInput (Xbox, ou PlayStation pelo DS4Windows/Steam) ou o teclado.</li>
</ol>

<h2>Conectando pela internet</h2>
<p><b>Mais fácil:</b> todos instalam o <b>Radmin VPN</b>, <b>ZeroTier</b> ou <b>Tailscale</b> e entram na
mesma rede; o convidado usa o IP do host nessa rede. Funciona <b>mesmo com CGNAT</b> e não expõe nada
para a internet. <b>Alternativa:</b> o host libera a porta TCP (padrão 27900) no roteador e passa o IP
público — isso <b>não funciona com CGNAT</b> (se o IP WAN mostrado no roteador for diferente do IP público,
ou começar com 100.64–100.127, é CGNAT).</p>

<h2>Dicas</h2>
<ul>
<li>Travando? Baixe a <b>Qualidade</b> ou a <b>Taxa de vídeo</b>. Placa NVIDIA/AMD/Intel: escolha o codificador
dela para aliviar o processador.</li>
<li>O áudio enviado é o som do PC inteiro do host — se ele usa Discord nas caixas de som, o convidado ouve
eco. Use fone, ou desligue o áudio da sala e usem a chamada.</li>
<li>Jogos para 3–4 jogadores precisam do modo multitap certo (alguns usam a porta 1, outros a 2) —
veja a configuração do jogo.</li>
<li>Ping abaixo de ~60 ms é ótimo; acima de 120 ms jogos de luta ficam difíceis.</li>
</ul>
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)
        self.settings = QSettings("PS2Online", "PS2Online")
        tabs = QTabWidget()
        self.host_tab = HostTab(self.settings)
        self.guest_tab = GuestTab(self.settings)
        help_lbl = QLabel(HELP)
        help_lbl.setWordWrap(True)
        help_lbl.setTextFormat(Qt.RichText)
        help_lbl.setAlignment(Qt.AlignTop)
        help_lbl.setContentsMargins(16, 8, 16, 8)
        tabs.addTab(self.host_tab, "🎮  Hospedar")
        tabs.addTab(self.guest_tab, "🔌  Entrar")
        tabs.addTab(help_lbl, "❓  Ajuda")
        tabs.setCurrentIndex(int(self.settings.value("ui/tab", 0)))
        tabs.currentChanged.connect(lambda i: self.settings.setValue("ui/tab", i))

        header = QWidget()
        hl = QHBoxLayout(header)
        hl.setContentsMargins(4, 0, 4, 4)
        title = QLabel("PS2 <span style='color:#4c6ef5'>Online</span>")
        title.setStyleSheet("font-size: 20pt; font-weight: 800;")
        sub = hint("Multiplayer local do PCSX2 pela internet")
        hl.addWidget(title)
        hl.addWidget(sub, 1, Qt.AlignBottom)
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(14, 10, 14, 14)
        cl.addWidget(header)
        cl.addWidget(tabs, 1)
        self.setCentralWidget(central)

        self._quitting = False
        self._tray_hint_shown = False
        self._build_tray()

    # ------------------------------------------------------------- bandeja do sistema
    def _build_tray(self):
        self.tray = QSystemTrayIcon(QIcon(str(BASE_DIR / "icon.png")), self)
        menu = QMenu()
        menu.addAction("Abrir PS2 Online", self.show_window)
        menu.addSeparator()
        self.act_status = menu.addAction("Sala fechada")
        self.act_status.setEnabled(False)
        self.act_room = menu.addAction("Abrir sala", self._tray_toggle_room)
        menu.addSeparator()
        menu.addAction("Sair do PS2 Online", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._tray_timer = QTimer(self)
        self._tray_timer.timeout.connect(self._update_tray)
        self._tray_timer.start(1000)
        self._update_tray()

    def _busy(self):
        return self.host_tab.server is not None or self.guest_tab.client is not None

    def _update_tray(self):
        srv = self.host_tab.server
        if srv:
            n, total = len(srv.snapshot()), len(srv.slots)
            status = f"Sala aberta · {n}/{total} convidado(s)"
            self.act_room.setText("Fechar sala")
        else:
            status = "Sala fechada"
            self.act_room.setText("Abrir sala")
        if self.guest_tab.client:
            status += " · conectado a " + self.guest_tab.host.text().strip()
        self.act_status.setText(status)
        self.tray.setToolTip(f"{APP_NAME}\n{status}")

    def _tray_toggle_room(self):
        self.host_tab._toggle_server()
        self._update_tray()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self._quitting = True
        self.close()

    def closeEvent(self, e):
        # Com sala aberta ou conectado, o X só esconde a janela: o app continua na bandeja.
        if not self._quitting and self._busy() and self.tray.isVisible():
            e.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.showMessage(APP_NAME, "Continuo rodando aqui na bandeja. Clique com o botão direito "
                                                "no ícone para fechar a sala ou sair.",
                                      QSystemTrayIcon.Information, 4000)
            return
        self.guest_tab.shutdown()
        self.host_tab.shutdown()
        self.tray.hide()
        super().closeEvent(e)
        QApplication.quit()


def selftest(out_path):
    """Diagnóstico: abre host e convidado neste PC por 3 s e grava o resultado em out_path."""
    from PySide6.QtCore import QCoreApplication
    import host as hostmod
    from guest import GuestClient

    lines = []
    app = QCoreApplication(sys.argv)
    pcsx2.find_game_area = lambda game_area_only=True: ({"left": 0, "top": 0, "width": 640, "height": 480}, None)
    before = set(xinput.connected())
    try:
        srv = hostmod.HostServer({"port": 27999, "password": "t", "mode": "off", "codec": "libx264", "height": 480,
                                  "fps": 60, "bitrate": 3000, "jpeg_quality": 70, "audio": True,
                                  "game_area_only": True}, lambda m: lines.append("host: " + m))
        srv.start()
    except Exception as e:
        lines.append(f"FALHA ao abrir sala: {e!r}")
        Path(out_path).write_text("\n".join(lines), encoding="utf-8")
        return 1
    time.sleep(0.4)
    vpad = sorted(set(xinput.connected()) - before)
    res = {"frames": 0}
    g = GuestClient("127.0.0.1", 27999, "teste", "t", pad_index=-2)
    g.frame.connect(lambda img: res.__setitem__("frames", res["frames"] + 1))
    g.welcome.connect(lambda i: lines.append(f"welcome: {i}"))
    g.start()
    QTimer.singleShot(1500, lambda: g.set_keys({Qt.Key.Key_K}))
    QTimer.singleShot(2000, lambda: res.__setitem__("pad", xinput.get_state(vpad[0]) if vpad else None))
    QTimer.singleShot(3000, app.quit)
    app.exec()
    g.stop()
    srv.stop()
    pad_ok = bool(res.get("pad") and res["pad"][0] & xinput.A)
    lines.append(f"frames={res['frames']} pad={res.get('pad')}")
    lines.append("RESULT: " + ("OK" if res["frames"] > 60 and pad_ok else "FAIL"))
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return 0


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(BASE_DIR / "icon.png")))
    app.setQuitOnLastWindowClosed(False)   # quem decide sair é a janela principal / a bandeja
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#14161c"))
    pal.setColor(QPalette.WindowText, QColor("#e6e8ee"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
