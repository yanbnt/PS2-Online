"""PS2 Online — jogue o multiplayer local do PCSX2 pela internet.

O host roda o PCSX2 normalmente; os convidados recebem a imagem e o som e
controlam os Jogadores 2, 3 e 4 por controles virtuais.
"""
import getpass
import html
import ipaddress
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QObject, QPropertyAnimation, QRect, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QIntValidator, QPainter, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QGraphicsOpacityEffect,
                               QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QStyle,
                               QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget)

import invite
import pcsx2
import upnp
import voice
import xinput
from protocol import DEFAULT_PORT
from widgets import (ACCENT, BAD, MUTED, OK, WARN, AnimButton, Card, FadeStack, GamepadView, PasswordEdit,
                     PulseDot, Sidebar, Spinner, StatusIcon, Toast, field)

APP_NAME = "PS2 Online"
APP_VERSION = "1.3.1"
APPROVAL_TIMEOUT = 90
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

QUALITY_PRESETS = [
    ("Leve — 480p, 30 fps (internet fraca)", 480, 30, 2500),
    ("Padrão — 480p, 60 fps", 480, 60, 5000),
    ("Alta — 720p, 60 fps", 720, 60, 8000),
    ("Máxima — 1080p, 60 fps (só rede local)", 1080, 60, 15000),
]

STYLE = """
* { font-family: 'Segoe UI'; }
QWidget { background: transparent; color: #e6e8ee; font-size: 10pt; }
QMainWindow, #root { background: #0f1116; }
#content { background: #12141b; }
#sidebar { background: #0b0d12; border-right: 1px solid #1f232d; }
#navind { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #4c6ef5, stop:1 #7950f2); border-radius: 2px; }
QPushButton#nav { text-align: left; padding: 11px 14px; border: none; border-radius: 10px; color: #9aa1b2;
                  font-size: 10.5pt; font-weight: 600; background: transparent; }
QPushButton#nav:hover { background: #171a23; color: #e6e8ee; }
QPushButton#nav:checked { background: #1a1f2e; color: #ffffff; }
#card { background: #181b24; border: 1px solid #242936; border-radius: 14px; }
QLabel#cardtitle { font-size: 12pt; font-weight: 700; color: #ffffff; }
QLabel#step { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #4c6ef5, stop:1 #7950f2); color: white;
              border-radius: 13px; font-weight: 800; }
QLabel#pagetitle { font-size: 20pt; font-weight: 800; color: #ffffff; }
QLabel#pagesub { color: #8c93a6; font-size: 10.5pt; }
QLabel#flabel { color: #9aa1b2; font-size: 9pt; font-weight: 600; letter-spacing: 0.3px; }
QLabel#hint { color: #8c93a6; font-size: 9pt; }
QLabel#big { font-size: 13pt; font-weight: 700; }
QLabel#code { font-family: Consolas; font-size: 13pt; color: #d0ffd6; background: #0d1015;
              border: 1px dashed #2f3a52; border-radius: 10px; padding: 12px; }
QLabel#toast { background: #1d2130; color: #ffffff; border-radius: 10px; padding: 10px 18px; font-weight: 600;
               border: 1px solid #2f3546; }
QLabel#pill { background: #171a23; border: 1px solid #242936; border-radius: 12px; padding: 6px 10px; color: #c5cad6; }
QLineEdit, QComboBox, QSpinBox {
    background: #0f1218; border: 1.5px solid #262b38; border-radius: 10px; padding: 8px 12px; min-height: 22px;
    selection-background-color: #3b5bdb; }
QLineEdit:hover, QComboBox:hover, QSpinBox:hover { border-color: #3a4152; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #4c6ef5; background: #111624; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled { color: #5d6375; background: #13151b; }
QLineEdit#invite { font-family: Consolas; font-size: 12.5pt; padding: 12px 14px; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: #141720; border: 1px solid #2f3442; border-radius: 8px; padding: 4px;
                              selection-background-color: #3b5bdb; outline: none; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QPlainTextEdit { background: #0d1015; border: 1px solid #222632; border-radius: 10px; padding: 6px;
                 font-family: Consolas; font-size: 9pt; color: #b7bdcc; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1.5px solid #4a5163; border-radius: 5px; background: #0f1218; }
QCheckBox::indicator:hover { border-color: #4c6ef5; }
QCheckBox::indicator:checked { background: #4c6ef5; border-color: #4c6ef5; }
QCheckBox::indicator:checked:disabled { background: #2f3a5c; border-color: #2f3a5c; }
QCheckBox:disabled { color: #6b7285; }
QToolButton#expander { border: none; color: #9aa1b2; font-weight: 600; padding: 4px 0; }
QToolButton#expander:hover { color: #ffffff; }
QPushButton#mini { background: #232734; border: 1px solid #2f3546; border-radius: 8px; padding: 5px 10px; }
QPushButton#mini:hover { background: #2e3445; }
QMenu { background: #1c1f27; border: 1px solid #2f3442; padding: 4px; border-radius: 8px; }
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: #3b5bdb; }
QMenu::item:disabled { color: #8c93a6; }
QMenu::separator { height: 1px; background: #2f3442; margin: 4px 8px; }
QSlider::groove:horizontal { height: 6px; background: #262b38; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #4c6ef5; border-radius: 3px; }
QSlider::handle:horizontal { width: 18px; margin: -7px 0; border-radius: 9px; background: #ffffff; }
QScrollArea { border: none; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #2a2f3d; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QToolTip { background: #1d2130; color: #e6e8ee; border: 1px solid #2f3546; padding: 6px; }
QMessageBox { background: #181b24; }
QMessageBox QPushButton { background: #262b38; border: 1px solid #343a4a; border-radius: 8px; padding: 7px 16px; min-width: 80px; }
QMessageBox QPushButton:hover { background: #3b5bdb; }
"""


# ============================================================================== utilitários
def hint(text):
    lab = QLabel(text)
    lab.setObjectName("hint")
    lab.setWordWrap(True)
    return lab


def page_header(title, sub):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 6)
    v.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("pagetitle")
    s = QLabel(sub)
    s.setObjectName("pagesub")
    s.setWordWrap(True)
    v.addWidget(t)
    v.addWidget(s)
    return w


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


class NumberEdit(QLineEdit):
    """Campo numérico com o mesmo visual dos outros campos (o QSpinBox estilizado some com o texto)."""
    valueChanged = Signal(int)

    def __init__(self, lo, hi, value):
        super().__init__(str(value))
        self.lo, self.hi = lo, hi
        self.setValidator(QIntValidator(lo, hi, self))
        self.textChanged.connect(self._changed)
        self.editingFinished.connect(lambda: self.setText(str(self.value())))

    def value(self) -> int:
        try:
            return max(self.lo, min(self.hi, int(self.text())))
        except ValueError:
            return self.lo

    def setValue(self, v):
        self.setText(str(max(self.lo, min(self.hi, int(v)))))

    def _changed(self, text):
        if text.isdigit() and self.lo <= int(text) <= self.hi:
            self.valueChanged.emit(int(text))


def spin(lo, hi, value, step=1, suffix=""):
    return NumberEdit(lo, hi, value)


def scrollable(widget):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(widget)
    return sa


class Bridge(QObject):
    log = Signal(str)
    wan = Signal(str)
    approve = Signal(object)
    pcsx2_closed = Signal(bool)


# ============================================================================== AVANÇADO
class AdvancedPage(QWidget):
    def __init__(self, main, settings):
        super().__init__()
        self.main = main
        self.s = settings
        self.logf = lambda m: None
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addWidget(page_header("Avançado", "Ajustes técnicos. O padrão já funciona para a maioria dos casos."))

        # PCSX2 e controles
        c1 = Card("PCSX2 e controles dos convidados")
        self.exe = QLineEdit(self.s.value("host/exe", pcsx2.DEFAULT_EXE))
        b_exe = QPushButton("Procurar…")
        b_exe.setObjectName("mini")
        b_exe.clicked.connect(self._browse_exe)
        row = QHBoxLayout()
        row.addWidget(self.exe, 1)
        row.addWidget(b_exe)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        c1.body.addWidget(field("Executável do PCSX2", w))
        self.mode = QComboBox()
        for key, m in pcsx2.MULTITAP_MODES.items():
            self.mode.addItem(m["label"], key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.s.value("host/mode", "off"))))
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setAlignment(Qt.AlignTop)
        g.addWidget(field("Jogadores", self.mode), 0, 0, Qt.AlignTop)
        self.map_lbl = QLabel()
        self.map_lbl.setWordWrap(True)
        g.addWidget(field("Ligação dos controles (automática)", self.map_lbl,
                          "O app descobre qual controle é o seu e qual é o de cada amigo, e ajusta o PCSX2."),
                    0, 1, Qt.AlignTop)
        c1.body.addLayout(g)
        st_row = QHBoxLayout()
        self.pad_icon = StatusIcon()
        self.pad_status = QLabel()
        self.pad_status.setWordWrap(True)
        self.btn_cfg = AnimButton("⚙  Configurar portas no PCSX2", "ghost", height=36)
        self.btn_cfg.clicked.connect(lambda: self.configure_pcsx2())
        st_row.addWidget(self.pad_icon)
        st_row.addWidget(self.pad_status, 1)
        st_row.addWidget(self.btn_cfg)
        c1.body.addLayout(st_row)
        root.addWidget(c1)

        # Transmissão
        c2 = Card("Transmissão")
        from host import ENCODERS
        self.quality = QComboBox()
        for p in QUALITY_PRESETS:
            self.quality.addItem(p[0])
        self.quality.setCurrentIndex(int(self.s.value("host/quality", 1)))
        self.codec = QComboBox()
        for key, (label, _) in ENCODERS.items():
            self.codec.addItem(label, key)
        self.codec.setCurrentIndex(max(0, self.codec.findData(self.s.value("host/codec", "libx264"))))
        self.bitrate = spin(500, 50000, int(self.s.value("host/bitrate", QUALITY_PRESETS[self.quality.currentIndex()][3])),
                            500, " kbps")
        self.quality.currentIndexChanged.connect(lambda i: self.bitrate.setValue(QUALITY_PRESETS[i][3]))
        self.area = QComboBox()
        self.area.addItems(["Só a imagem do jogo", "Janela inteira do PCSX2"])
        self.audio = QCheckBox("Transmitir o áudio do PC")
        self.audio.setChecked(self.s.value("host/audio", "true") == "true")
        g2 = QGridLayout()
        g2.setHorizontalSpacing(14)
        g2.setVerticalSpacing(12)
        g2.addWidget(field("Qualidade", self.quality), 0, 0)
        g2.addWidget(field("Codificador de vídeo", self.codec), 0, 1)
        g2.addWidget(field("Taxa de vídeo (kbps)", self.bitrate), 1, 0)
        g2.addWidget(field("Captura", self.area), 1, 1)
        c2.body.addLayout(g2)
        c2.body.addWidget(self.audio)
        root.addWidget(c2)

        # Rede
        c3 = Card("Rede")
        self.port = spin(1024, 65535, int(self.s.value("host/port", DEFAULT_PORT)))
        self.upnp_cb = QCheckBox("Abrir a porta no roteador automaticamente (UPnP) e fechar ao sair")
        self.upnp_cb.setChecked(self.s.value("host/upnp", "true") == "true")
        c3.body.addWidget(field("Porta TCP", self.port))
        c3.body.addWidget(self.upnp_cb)
        root.addWidget(c3)

        # Voz
        c4 = Card("Chamada de voz")
        self.voice_cb = QCheckBox("Ativar chamada de voz (falar com os amigos e ouvir eles junto com o jogo)")
        self.voice_cb.setChecked(self.s.value("voice/on", "true") == "true")
        c4.body.addWidget(self.voice_cb)
        self.mic_combo = QComboBox()
        self.mic_combo.addItem("Microfone padrão do Windows", None)
        try:
            for idx, name in voice.input_devices():
                self.mic_combo.addItem(name, idx)
        except Exception:
            pass
        saved_mic = self.s.value("voice/mic_name", "")
        i = self.mic_combo.findText(saved_mic) if saved_mic else -1
        self.mic_combo.setCurrentIndex(max(0, i))
        self.voice_mode = QComboBox()
        self.voice_mode.addItem("Falar automaticamente (detecta a sua voz)", False)
        self.voice_mode.addItem("Apertar uma tecla para falar", True)
        self.voice_mode.setCurrentIndex(1 if self.s.value("voice/ptt", "false") == "true" else 0)
        self.ptt_key = QComboBox()
        for name in voice.PTT_KEYS:
            self.ptt_key.addItem(name)
        self.ptt_key.setCurrentIndex(max(0, self.ptt_key.findText(self.s.value("voice/ptt_key", "CapsLock"))))
        self.sens = QSlider(Qt.Horizontal)
        self.sens.setRange(0, 100)
        self.sens.setValue(int(self.s.value("voice/sens", 50)))
        self.voice_vol = QSlider(Qt.Horizontal)
        self.voice_vol.setRange(0, 200)
        self.voice_vol.setValue(int(self.s.value("voice/volume", 100)))
        g4 = QGridLayout()
        g4.setHorizontalSpacing(14)
        g4.setVerticalSpacing(12)
        g4.addWidget(field("Microfone", self.mic_combo), 0, 0)
        g4.addWidget(field("Modo", self.voice_mode), 0, 1)
        g4.addWidget(field("Sensibilidade do microfone", self.sens, "Mais para a direita = capta voz mais baixa."), 1, 0)
        g4.addWidget(field("Tecla para falar", self.ptt_key, "Funciona mesmo com o jogo em foco."), 1, 1)
        g4.addWidget(field("Volume das vozes", self.voice_vol), 2, 0)
        c4.body.addLayout(g4)
        c4.body.addWidget(hint("<b>F9</b> liga/desliga o seu microfone a qualquer momento. Use fone de ouvido: "
                               "sem fone, o microfone capta o som da caixa e os amigos ouvem eco."))
        root.addWidget(c4)
        self.voice_cb.toggled.connect(lambda *_: self.save_voice())
        for w in (self.voice_mode, self.ptt_key, self.mic_combo):
            w.currentIndexChanged.connect(lambda *_: self.save_voice())
        for w in (self.sens, self.voice_vol):
            w.valueChanged.connect(lambda *_: self.save_voice())
        root.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scrollable(inner))
        self.mode.currentIndexChanged.connect(lambda _: self.update_pad_status())
        self.exe.editingFinished.connect(self.update_pad_status)
        self.update_pad_status()

    def save(self):
        s = self.s
        s.setValue("host/exe", self.exe.text())
        s.setValue("host/mode", self.mode.currentData())
        s.setValue("host/quality", self.quality.currentIndex())
        s.setValue("host/codec", self.codec.currentData())
        s.setValue("host/bitrate", self.bitrate.value())
        s.setValue("host/audio", "true" if self.audio.isChecked() else "false")
        s.setValue("host/port", self.port.value())
        s.setValue("host/upnp", "true" if self.upnp_cb.isChecked() else "false")

    def save_voice(self):
        s = self.s
        s.setValue("voice/on", "true" if self.voice_cb.isChecked() else "false")
        s.setValue("voice/mic_name", self.mic_combo.currentText() if self.mic_combo.currentIndex() > 0 else "")
        s.setValue("voice/ptt", "true" if self.voice_mode.currentData() else "false")
        s.setValue("voice/ptt_key", self.ptt_key.currentText())
        s.setValue("voice/sens", self.sens.value())
        s.setValue("voice/volume", self.voice_vol.value())

    def voice_cfg(self):
        """Configuração da voz para a chamada, ou None se a voz estiver desligada."""
        if not self.voice_cb.isChecked():
            return None
        return {"device": self.mic_combo.currentData(), "ptt": bool(self.voice_mode.currentData()),
                "ptt_key": voice.PTT_KEYS[self.ptt_key.currentText()],
                "threshold": -25.0 - self.sens.value() * 0.4, "volume": self.voice_vol.value() / 100}

    def locked_widgets(self):
        return [self.port, self.mode, self.quality, self.codec, self.bitrate, self.audio, self.area, self.upnp_cb,
                self.btn_cfg, self.voice_cb, self.mic_combo]

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "Localizar pcsx2-qt.exe", self.exe.text(), "PCSX2 (*.exe)")
        if path:
            self.exe.setText(str(Path(path)))
            self.save()
            self.update_pad_status()
            self.main.host.refresh_games()

    def expected_devices(self):
        """(controle do host, [controles dos convidados], exato?) no formato do PCSX2 ('SDL-N').

        O PCSX2 chama de SDL-N o controle XInput N. Com a sala aberta sabemos exatamente onde os controles
        virtuais ficaram; com a sala fechada é uma previsão (as próximas posições livres).
        """
        n = len(pcsx2.MULTITAP_MODES[self.mode.currentData()]["slots"])
        host = getattr(self.main, "host", None)
        srv = host.server if host else None
        connected = xinput.connected()
        virt = list(srv.virtual_slots)[:n] if srv and srv.virtual_slots else []
        exact = bool(virt)
        phys = [i for i in connected if i not in virt]
        if len(virt) < n:
            free = [i for i in range(4) if i not in connected and i not in virt]
            virt += free[: n - len(virt)]
        host_dev = f"SDL-{phys[0]}" if phys else None
        return host_dev, [f"SDL-{v}" for v in virt], exact

    def pad_problems(self):
        try:
            host_dev, guests, _ = self.expected_devices()
            return pcsx2.check_guest_pads(self.exe.text(), self.mode.currentData(), guests, host_dev)
        except Exception as e:
            return [f"não consegui ler a configuração do PCSX2 ({e})"]

    def update_pad_status(self):
        host_dev, guests, exact = self.expected_devices()
        you = f"<b>você</b> → {host_dev}" if host_dev else "<b>você</b> → (nenhum controle ligado agora)"
        friends = " · ".join(f"<b>Jogador {i + 2}</b> → {d}" for i, d in enumerate(guests))
        self.map_lbl.setText(f"{you} · {friends}" + ("" if exact else "<br><i>previsão — confirmada ao abrir a sala</i>"))
        problems = self.pad_problems()
        if problems:
            self.pad_icon.set("warn")
            self.pad_status.setText("Controles dos convidados <b>não configurados</b> no PCSX2.")
            self.pad_status.setToolTip("\n".join(problems))
        else:
            self.pad_icon.set("ok")
            self.pad_status.setText("PCSX2 pronto para os convidados.")
            self.pad_status.setToolTip("")
        return problems

    def configure_pcsx2(self, quiet=False) -> bool:
        if pcsx2.is_running():
            QMessageBox.warning(self, APP_NAME, "Feche o PCSX2 antes. Ele regrava a configuração ao sair e "
                                                "desfaria a alteração.")
            return False
        mode = self.mode.currentData()
        host_dev, guests, _ = self.expected_devices()
        try:
            ini, backup, done = pcsx2.configure_guest_pads(self.exe.text(), mode, guests, host_dev)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, str(e))
            return False
        self.save()
        self.logf(f"PCSX2 configurado ({ini.name}); backup em {backup.name}.")
        self.update_pad_status()
        names = {"Pad1": "você"}
        resumo = " · ".join(f"{names.get(sl, 'Jogador ' + str(i + (1 if done[0][0] == 'Pad1' else 2)))} = {d}"
                            for i, (sl, d) in enumerate(done))
        self.main.toast(f"Controles ajustados no PCSX2: {resumo}", "ok")
        if not quiet:
            lines = "\n".join(("Jogador 1 (você)" if sl == "Pad1" else f"Porta {pcsx2.SLOT_NAMES[sl]}") + f" → {d}"
                              for sl, d in done)
            QMessageBox.information(self, APP_NAME, f"Portas configuradas:\n\n{lines}\n\nBackup em:\n{backup}")
        return True


# ============================================================================== VOZ (barra lateral)
class LevelMeter(QWidget):
    def __init__(self):
        super().__init__()
        self.level = 0.0
        self.active = False
        self.setFixedHeight(6)

    def set(self, level, active):
        level = round(level, 2)
        if (level, active) != (self.level, self.active):
            self.level, self.active = level, active
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#262b38"))
        p.drawRoundedRect(self.rect(), 3, 3)
        w = int(self.width() * self.level)
        if w > 0:
            p.setBrush(QColor(OK if self.active else "#4a5163"))
            p.drawRoundedRect(QRect(0, 0, w, self.height()), 3, 3)


class VoiceBar(QFrame):
    """Mostra o estado do seu microfone na barra lateral, durante uma chamada."""

    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setStyleSheet("#card { background: #141823; border: 1px solid #242936; border-radius: 12px; }")
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 10)
        v.setSpacing(6)
        top = QHBoxLayout()
        self.btn = QPushButton("🎤")
        self.btn.setObjectName("mini")
        self.btn.setFixedWidth(40)
        self.btn.setToolTip("Mutar / desmutar (F9)")
        self.lbl = QLabel("Chamada de voz")
        self.lbl.setStyleSheet("font-size: 9pt; font-weight: 600;")
        self.lbl.setWordWrap(True)
        top.addWidget(self.btn)
        top.addWidget(self.lbl, 1)
        v.addLayout(top)
        self.meter = LevelMeter()
        v.addWidget(self.meter)
        self.hide()


# ============================================================================== HOSPEDAR
class PlayerRow(QFrame):
    def __init__(self, slot_idx, name, kick_cb):
        super().__init__()
        self.setObjectName("card")
        self.setStyleSheet("#card { background: #1d2130; border-radius: 12px; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        hue = (sum(map(ord, name)) * 47) % 360
        av = QLabel((name[:1] or "?").upper())
        av.setFixedSize(40, 40)
        av.setAlignment(Qt.AlignCenter)
        self._av_style = f"background: hsl({hue}, 60%, 45%); border-radius: 20px; font-weight: 800; font-size: 13pt;"
        av.setStyleSheet(self._av_style + "border: 3px solid transparent;")
        self.av = av
        self._speaking = False
        lay.addWidget(av)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.name = QLabel(f"<b>{html.escape(name)}</b>")
        self.sub = QLabel(f"Jogador {slot_idx + 2}")
        self.sub.setObjectName("hint")
        col.addWidget(self.name)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.ping = QLabel("— ms")
        self.ping.setStyleSheet("font-weight: 700;")
        lay.addWidget(self.ping)
        kick = QPushButton("Remover")
        kick.setObjectName("mini")
        kick.clicked.connect(lambda: kick_cb(slot_idx))
        lay.addWidget(kick)

    def set_speaking(self, on):
        if on != self._speaking:
            self._speaking = on
            self.av.setStyleSheet(self._av_style + ("border: 3px solid #51cf66;" if on else "border: 3px solid transparent;"))

    def update_stats(self, rtt, mbps, slot_label):
        c = OK if rtt < 60 else WARN if rtt < 120 else BAD
        self.ping.setText(f"<span style='color:{c}'>●</span> {rtt:.0f} ms")
        self.sub.setText(f"{slot_label} · {mbps:.1f} Mbps")


class HostPage(QWidget):
    def __init__(self, main, adv, settings):
        super().__init__()
        self.main = main
        self.adv = adv
        self.s = settings
        self.server = None
        self.wan_ip = None
        self.own_invites = set()
        self.rows = {}
        self._prev_bytes = {}
        self.bridge = Bridge()
        self.bridge.log.connect(self._append_log)
        self.bridge.wan.connect(self._on_wan)
        self.bridge.approve.connect(self._ask_approval)
        self.bridge.pcsx2_closed.connect(self._after_pcsx2_closed)
        self.mic = None
        self.voice_mix = None
        self._pad_warned = None
        self._pad_fixing = False
        adv.logf = self.logf

        inner = QWidget()
        outer = QVBoxLayout(inner)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)
        outer.addWidget(page_header("Hospedar partida", "Três passos: escolha o jogo, abra a sala e mande o convite."))
        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        right = QVBoxLayout()
        right.setSpacing(16)
        cols.addLayout(left, 11)
        cols.addLayout(right, 9)
        outer.addLayout(cols, 1)

        # 1 · Jogo
        c1 = Card("Escolha o jogo", step=1)
        self.games = QComboBox()
        self.games.setMinimumContentsLength(24)
        b_iso = QPushButton("Procurar ISO…")
        b_iso.setObjectName("mini")
        b_iso.clicked.connect(self._browse_game)
        b_ref = QPushButton()
        b_ref.setObjectName("mini")
        b_ref.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        b_ref.setToolTip("Recarregar a lista de jogos do PCSX2")
        b_ref.clicked.connect(self.refresh_games)
        r = QHBoxLayout()
        r.addWidget(self.games, 1)
        r.addWidget(b_iso)
        r.addWidget(b_ref)
        c1.body.addLayout(r)
        r2 = QHBoxLayout()
        self.fullscreen = QCheckBox("Abrir em tela cheia")
        self.btn_launch = AnimButton("▶  Abrir jogo no PCSX2", "ghost")
        self.btn_launch.clicked.connect(self._launch)
        r2.addWidget(self.fullscreen)
        r2.addStretch()
        r2.addWidget(self.btn_launch)
        c1.body.addLayout(r2)
        left.addWidget(c1)

        # 2 · Sala
        c2 = Card("Abra a sala", step=2)
        self.password = PasswordEdit(self.s.value("host/password", ""), "deixe vazio para sala sem senha")
        self.password.textChanged.connect(self._update_invite)
        c2.body.addWidget(field("Senha da sala (opcional)", self.password))
        self.approve_cb = QCheckBox("Pedir minha aprovação antes de cada jogador entrar")
        self.approve_cb.setChecked(self.s.value("host/approve", "true") == "true")
        c2.body.addWidget(self.approve_cb)
        r3 = QHBoxLayout()
        self.dot = PulseDot(MUTED)
        self.room_lbl = QLabel("Sala fechada")
        self.room_lbl.setObjectName("big")
        self.btn_room = AnimButton("Abrir sala", "primary", height=44)
        self.btn_room.setMinimumWidth(170)
        self.btn_room.clicked.connect(self.toggle_server)
        r3.addWidget(self.dot)
        r3.addWidget(self.room_lbl, 1)
        r3.addWidget(self.btn_room)
        c2.body.addLayout(r3)
        self.room_sub = hint("")
        c2.body.addWidget(self.room_sub)
        # aviso quando os controles do PCSX2 estão trocados (aparece só quando precisa)
        self.pad_banner = QFrame()
        self.pad_banner.setStyleSheet("QFrame { background: rgba(252,196,25,0.10); border: 1px solid rgba(252,196,25,0.45);"
                                      " border-radius: 10px; }")
        pb = QHBoxLayout(self.pad_banner)
        pb.setContentsMargins(12, 8, 8, 8)
        self.pad_banner_lbl = QLabel()
        self.pad_banner_lbl.setWordWrap(True)
        self.pad_banner_lbl.setStyleSheet("border: none; background: transparent;")
        self.btn_fix_pads = AnimButton("Corrigir agora", "ghost", height=34)
        self.btn_fix_pads.clicked.connect(self.fix_pads_restart)
        pb.addWidget(self.pad_banner_lbl, 1)
        pb.addWidget(self.btn_fix_pads)
        self.pad_banner.hide()
        c2.body.addWidget(self.pad_banner)
        left.addWidget(c2)

        # 3 · Convite
        c3 = Card("Convide seus amigos", step=3)
        self.code = QLabel("—")
        self.code.setObjectName("code")
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.code.setWordWrap(True)
        c3.body.addWidget(self.code)
        r4 = QHBoxLayout()
        self.addr = QComboBox()
        self._addr_chosen = False   # vira True quando o usuário escolhe um endereço na mão
        self.addr.currentIndexChanged.connect(self._update_invite)
        self.addr.activated.connect(lambda _: setattr(self, "_addr_chosen", True))
        self.btn_copy = AnimButton("📋  Copiar convite", "primary")
        self.btn_copy.setMinimumWidth(170)
        self.btn_copy.clicked.connect(self.copy_invite)
        r4.addWidget(field("Endereço usado no convite", self.addr), 1)
        r4.addWidget(self.btn_copy, 0, Qt.AlignBottom)
        c3.body.addLayout(r4)
        self.addr_hint = hint("Mande o convite pelo WhatsApp/Discord. Ele leva IP, porta e senha — só mande para "
                              "quem você quer que entre.")
        c3.body.addWidget(self.addr_hint)
        left.addWidget(c3)
        left.addStretch()

        # Jogadores
        c4 = Card("Jogadores")
        self.players_box = QVBoxLayout()
        self.players_box.setSpacing(8)
        self.empty = QLabel("Ninguém conectado ainda.\nMande o convite para os amigos! 🎮")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName("hint")
        self.empty.setMinimumHeight(90)
        self.players_box.addWidget(self.empty)
        c4.body.addLayout(self.players_box)
        self.cap_lbl = hint("")
        c4.body.addWidget(self.cap_lbl)
        right.addWidget(c4)

        c5 = Card("Atividade")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(400)
        self.log.setMinimumHeight(160)
        c5.body.addWidget(self.log)
        right.addWidget(c5, 1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scrollable(inner))

        self.refresh_games()
        self._rebuild_addresses()
        threading.Thread(target=self._discover_wan, daemon=True).start()
        self.adv.port.valueChanged.connect(lambda _: self._rebuild_addresses())
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self.talk_timer = QTimer(self)
        self.talk_timer.timeout.connect(self._talk_tick)
        self.talk_timer.start(100)
        self._set_room_ui()

    # ------------------------------------------------------------- log
    def _append_log(self, msg):
        self.log.appendPlainText(time.strftime("[%H:%M:%S] ") + msg)
        if " entrou como " in msg:
            self.main.toast(msg.split(" (")[0] + " entrou na sala 🎉", "ok")
        elif msg.endswith(" saiu."):
            self.main.toast(msg, "warn")

    def logf(self, msg):
        self.bridge.log.emit(msg)

    # ------------------------------------------------------------- jogos
    def refresh_games(self):
        cur = self.games.currentData() or self.s.value("host/game", "")
        extra = self.s.value("host/extra_games", []) or []
        if isinstance(extra, str):
            extra = [extra]
        games = pcsx2.scan_games(pcsx2.game_folders(self.adv.exe.text()))
        for g in extra:
            if g not in games and Path(g).exists():
                games.append(g)
        self.games.clear()
        self.games.addItem("(abrir só o PCSX2)", "")
        for g in games:
            self.games.addItem(Path(g).stem, g)
        self.games.setCurrentIndex(max(0, self.games.findData(cur)))

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
            self.refresh_games()

    def _launch(self):
        exe = self.adv.exe.text()
        if not Path(exe).exists():
            QMessageBox.warning(self, APP_NAME, "Não encontrei o PCSX2. Ajuste o caminho na aba Avançado.")
            return
        if pcsx2.is_running():
            self.main.toast("O PCSX2 já está aberto.", "warn")
            return
        if not self.server:
            self.main.toast("Abrindo a sala primeiro, para ligar os controles certos…")
            self.toggle_server()
            if not self.server:
                return
        if not self.ensure_pads():
            return
        game = self.games.currentData() or None
        self.s.setValue("host/game", game or "")
        pcsx2.launch(exe, game, self.fullscreen.isChecked())
        self.main.toast(f"Abrindo {Path(game).stem if game else 'o PCSX2'}…")
        self.logf(f"Abrindo PCSX2{' com ' + Path(game).stem if game else ''}.")

    def ensure_pads(self) -> bool:
        problems = self.adv.pad_problems()
        if not problems:
            return True
        if not pcsx2.is_running():
            # PCSX2 fechado: ajusta sozinho (você no Jogador 1, amigos nos controles virtuais)
            return self.adv.configure_pcsx2(quiet=True)
        text = ("Os controles dos convidados ainda não estão configurados no PCSX2:\n\n• "
                + "\n• ".join(problems) + "\n\nSem isso o PCSX2 abre, mas o seu amigo não controla nada no jogo.")
        if pcsx2.is_running():
            ans = QMessageBox.warning(self, APP_NAME, text + "\n\nFeche o PCSX2 e clique em \"Configurar portas\" "
                                      "(aba Avançado).\n\nContinuar mesmo assim?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            return ans == QMessageBox.Yes
        box = QMessageBox(QMessageBox.Warning, APP_NAME, text, parent=self)
        b_cfg = box.addButton("Configurar e continuar", QMessageBox.AcceptRole)
        b_skip = box.addButton("Continuar sem configurar", QMessageBox.DestructiveRole)
        box.addButton("Cancelar", QMessageBox.RejectRole)
        box.setDefaultButton(b_cfg)
        box.exec()
        if box.clickedButton() is b_cfg:
            return self.adv.configure_pcsx2(quiet=True)
        return box.clickedButton() is b_skip

    # ------------------------------------------------------------- endereços e convite
    def _discover_wan(self):
        try:
            gw = upnp.discover()
            ip = gw.external_ip()
            if ip:
                self.bridge.wan.emit(ip)
        except Exception:
            pass

    def _on_wan(self, ip):
        self.wan_ip = ip
        self._rebuild_addresses()
        self.main.home.refresh()

    def _rebuild_addresses(self):
        cur = self.addr.currentData()
        items = []
        for ip in local_ips():
            d = describe_ip(ip)
            prio = 0 if d in ("Radmin VPN", "Tailscale", "Hamachi") else 2
            items.append((prio, ip, f"{ip}  ·  {d}"))
        if self.wan_ip:
            items.append((1, self.wan_ip, f"{self.wan_ip}  ·  roteador ({upnp.describe_wan(self.wan_ip)})"))
        items.sort()
        self.addr.blockSignals(True)
        self.addr.clear()
        for _, ip, label in items:
            self.addr.addItem(label, ip)
        idx = self.addr.findData(cur) if (cur and self._addr_chosen) else -1
        self.addr.setCurrentIndex(idx if idx >= 0 else 0)   # sem escolha manual: sempre o melhor endereço
        self.addr.blockSignals(False)
        self._update_invite()

    def current_invite(self):
        ip = self.addr.currentData()
        if not ip:
            return None
        port = self.server.cfg["port"] if self.server else self.adv.port.value()
        # pelo IP do roteador, usa a porta que o UPnP conseguiu abrir (pode ser alternativa)
        if self.server and ip == self.wan_ip and self.server.external_port:
            port = self.server.external_port
        return invite.encode(ip, port, self.password.text(), getpass.getuser())

    def _update_invite(self, *_):
        code = self.current_invite()
        self.code.setText(code or "Nenhum endereço de rede encontrado.")
        ip = self.addr.currentData() or ""
        if ip and ip == self.wan_ip and upnp.describe_wan(ip).startswith("CGNAT"):
            self.addr_hint.setText("⚠ Seu roteador está atrás de CGNAT: este convite só funciona para amigos da "
                                   "<b>mesma operadora</b>. Para outros, usem Radmin VPN ou Tailscale.")
        elif ip.startswith("192.168.") or ip.startswith("10."):
            self.addr_hint.setText("⚠ Endereço da sua rede local: só funciona para quem está na mesma casa/Wi-Fi.")
        else:
            self.addr_hint.setText("Mande o convite pelo WhatsApp/Discord. Ele leva IP, porta e senha — só mande "
                                   "para quem você quer que entre.")
        self.code.setStyleSheet("" if self.server else "color: #6b7285;")

    def copy_invite(self):
        code = self.current_invite()
        if not code:
            return
        self.own_invites.add(code)
        QApplication.clipboard().setText(code)
        self.btn_copy.flash("✓  Copiado!")
        if self.server:
            self.main.toast("Convite copiado! Cole no WhatsApp ou Discord do seu amigo.", "ok")
        else:
            self.main.toast("Convite copiado — lembre de clicar em Abrir sala!", "warn")

    # ------------------------------------------------------------- aprovação
    def _approve_blocking(self, name, ip, player):
        req = {"name": name, "ip": ip, "player": player, "event": threading.Event(), "ok": False}
        self.bridge.approve.emit(req)
        req["event"].wait(APPROVAL_TIMEOUT)
        return req["ok"]

    def _ask_approval(self, req):
        self.main.show_window()
        self.main.tray.showMessage(APP_NAME, f"{req['name']} quer entrar na sala", QSystemTrayIcon.Information, 4000)
        box = QMessageBox(QMessageBox.Question, APP_NAME,
                          f"<b>{html.escape(req['name'])}</b> quer entrar na sua sala como "
                          f"<b>Jogador {req['player']}</b>.<br><br>IP: {req['ip']}<br><br>Deixar entrar?",
                          parent=self.main)
        yes = box.addButton("✓  Aceitar", QMessageBox.AcceptRole)
        box.addButton("Recusar", QMessageBox.RejectRole)
        box.setDefaultButton(yes)

        def done(_):
            req["ok"] = box.clickedButton() is yes
            req["event"].set()

        box.finished.connect(done)
        QTimer.singleShot((APPROVAL_TIMEOUT - 2) * 1000, lambda: box.isVisible() and box.reject())
        box.open()

    # ------------------------------------------------------------- servidor
    def toggle_server(self):
        if self.server:
            self._stop_voice()
            self.server.stop()
            self.server = None
            self._set_room_ui()
            self.main.toast("Sala fechada.")
            return
        if not vigem_installed():
            msi = vigem_msi()
            if msi is None:
                QMessageBox.warning(self, APP_NAME, "Para hospedar é preciso o driver ViGEmBus:\n"
                                                    "https://github.com/nefarius/ViGEmBus/releases")
                return
            ans = QMessageBox.question(self, APP_NAME, "Para hospedar é preciso o driver ViGEmBus (cria os controles "
                                       "virtuais dos convidados).\n\nAbrir o instalador agora? Depois de instalar, "
                                       "clique em Abrir sala de novo.")
            if ans == QMessageBox.Yes:
                subprocess.Popen(["msiexec", "/i", str(msi)])
            return
        from host import HostServer

        a = self.adv
        a.save()
        q = QUALITY_PRESETS[a.quality.currentIndex()]
        cfg = {
            "port": a.port.value(), "password": self.password.text(), "mode": a.mode.currentData(),
            "codec": a.codec.currentData(), "height": q[1], "fps": q[2], "bitrate": a.bitrate.value(),
            "jpeg_quality": 75, "audio": a.audio.isChecked(), "game_area_only": a.area.currentIndex() == 0,
            "upnp": a.upnp_cb.isChecked(),
            "approve": self._approve_blocking if self.approve_cb.isChecked() else None,
            "voice": a.voice_cfg() is not None, "host_name": getpass.getuser(),
        }
        self.s.setValue("host/password", self.password.text())
        self.s.setValue("host/approve", "true" if self.approve_cb.isChecked() else "false")
        server = HostServer(cfg, self.logf)
        try:
            server.start()
        except Exception as e:
            msg = str(e)
            if "VIGEM" in msg.upper():
                msg += "\n\nReinstale o driver ViGEmBus."
            elif isinstance(e, OSError) and getattr(e, "winerror", None) == 10048:
                msg = f"A porta {cfg['port']} já está em uso. Troque na aba Avançado."
            QMessageBox.critical(self, APP_NAME, f"Não foi possível abrir a sala:\n{msg}")
            try:
                server.stop()
            except Exception:
                pass
            return
        self.server = server
        self._start_voice()
        self._set_room_ui()
        self.main.toast("Sala aberta! Agora copie o convite 📋", "ok")
        self.check_pad_mapping()
        if not pcsx2.is_running():
            self.logf("Dica: abra o jogo no PCSX2 — os convidados verão a janela dele.")

    def _set_room_ui(self):
        on = self.server is not None
        self.btn_room.setText("Fechar sala" if on else "Abrir sala")
        self.btn_room.set_variant("danger" if on else "primary")
        for w in self.adv.locked_widgets() + [self.password, self.approve_cb]:
            w.setEnabled(not on)
        if not on:
            self.dot.set_state(MUTED, False)
            self.room_lbl.setText("Sala fechada")
            self.room_sub.setText("Ao abrir, a porta é liberada no roteador (UPnP) e o convite passa a funcionar.")
            for row in list(self.rows.values()):
                row.deleteLater()
            self.rows.clear()
            self.empty.show()
            self.cap_lbl.setText("")
            self.pad_banner.hide()
            self._pad_warned = None
        self.adv.update_pad_status()
        self._update_invite()

    def kick(self, slot_idx):
        if self.server:
            self.server.kick(slot_idx)

    def _tick(self):
        if not self.server:
            return
        snap = {c["slot_idx"]: c for c in self.server.snapshot()}
        for slot in list(self.rows):
            if slot not in snap:
                self.rows.pop(slot).deleteLater()
        for slot, c in sorted(snap.items()):
            if slot not in self.rows:
                row = PlayerRow(slot, c["name"], self.kick)
                self.rows[slot] = row
                self.players_box.addWidget(row)
                eff = QGraphicsOpacityEffect(row)
                row.setGraphicsEffect(eff)
                an = QPropertyAnimation(eff, b"opacity", row, duration=350, easingCurve=QEasingCurve.OutCubic)
                an.setStartValue(0.0)
                an.setEndValue(1.0)
                an.finished.connect(lambda r=row: r.setGraphicsEffect(None))
                an.start()
            prev = self._prev_bytes.get(slot, c["bytes"])
            self._prev_bytes[slot] = c["bytes"]
            mbps = max(0, c["bytes"] - prev) * 8 / 1e6
            slot_name = pcsx2.SLOT_NAMES[self.server.slots[slot]]
            self.rows[slot].update_stats(c["rtt"], mbps, f"Jogador {slot + 2} · porta {slot_name}")
        self.empty.setVisible(not snap)
        if self.server.external_port != getattr(self, "_shown_ext", None):
            self._shown_ext = self.server.external_port
            self._update_invite()      # UPnP terminou: o convite passa a usar a porta aberta
        n, total = len(snap), len(self.server.slots)
        self.dot.set_state(OK, True)
        self.room_lbl.setText(f"Sala aberta · {n}/{total}")
        extra = f" · {self.server.upnp_status}" if self.server.upnp_status else ""
        self.room_sub.setText(("Esperando amigos — mande o convite!" if not n else "Partida rolando!") + extra)
        self.cap_lbl.setText(f"Captura: {self.server.capture_status}"
                             + (f" · {self.server.capture_fps:.0f} fps" if n else ""))
        self._pad_tick = getattr(self, "_pad_tick", 0) + 1
        if self._pad_tick % 3 == 0:
            self.check_pad_mapping()

    # ------------------------------------------------------------- voz
    def _start_voice(self):
        vcfg = self.adv.voice_cfg()
        if not vcfg or not self.server:
            return
        try:
            self.voice_mix = voice.VoiceMixer(vcfg["volume"])
            self.voice_mix.start()
            self.server.on_voice = self.voice_mix.push
        except Exception as e:
            self.voice_mix = None
            self.logf(f"Voz: não consegui abrir a saída de som ({e}).")
        try:
            self.mic = voice.Mic(self.server.send_voice, vcfg["device"])
            self.mic.ptt_mode = vcfg["ptt"]
            self.mic.threshold_db = vcfg["threshold"]
            self.mic.start()
            self.logf(f"Chamada de voz ligada · microfone: {self.mic.device_name}. F9 muta/desmuta.")
        except Exception as e:
            self.mic = None
            self.logf(f"Voz: não consegui abrir o microfone ({e}). Você ainda ouve os amigos.")
            self.main.toast("Microfone não encontrado — você só vai ouvir a chamada.", "warn")

    def _stop_voice(self):
        for x in (self.mic, self.voice_mix):
            if x:
                try:
                    x.stop()
                except Exception:
                    pass
        self.mic = self.voice_mix = None

    def _talk_tick(self):
        if not self.voice_mix:
            return
        for slot, row in self.rows.items():
            row.set_speaking(self.voice_mix.speaking(slot + 1))

    # ------------------------------------------------------------- controles do PCSX2
    def check_pad_mapping(self):
        """Com a sala aberta: confere se o PCSX2 liga você ao seu controle e cada amigo ao controle virtual dele."""
        if not self.server or self._pad_fixing:
            return
        self.adv.update_pad_status()
        problems = self.adv.pad_problems()
        if not problems:
            self.pad_banner.hide()
            self._pad_warned = None
            return
        if not pcsx2.is_running():
            self.adv.configure_pcsx2(quiet=True)      # PCSX2 fechado: corrige sem perguntar
            self.pad_banner.hide()
            return
        host_dev, guests, _ = self.adv.expected_devices()
        self.pad_banner_lbl.setText("⚠ <b>Os controles no PCSX2 estão trocados.</b> Para você ficar no Jogador 1 "
                                    f"({host_dev or '?'}) e o amigo no Jogador 2 ({guests[0]}), o PCSX2 precisa "
                                    "reabrir. <b>Salve o jogo antes.</b>")
        self.pad_banner.show()
        sig = (host_dev, tuple(guests))
        if sig != self._pad_warned:
            self._pad_warned = sig
            self.logf("Controles do PCSX2 trocados: " + "; ".join(problems))
            self.main.toast("Os controles no PCSX2 estão trocados — veja o aviso em Hospedar.", "warn")

    def fix_pads_restart(self):
        ans = QMessageBox.question(self, APP_NAME, "Para corrigir os controles, o PCSX2 vai fechar e abrir de novo "
                                   "com o mesmo jogo.\n\nSALVE O JOGO ANTES (o PCSX2 pode perguntar se você "
                                   "quer mesmo sair).\n\nContinuar?")
        if ans != QMessageBox.Yes:
            return
        self._pad_fixing = True
        self.btn_fix_pads.setEnabled(False)
        self.main.toast("Fechando o PCSX2…")
        threading.Thread(target=lambda: self.bridge.pcsx2_closed.emit(pcsx2.close_gracefully(90)), daemon=True).start()

    def _after_pcsx2_closed(self, ok):
        self._pad_fixing = False
        self.btn_fix_pads.setEnabled(True)
        if not ok:
            self.main.toast("O PCSX2 não fechou. Feche ele e clique em Corrigir de novo.", "warn")
            return
        if self.adv.configure_pcsx2(quiet=True):
            self.pad_banner.hide()
            self._pad_warned = None
            game = self.s.value("host/game", "") or None
            pcsx2.launch(self.adv.exe.text(), game, self.fullscreen.isChecked())
            self.main.toast("Controles corrigidos! Reabrindo o PCSX2…", "ok")

    def shutdown(self):
        self._stop_voice()
        if self.server:
            self.server.stop()
            self.server = None


# ============================================================================== ENTRAR
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
        self.setStyleSheet("background: black;")
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
        self.view.overlay = f"ping {s['rtt']:.0f} ms · {s['fps']:.0f} fps · {s['kbps'] / 1000:.1f} Mbps · {pad}"
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


class JoinPage(QWidget):
    def __init__(self, main, settings):
        super().__init__()
        self.main = main
        self.s = settings
        self.client = None
        self.window = None
        self.inv = None
        self.target = ""

        inner = QWidget()
        outer = QVBoxLayout(inner)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)
        outer.addWidget(page_header("Entrar numa sala", "Cole o convite que seu amigo mandou e clique em Entrar."))
        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)
        right = QVBoxLayout()
        right.setSpacing(16)
        cols.addLayout(left, 11)
        cols.addLayout(right, 9)
        outer.addLayout(cols, 1)

        c1 = Card("Convite")
        r = QHBoxLayout()
        self.code = QLineEdit()
        self.code.setObjectName("invite")
        self.code.setPlaceholderText("PS2-XXXX-XXXX-XXXX-…")
        self.code.setClearButtonEnabled(True)
        self.code.textChanged.connect(self._parse)
        b_paste = AnimButton("📋 Colar", "ghost", height=46)
        b_paste.setMinimumWidth(100)
        b_paste.clicked.connect(self.paste)
        r.addWidget(self.code, 1)
        r.addWidget(b_paste)
        c1.body.addLayout(r)
        ir = QHBoxLayout()
        self.inv_icon = StatusIcon()
        self.inv_icon.hide()
        self.inv_lbl = hint("O convite começa com PS2- e leva IP, porta e senha da sala.")
        ir.addWidget(self.inv_icon)
        ir.addWidget(self.inv_lbl, 1)
        c1.body.addLayout(ir)

        self.name = QLineEdit(self.s.value("guest/name", getpass.getuser()[:20]))
        self.name.setMaxLength(24)
        c1.body.addWidget(field("Seu nome (aparece para o host)", self.name))

        # modo manual (escondido)
        self.exp = QToolButton()
        self.exp.setObjectName("expander")
        self.exp.setText("  Entrar com IP e senha (sem convite)")
        self.exp.setCheckable(True)
        self.exp.setArrowType(Qt.RightArrow)
        self.exp.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.exp.toggled.connect(self._toggle_manual)
        c1.body.addWidget(self.exp)
        self.manual = QWidget()
        g = QGridLayout(self.manual)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(12)
        self.host = QLineEdit(self.s.value("guest/host", ""))
        self.host.setPlaceholderText("ex.: 26.12.34.56")
        self.port = spin(1024, 65535, int(self.s.value("guest/port", DEFAULT_PORT)))
        self.password = PasswordEdit("", "se o host definiu")
        g.addWidget(field("IP do host", self.host), 0, 0)
        g.addWidget(field("Porta", self.port), 0, 1)
        g.addWidget(field("Senha", self.password), 1, 0, 1, 2)
        self.manual.setMaximumHeight(0)
        self._man_anim = QPropertyAnimation(self.manual, b"maximumHeight", self, duration=260,
                                            easingCurve=QEasingCurve.OutCubic)
        c1.body.addWidget(self.manual)

        st = QHBoxLayout()
        self.spinner = Spinner()
        self.spinner.hide()
        self.st_icon = StatusIcon()
        self.st_icon.hide()
        self.st_lbl = QLabel("")
        self.st_lbl.setWordWrap(True)
        self.btn = AnimButton("Entrar na sala", "primary", height=46)
        self.btn.setMinimumWidth(180)
        self.btn.clicked.connect(self.toggle)
        st.addWidget(self.spinner)
        st.addWidget(self.st_icon)
        st.addWidget(self.st_lbl, 1)
        st.addWidget(self.btn)
        c1.body.addLayout(st)
        left.addWidget(c1)
        left.addStretch()

        self.call_card = Card("Na chamada")
        self.call_box = QVBoxLayout()
        self.call_box.setSpacing(4)
        self.call_card.body.addLayout(self.call_box)
        self.call_rows = {}
        self.call_card.hide()
        right.addWidget(self.call_card)
        self.call_timer = QTimer(self)
        self.call_timer.timeout.connect(self._call_tick)
        self.call_timer.start(100)

        c2 = Card("Seu controle")
        self.pad = QComboBox()
        self.pad.addItem("Automático (primeiro controle encontrado)", -1)
        for i in range(4):
            self.pad.addItem(f"Controle XInput {i + 1}", i)
        self.pad.addItem("Somente teclado", -2)
        self.pad.setCurrentIndex(max(0, self.pad.findData(int(self.s.value("guest/pad", -1)))))
        c2.body.addWidget(field("Usar", self.pad))
        self.pad_view = GamepadView()
        c2.body.addWidget(self.pad_view)
        self.pad_lbl = hint("")
        self.pad_lbl.setAlignment(Qt.AlignCenter)
        c2.body.addWidget(self.pad_lbl)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 150)
        self.volume.setValue(int(self.s.value("guest/volume", 100)))
        self.volume.valueChanged.connect(self._volume)
        c2.body.addWidget(field("Volume do jogo", self.volume))
        from guest import KEYBOARD_HELP
        kb = hint("<b>Teclado:</b> " + html.escape(KEYBOARD_HELP).replace("\n", "<br>"))
        c2.body.addWidget(kb)
        right.addWidget(c2)
        right.addStretch()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scrollable(inner))
        self.pad_timer = QTimer(self)
        self.pad_timer.timeout.connect(self._poll_pad)
        self.pad_timer.start(33)
        self._set_idle()

    # ------------------------------------------------------------- controle ao vivo
    def _poll_pad(self):
        if not self.isVisible():
            return
        sel = self.pad.currentData()
        idx = None
        if sel >= 0:
            idx = sel if xinput.get_state(sel) is not None else None
        elif sel == -1:
            c = xinput.connected()
            idx = c[0] if c else None
        st = xinput.get_state(idx) if idx is not None else None
        self.pad_view.set_state(st)
        self.pad_lbl.setText(f"Controle {idx + 1} — aperte os botões para testar" if st else
                             ("Nenhum controle — você vai jogar pelo teclado" if sel != -2 else "Somente teclado"))

    def _volume(self, v):
        self.s.setValue("guest/volume", v)
        if self.client:
            self.client.set_volume(v / 100)

    # ------------------------------------------------------------- convite
    def paste(self):
        self.code.setText(QApplication.clipboard().text().strip())
        if not self.inv:
            self.main.toast("Não achei um convite na área de transferência.", "warn")

    def _parse(self, text):
        self.inv = invite.decode(text)
        if not text.strip():
            self.inv_icon.hide()
            self.inv_lbl.setText("O convite começa com PS2- e leva IP, porta e senha da sala.")
        elif self.inv:
            self.inv_icon.set("ok")
            self.inv_icon.show()
            self.inv_lbl.setText(f"Convite de <b>{html.escape(self.inv['name'] or 'host')}</b> · "
                                 f"{self.inv['host']}:{self.inv['port']}"
                                 + (" · com senha" if self.inv["password"] else ""))
        else:
            self.inv_icon.set("bad")
            self.inv_icon.show()
            self.inv_lbl.setText("Código inválido — confira se copiou o convite inteiro.")

    def use_invite(self, inv, connect=False):
        self.exp.setChecked(False)
        self.code.setText(inv["code"])
        if connect and not self.client:
            self.toggle()

    def _toggle_manual(self, on):
        self.exp.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self._man_anim.stop()
        self._man_anim.setStartValue(self.manual.maximumHeight())
        self._man_anim.setEndValue(self.manual.sizeHint().height() if on else 0)
        self._man_anim.start()

    # ------------------------------------------------------------- estados
    def _state(self, kind, text):
        self.spinner.setVisible(kind == "busy")
        self.st_icon.setVisible(kind in ("ok", "bad", "warn"))
        if kind in ("ok", "bad", "warn"):
            self.st_icon.set(kind)
        self.st_lbl.setText(text)

    def _set_idle(self, text=""):
        self.client = None
        self.btn.setText("Entrar na sala")
        self.btn.set_variant("primary")
        self._state("bad" if text else "idle", text)

    # ------------------------------------------------------------- conexão
    def toggle(self):
        if self.client:
            if self.window:
                self.window.close()
            else:
                self.client.stop()
                self._set_idle("Cancelado.")
            return
        if self.exp.isChecked():
            host, port, pw = self.host.text().strip(), self.port.value(), self.password.text()
            if not host:
                self.main.toast("Digite o IP do host.", "warn")
                self.host.setFocus()
                return
            self.s.setValue("guest/host", host)
            self.s.setValue("guest/port", port)
            who = host
        else:
            if not self.inv:
                self.main.toast("Cole o convite que seu amigo mandou.", "warn")
                self.code.setFocus()
                return
            host, port, pw = self.inv["host"], self.inv["port"], self.inv["password"]
            who = self.inv["name"] or host
        self.target = who
        name = self.name.text().strip() or "Convidado"
        self.s.setValue("guest/name", name)
        self.s.setValue("guest/pad", self.pad.currentData())
        from guest import GuestClient

        self.client = GuestClient(host, port, name, pw, self.pad.currentData(), self.volume.value() / 100,
                                  voice_cfg=self.main.adv.voice_cfg())
        self.client.roster_changed.connect(self._rebuild_call)
        self.client.welcome.connect(self._on_welcome)
        self.client.waiting.connect(lambda: self._state("busy", f"Aguardando <b>{html.escape(who)}</b> aceitar…"))
        self.client.failed.connect(self._on_failed)
        self.client.disconnected.connect(self._on_disconnected)
        self._state("busy", f"Conectando em {html.escape(who)}…")
        self.btn.setText("Cancelar")
        self.btn.set_variant("ghost")
        self.client.start()

    def _on_welcome(self, info):
        extra = "" if info.get("audio") else " · sem áudio"
        if info.get("audio_error"):
            extra = f" · áudio falhou: {info['audio_error']}"
        if info.get("voice_error"):
            extra += f" · voz falhou: {info['voice_error']}"
        elif info.get("voice") and self.client and self.client.mic:
            extra += " · 🎤 voz ligada (F9 muta)"
        elif not info.get("voice"):
            extra += " · o host está sem chamada de voz"
        self._state("ok", f"<b>Conectado como Jogador {info['player']}</b> · porta {info['slot']}{extra}")
        self.btn.setText("Sair da sala")
        self.btn.set_variant("danger")
        self.main.toast(f"Você entrou como Jogador {info['player']}! 🎮", "ok")
        self.window = GameWindow(self.client, f"{APP_NAME} — Jogador {info['player']}")
        self.window.view.message = "Aguardando a imagem do host…"
        self.window.closed.connect(lambda: setattr(self, "window", None))
        self.window.show()
        self.window.activateWindow()

    def _rebuild_call(self, roster):
        for row in self.call_rows.values():
            row.deleteLater()
        self.call_rows = {}
        me = self.client.my_id if self.client else None
        for sid in sorted(roster):
            name = roster[sid] + (" (você)" if sid == me else " (host)" if sid == 0 else "")
            lab = QLabel()
            lab.setProperty("nm", html.escape(name))
            self.call_box.addWidget(lab)
            self.call_rows[sid] = lab
        self.call_card.setVisible(bool(roster) and bool(self.client and self.client.voice))

    def _call_tick(self):
        c = self.client
        if not c or not c.voice or not self.call_rows:
            if self.call_card.isVisible() and not (c and c.voice):
                self.call_card.hide()
            return
        for sid, lab in self.call_rows.items():
            talking = (c.mic.talking if c.mic else False) if sid == c.my_id else c.voice.speaking(sid)
            dot = OK if talking else "#3a4152"
            txt = f"<span style='color:{dot}; font-size:14pt'>●</span> {lab.property('nm')}" + (
                "  <span style='color:#51cf66'>falando…</span>" if talking else "")
            if lab.text() != txt:
                lab.setText(txt)

    def _on_failed(self, msg):
        self._set_idle(msg)
        self.main.toast(msg, "bad")

    def _on_disconnected(self, reason):
        if self.window:
            w, self.window = self.window, None
            w.close()
        self._set_idle()
        self._state("warn", reason)
        self.main.toast(reason, "warn")

    def shutdown(self):
        if self.client:
            self.client.stop()


# ============================================================================== CONTROLES
class PadCard(Card):
    def __init__(self, title):
        super().__init__(title)
        self.view = GamepadView()
        self.sub = hint("")
        self.sub.setAlignment(Qt.AlignCenter)
        self.body.addWidget(self.view)
        self.body.addWidget(self.sub)
        self.setMinimumWidth(300)
        self.title_lbl = self.findChild(QLabel, "cardtitle")


class ControllersPage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)
        root.addWidget(page_header("Controles", "Os controles conectados agora, ao vivo. Aperte os botões para testar."))
        lab = QLabel("FÍSICOS — ligados neste PC")
        lab.setObjectName("flabel")
        root.addWidget(lab)
        self.phys_grid = QGridLayout()
        self.phys_grid.setSpacing(16)
        root.addLayout(self.phys_grid)
        self.phys_cards = []
        for i in range(4):
            c = PadCard(f"🎮  Controle {i + 1}")
            self.phys_cards.append(c)
            self.phys_grid.addWidget(c, i // 2, i % 2)
        self.no_phys = hint("Nenhum controle físico encontrado. Controles de PlayStation precisam do DS4Windows ou "
                            "do Steam para aparecer como XInput.")
        root.addWidget(self.no_phys)
        lab2 = QLabel("VIRTUAIS — um para cada amigo (só com a sala aberta)")
        lab2.setObjectName("flabel")
        root.addSpacing(8)
        root.addWidget(lab2)
        self.virt_grid = QGridLayout()
        self.virt_grid.setSpacing(16)
        root.addLayout(self.virt_grid)
        self.virt_cards = []
        for i in range(3):
            c = PadCard(f"🌐  Jogador {i + 2}")
            self.virt_cards.append(c)
            self.virt_grid.addWidget(c, i // 2, i % 2)
        self.no_virt = hint("Abra a sala na aba Hospedar para criar os controles virtuais dos amigos.")
        root.addWidget(self.no_virt)
        root.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scrollable(inner))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(33)

    def _poll(self):
        if not self.isVisible():
            return
        srv = self.main.host.server
        virtual = set(srv.virtual_slots) if srv else set()
        any_phys = False
        n = 0
        for i in range(4):
            st = None if i in virtual else xinput.get_state(i)
            card = self.phys_cards[i]
            card.setVisible(st is not None)
            if st is not None:
                any_phys = True
                n += 1
                card.view.set_state(st)
                card.sub.setText(f"XInput {i + 1} · no PCSX2: SDL-{i}")
        self.no_phys.setVisible(not any_phys)

        clients = {c["slot_idx"]: c for c in srv.snapshot()} if srv else {}
        for i, card in enumerate(self.virt_cards):
            show = bool(srv) and i < len(srv.pads)
            card.setVisible(show)
            if not show:
                continue
            c = clients.get(i)
            card.view.set_state(srv.pad_state(i) if c else None)
            slot = pcsx2.SLOT_NAMES[srv.slots[i]]
            sdl = srv.virtual_slots[i] if i < len(srv.virtual_slots) else "?"
            who = f"<b>{html.escape(c['name'])}</b> · {c['rtt']:.0f} ms" if c else "livre — aguardando amigo"
            card.sub.setText(f"{who}<br>porta {slot} · no PCSX2: SDL-{sdl}")
        self.no_virt.setVisible(not srv)


# ============================================================================== INÍCIO
class CheckRow(QWidget):
    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        self.icon = StatusIcon()
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.btn = QPushButton()
        self.btn.setObjectName("mini")
        self.btn.hide()
        self._cb = None
        self.btn.clicked.connect(lambda: self._cb and self._cb())
        lay.addWidget(self.icon)
        lay.addWidget(self.text, 1)
        lay.addWidget(self.btn)

    def set(self, kind, text, fix=None, fix_cb=None):
        self.icon.set(kind)
        self.text.setText(text)
        self.btn.setVisible(bool(fix))
        if fix:
            self.btn.setText(fix)
            self._cb = fix_cb


class HomePage(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addWidget(page_header(f"Bora jogar, {getpass.getuser()}! 👋",
                                   "Multiplayer local do PCSX2 pela internet. O que você quer fazer?"))
        cards = QHBoxLayout()
        cards.setSpacing(16)
        for icon, title, text, btn, variant, cb in (
                ("🎮", "Hospedar partida", "Você roda o jogo no seu PCSX2 e convida os amigos para jogar junto.",
                 "Começar", "primary", lambda: main.go(2)),
                ("🔗", "Entrar com convite", "Seu amigo mandou um código PS2-…? Cole aqui e entre direto na sala.",
                 "Colar convite", "ghost", self._join)):
            c = Card()
            c.setMinimumHeight(210)
            ic = QLabel(icon)
            ic.setStyleSheet("font-size: 34pt;")
            t = QLabel(title)
            t.setObjectName("cardtitle")
            t.setStyleSheet("font-size: 15pt;")
            d = hint(text)
            b = AnimButton(btn, variant, height=44)
            b.clicked.connect(cb)
            c.body.addWidget(ic)
            c.body.addWidget(t)
            c.body.addWidget(d)
            c.body.addStretch()
            c.body.addWidget(b)
            cards.addWidget(c)
        root.addLayout(cards)

        chk = Card("Está tudo pronto?")
        self.r_pcsx2, self.r_pads, self.r_vigem, self.r_net = CheckRow(), CheckRow(), CheckRow(), CheckRow()
        for r in (self.r_pcsx2, self.r_pads, self.r_vigem, self.r_net):
            chk.body.addWidget(r)
        root.addWidget(chk)
        root.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scrollable(inner))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)

    def _join(self):
        self.main.go(3)
        self.main.join.paste()

    def _install_vigem(self):
        msi = vigem_msi()
        if msi:
            subprocess.Popen(["msiexec", "/i", str(msi)])

    def refresh(self):
        adv, host = self.main.adv, self.main.host
        if Path(adv.exe.text()).exists():
            self.r_pcsx2.set("ok", "PCSX2 encontrado.")
        else:
            self.r_pcsx2.set("bad", "PCSX2 não encontrado — só necessário para hospedar.", "Localizar",
                             lambda: (self.main.go(5), adv._browse_exe()))
        if adv.pad_problems():
            self.r_pads.set("warn", "Controles dos convidados não configurados no PCSX2.", "Configurar",
                            lambda: (adv.configure_pcsx2(), self.refresh()))
        else:
            self.r_pads.set("ok", "PCSX2 pronto para receber os controles dos convidados.")
        if vigem_installed():
            self.r_vigem.set("ok", "Driver de controle virtual (ViGEmBus) instalado.")
        else:
            self.r_vigem.set("warn", "Driver ViGEmBus ausente — necessário para hospedar.", "Instalar",
                             self._install_vigem)
        vpn = [ip for ip in local_ips() if describe_ip(ip) in ("Radmin VPN", "Tailscale", "Hamachi")]
        if vpn:
            self.r_net.set("ok", f"VPN de jogos ativa ({describe_ip(vpn[0])}: {vpn[0]}) — funciona com qualquer amigo.")
        elif host.wan_ip:
            d = upnp.describe_wan(host.wan_ip)
            kind = "warn" if d.startswith("CGNAT") else "ok"
            self.r_net.set(kind, f"Roteador com UPnP · IP {host.wan_ip} ({d}).")
        else:
            self.r_net.set("warn", "Roteador sem UPnP e nenhuma VPN — use Radmin VPN ou Tailscale para jogar online.")


# ============================================================================== AJUDA
HELP = """
<h2>Como funciona</h2>
<p>O <b>host</b> roda o PCSX2 no PC dele e joga como Jogador 1. O PS2 Online transmite a imagem e o som para os
<b>convidados</b>, e cada convidado vira um controle virtual no PC do host (Jogador 2, 3 ou 4). Para o jogo, é
como se todos estivessem no mesmo sofá.</p>
<h2>Hospedar</h2>
<ol>
<li>Na tela <b>Início</b>, confira se está tudo ✓ (o app ajuda a corrigir o que faltar).</li>
<li>Em <b>Hospedar</b>: escolha o jogo, clique <b>Abrir sala</b> e depois <b>Copiar convite</b>.</li>
<li>Mande o convite para o amigo. Quando ele tentar entrar, você aprova (se a opção estiver ligada).</li>
<li>Abra o jogo pelo botão <b>Abrir jogo no PCSX2</b> e deixe a janela visível (não minimize).</li>
</ol>
<h2>Entrar</h2>
<ol>
<li>Copie o convite que o amigo mandou e abra o PS2 Online — ele detecta o convite e pergunta se quer entrar.</li>
<li>Ou vá em <b>Entrar</b>, cole o código e clique <b>Entrar na sala</b>.</li>
<li>Na janela do jogo: <b>F11</b> = tela cheia, <b>F1</b> = ping/fps.</li>
</ol>
<h2>Internet e CGNAT</h2>
<p>O app abre a porta no roteador sozinho (UPnP) e a fecha quando você sai. Mas se a sua operadora usa
<b>CGNAT</b> (IP do roteador começando com 100.64–100.127), só amigos da <b>mesma operadora</b> conseguem
entrar assim. Para os outros, usem <b>Radmin VPN</b> ou <b>Tailscale</b>: o convite passa a usar o IP da VPN.</p>
<h2>Chamada de voz</h2>
<ul>
<li>Liga sozinha quando a sala abre (host) ou quando você entra (convidado). Todo mundo ouve todo mundo, junto
com o som do jogo.</li>
<li><b>F9</b> muta/desmuta o seu microfone, mesmo com o jogo em foco. O botão 🎤 na barra lateral faz o mesmo.</li>
<li>Em <b>Avançado → Chamada de voz</b>: microfone, sensibilidade, volume das vozes e o modo
<b>apertar para falar</b> (ex.: segurar CapsLock).</li>
<li>Quem está falando aparece com um anel verde (host) ou "falando…" na lista da chamada (convidado).</li>
<li>Use <b>fone de ouvido</b>: sem fone, o microfone capta a caixa de som e os outros ouvem eco.</li>
</ul>
<h2>Controles no PCSX2</h2>
<p>Ao abrir a sala, o app descobre qual controle é o seu e qual é o de cada amigo e ajusta o PCSX2 sozinho
(você no Jogador 1). Se o PCSX2 já estiver aberto com os controles trocados, aparece um aviso em
<b>Hospedar</b> com o botão <b>Corrigir agora</b>, que reabre o PCSX2 no mesmo jogo — salve antes.</p>
<h2>Dicas</h2>
<ul>
<li>Travando? Em <b>Avançado</b>, baixe a qualidade ou a taxa de vídeo, ou use o codificador da sua placa de vídeo.</li>
<li>O som enviado aos amigos é <b>só o som do PCSX2</b>: a voz da chamada, Spotify, Discord e as
notificações do seu PC não vão junto.</li>
<li>A aba <b>Controles</b> mostra ao vivo se o controle de cada amigo está chegando.</li>
<li>Ping abaixo de ~60 ms é ótimo; acima de 120 ms jogos de luta ficam difíceis.</li>
</ul>
"""


class HelpPage(QWidget):
    def __init__(self):
        super().__init__()
        inner = QWidget()
        root = QVBoxLayout(inner)
        root.setContentsMargins(28, 24, 28, 24)
        root.addWidget(page_header("Ajuda", f"PS2 Online {APP_VERSION}"))
        c = Card()
        lbl = QLabel(HELP)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setStyleSheet("font-size: 10.5pt; line-height: 140%;")
        c.body.addWidget(lbl)
        root.addWidget(c)
        root.addStretch()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scrollable(inner))


# ============================================================================== JANELA
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1240, 800)
        self.setMinimumSize(980, 640)
        self.settings = QSettings("PS2Online", "PS2Online")
        self._last_offered = None

        root = QWidget()
        root.setObjectName("root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = Sidebar()
        logo = QLabel("PS2 <span style='color:#5c7cfa'>Online</span>")
        logo.setStyleSheet("font-size: 17pt; font-weight: 800; padding: 0 6px 14px 6px;")
        self.sidebar.lay.addWidget(logo)
        self.stack = FadeStack()
        self.stack.setObjectName("content")

        self.adv = AdvancedPage(self, self.settings)
        self.host = HostPage(self, self.adv, self.settings)
        self.join = JoinPage(self, self.settings)
        self.home = HomePage(self)
        self.pads = ControllersPage(self)
        self.help = HelpPage()
        # índices: 0 início, 1 (reservado p/ ordem visual), ...
        self.pages = [("🏠   Início", self.home), ("🎮   Hospedar", self.host), ("🔗   Entrar", self.join),
                      ("🕹   Controles", self.pads), ("⚙   Avançado", self.adv), ("❓   Ajuda", self.help)]
        for label, page in self.pages:
            self.sidebar.add(label)
            self.stack.addWidget(page)
        self.sidebar.lay.addStretch()
        self.voice_bar = VoiceBar()
        self.voice_bar.btn.clicked.connect(self.toggle_mute)
        self.sidebar.lay.addWidget(self.voice_bar)
        self._f9 = False
        self.voice_timer = QTimer(self)
        self.voice_timer.timeout.connect(self._voice_tick)
        self.voice_timer.start(20)
        pill = QWidget()
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(4, 0, 4, 0)
        self.status_dot = PulseDot(MUTED, 10)
        self.status_lbl = QLabel("Inativo")
        self.status_lbl.setObjectName("hint")
        pl.addWidget(self.status_dot)
        pl.addWidget(self.status_lbl, 1)
        self.sidebar.lay.addWidget(pill)
        ver = hint(f"v{APP_VERSION}")
        ver.setContentsMargins(8, 4, 0, 0)
        self.sidebar.lay.addWidget(ver)
        self.sidebar.changed.connect(self.stack.fade_to)
        h.addWidget(self.sidebar)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self._toast = Toast(root)

        start = int(self.settings.value("ui/page", 0))
        start = start if 0 <= start < len(self.pages) else 0
        self.stack.setCurrentIndex(start)
        QTimer.singleShot(0, lambda: self.sidebar.select(start, animate=False))
        self.sidebar.changed.connect(lambda i: self.settings.setValue("ui/page", i))

        self._build_tray()
        self.home.refresh()
        QGuiApplication.instance().applicationStateChanged.connect(self._app_state)
        QTimer.singleShot(900, self.check_clipboard)

    # ------------------------------------------------------------- navegação / avisos
    def go(self, page_number):
        """page_number: 1 = Início, 2 = Hospedar, 3 = Entrar, 4 = Controles, 5 = Avançado, 6 = Ajuda."""
        self.sidebar.select(page_number - 1)

    def toast(self, text, kind="info"):
        self._toast.show_msg(text, kind)

    # ------------------------------------------------------------- convite na área de transferência
    def _app_state(self, state):
        if state == Qt.ApplicationActive:
            QTimer.singleShot(150, self.check_clipboard)

    def check_clipboard(self):
        if self.host.server or self.join.client or QApplication.activeModalWidget():
            return
        inv = invite.decode(QApplication.clipboard().text())
        if not inv or inv["code"] in self.host.own_invites or inv["code"] == self._last_offered:
            return
        if inv["host"] in local_ips() or inv["host"] == self.host.wan_ip:   # convite da minha própria sala
            return
        self._last_offered = inv["code"]
        who = inv["name"] or inv["host"]
        ans = QMessageBox.question(self, APP_NAME, f"Encontrei um convite de <b>{html.escape(who)}</b> "
                                                   f"({inv['host']}:{inv['port']}).<br><br>Entrar na sala agora?")
        if ans == QMessageBox.Yes:
            self.go(3)
            self.join.use_invite(inv, connect=True)

    # ------------------------------------------------------------- bandeja
    def _build_tray(self):
        self.tray = QSystemTrayIcon(QIcon(str(BASE_DIR / "icon.png")), self)
        menu = QMenu()
        menu.addAction("Abrir PS2 Online", self.show_window)
        menu.addSeparator()
        self.act_status = menu.addAction("Sala fechada")
        self.act_status.setEnabled(False)
        self.act_room = menu.addAction("Abrir sala", lambda: (self.go(2), self.host.toggle_server()))
        self.act_copy = menu.addAction("Copiar convite", self.host.copy_invite)
        menu.addSeparator()
        menu.addAction("Sair do PS2 Online", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show_window() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
        self.tray.show()
        t = QTimer(self)
        t.timeout.connect(self._update_status)
        t.start(1000)
        self._update_status()

    def _update_status(self):
        srv = self.host.server
        if self.join.client and self.join.window:
            text, color, pulse = f"Jogando em {self.join.target}", ACCENT, True
        elif self.join.client:
            text, color, pulse = "Conectando…", WARN, True
        elif srv:
            n = len(srv.snapshot())
            text, color, pulse = f"Sala aberta · {n}/{len(srv.slots)}", OK, True
        else:
            text, color, pulse = "Inativo", MUTED, False
        self.status_lbl.setText(text)
        self.status_dot.set_state(color, pulse)
        self.act_status.setText(text)
        self.act_room.setText("Fechar sala" if srv else "Abrir sala")
        self.tray.setToolTip(f"{APP_NAME}\n{text}")

    # ------------------------------------------------------------- voz
    def _call(self):
        """(microfone, mixer) da chamada atual, como host ou como convidado."""
        if self.host.server:
            return self.host.mic, self.host.voice_mix
        c = self.join.client
        if c:
            return c.mic, c.voice
        return None, None

    def toggle_mute(self):
        mic, _ = self._call()
        if mic:
            mic.muted = not mic.muted
            self.toast("🔇 Microfone mutado (F9 para voltar)" if mic.muted else "🎤 Microfone ligado",
                       "warn" if mic.muted else "ok")

    def _voice_tick(self):
        mic, mix = self._call()
        f9 = voice.key_down(voice.MUTE_KEY)
        if f9 and not self._f9 and mic:
            self.toggle_mute()
        self._f9 = f9
        if not (mic or mix):
            if self.voice_bar.isVisible():
                self.voice_bar.hide()
            return
        self.voice_bar.show()
        cfg = self.adv.voice_cfg()
        if cfg and mix:
            mix.volume = cfg["volume"]
        if not mic:
            self.voice_bar.btn.setText("🔇")
            self.voice_bar.lbl.setText("Sem microfone — só ouvindo")
            self.voice_bar.meter.set(0, False)
            return
        if cfg:
            mic.ptt_mode = cfg["ptt"]
            mic.threshold_db = cfg["threshold"]
            mic.ptt_down = cfg["ptt"] and voice.key_down(cfg["ptt_key"])
        self.voice_bar.btn.setText("🔇" if mic.muted else "🎤")
        if mic.muted:
            txt = "Mutado · F9 para falar"
        elif mic.ptt_mode and not mic.ptt_down:
            txt = f"Segure {self.adv.ptt_key.currentText()} para falar"
        elif mic.talking:
            txt = "Falando…"
        else:
            txt = "Microfone ligado"
        if self.voice_bar.lbl.text() != txt:
            self.voice_bar.lbl.setText(txt)
        self.voice_bar.meter.set(0 if mic.muted else mic.level, mic.talking)

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        self.show_window()
        self.close()

    def closeEvent(self, e):
        n = len(self.host.server.snapshot()) if self.host.server else 0
        if n or (self.join.client and self.join.window):
            msg = (f"Fechar o PS2 Online encerra a sala e desconecta {n} jogador(es)." if n else
                   "Fechar o PS2 Online tira você da sala.")
            if QMessageBox.question(self, APP_NAME, msg + "\n\nFechar mesmo assim?") != QMessageBox.Yes:
                e.ignore()
                return
        self.join.shutdown()
        self.host.shutdown()      # fecha a sala, avisa os convidados e fecha a porta do roteador
        self.tray.hide()
        self.settings.sync()
        super().closeEvent(e)
        QApplication.quit()


# ============================================================================== autoteste / main
def selftest(out_path):
    """Diagnóstico: abre host e convidado neste PC por 3 s e grava o resultado em out_path."""
    from PySide6.QtCore import QCoreApplication
    import host as hostmod
    from guest import GuestClient

    lines = []
    app = QCoreApplication(sys.argv)
    pcsx2.find_game_area = lambda game_area_only=True: ({"left": 0, "top": 0, "width": 1280, "height": 720}, None)
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
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, c in ((QPalette.Window, "#12141b"), (QPalette.WindowText, "#e6e8ee"), (QPalette.Base, "#0f1218"),
                    (QPalette.Text, "#e6e8ee"), (QPalette.Button, "#232734"), (QPalette.ButtonText, "#e6e8ee"),
                    (QPalette.Highlight, "#3b5bdb"), (QPalette.PlaceholderText, "#5d6375")):
        pal.setColor(role, QColor(c))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    rc = app.exec()
    os._exit(rc)   # garante que nenhuma thread (áudio, rede) fique viva depois de fechar


if __name__ == "__main__":
    main()
