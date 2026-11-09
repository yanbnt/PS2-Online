"""Componentes visuais do PS2 Online: botões animados, cartões, spinner, toast, controle desenhado."""
import math

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

ACCENT = "#4c6ef5"
ACCENT_2 = "#7950f2"
OK = "#51cf66"
WARN = "#fcc419"
BAD = "#ff6b6b"
MUTED = "#8c93a6"


def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


# ------------------------------------------------------------------------------ botão animado
class AnimButton(QPushButton):
    PALETTES = {
        "primary": ("#3b5bdb", "#5c7cfa", "#ffffff"),
        "danger": ("#c92a2a", "#f03e3e", "#ffffff"),
        "success": ("#2b8a3e", "#37b24d", "#ffffff"),
        "ghost": ("#232734", "#2e3445", "#e6e8ee"),
    }

    def __init__(self, text="", variant="primary", parent=None, height=40):
        super().__init__(text, parent)
        self._variant = variant
        self._t = 0.0
        self._anim = QVariantAnimation(self, duration=170, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(height)
        self._restore_timer = None

    def set_variant(self, v):
        self._variant = v
        self.update()

    def _on_anim(self, v):
        self._t = float(v)
        self.update()

    def _go(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._go(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._go(0.0)
        super().leaveEvent(e)

    def flash(self, text, ms=1600, variant="success"):
        """Mostra um texto temporário (ex.: 'Copiado!') e volta ao normal."""
        old_text, old_var = self.text(), self._variant
        if self._restore_timer:
            self._restore_timer.stop()
            old_text, old_var = self._restore
        self._restore = (old_text, old_var)
        self.setText(text)
        self.set_variant(variant)
        self._restore_timer = QTimer(self, singleShot=True)
        self._restore_timer.timeout.connect(lambda: (self.setText(old_text), self.set_variant(old_var),
                                                     setattr(self, "_restore_timer", None)))
        self._restore_timer.start(ms)

    def sizeHint(self):
        sh = super().sizeHint()
        return sh.expandedTo(sh.__class__(sh.width() + 24, self.minimumHeight()))

    def paintEvent(self, _):
        base, hover, fg = self.PALETTES.get(self._variant, self.PALETTES["primary"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.isEnabled():
            c = lerp_color(QColor(base), QColor(hover), self._t)
            if self.isDown():
                c = c.darker(115)
            if self._variant == "primary":
                g = QLinearGradient(r.topLeft(), r.topRight())
                g.setColorAt(0, c)
                g.setColorAt(1, lerp_color(c, QColor(ACCENT_2), 0.35))
                p.setBrush(QBrush(g))
            else:
                p.setBrush(c)
            p.setPen(QPen(QColor(255, 255, 255, int(18 + 30 * self._t)), 1))
            text_c = QColor(fg)
        else:
            p.setBrush(QColor("#1b1e26"))
            p.setPen(QPen(QColor("#262a35"), 1))
            text_c = QColor("#5d6375")
        p.drawRoundedRect(r, 10, 10)
        f = self.font()
        f.setBold(True)
        p.setFont(f)
        p.setPen(text_c)
        p.drawText(self.rect(), Qt.AlignCenter, self.text())


# ------------------------------------------------------------------------------ cartão com brilho
class Card(QFrame):
    def __init__(self, title=None, step=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._shadow = QGraphicsDropShadowEffect(self, blurRadius=0, offset=QPointF(0, 4))
        self._shadow.setColor(QColor(76, 110, 245, 0))
        self.setGraphicsEffect(self._shadow)
        self._anim = QVariantAnimation(self, duration=220, easingCurve=QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._glow)
        self._t = 0.0
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(10)
        if title:
            row = QHBoxLayout()
            row.setSpacing(10)
            if step is not None:
                badge = QLabel(str(step))
                badge.setObjectName("step")
                badge.setAlignment(Qt.AlignCenter)
                badge.setFixedSize(26, 26)
                row.addWidget(badge)
            t = QLabel(title)
            t.setObjectName("cardtitle")
            row.addWidget(t)
            row.addStretch()
            self.header = row
            self.body.addLayout(row)

    def _glow(self, v):
        self._t = float(v)
        self._shadow.setBlurRadius(6 + 26 * self._t)
        self._shadow.setColor(QColor(76, 110, 245, int(90 * self._t)))

    def _go(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, e):
        self._go(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._go(0.0)
        super().leaveEvent(e)


# ------------------------------------------------------------------------------ campos
def field(label, widget, hint_text=None):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(5)
    lab = QLabel(label)
    lab.setObjectName("flabel")
    v.addWidget(lab)
    v.addWidget(widget)
    if hint_text:
        h = QLabel(hint_text)
        h.setObjectName("hint")
        h.setWordWrap(True)
        v.addWidget(h)
    return w


def eye_icon(open_=True):
    """Ícone de olho desenhado (para mostrar/ocultar senha)."""
    pm = QPixmap(40, 40)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#9aa1b2"), 3))
    path = QPainterPath()
    path.moveTo(4, 20)
    path.quadTo(20, 4, 36, 20)
    path.quadTo(20, 36, 4, 20)
    p.drawPath(path)
    p.setBrush(QColor("#9aa1b2"))
    p.drawEllipse(QPointF(20, 20), 5, 5)
    if not open_:
        p.setPen(QPen(QColor("#9aa1b2"), 3))
        p.drawLine(8, 34, 32, 6)
    p.end()
    return QIcon(pm)


class PasswordEdit(QLineEdit):
    def __init__(self, text="", placeholder=""):
        super().__init__(text)
        self.setEchoMode(QLineEdit.Password)
        self.setPlaceholderText(placeholder)
        self._act = QAction(eye_icon(True), "Mostrar senha", self)
        self._act.triggered.connect(self._toggle)
        self.addAction(self._act, QLineEdit.TrailingPosition)

    def _toggle(self):
        show = self.echoMode() == QLineEdit.Password
        self.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password)
        self._act.setIcon(eye_icon(not show))
        self._act.setText("Ocultar senha" if show else "Mostrar senha")


# ------------------------------------------------------------------------------ indicadores
class PulseDot(QWidget):
    def __init__(self, color=MUTED, size=12):
        super().__init__()
        self._color = QColor(color)
        self._pulse = False
        self._t = 0.0
        self.setFixedSize(size * 2, size * 2)
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1400, loopCount=-1)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_t", float(v)), self.update()))

    def set_state(self, color, pulse):
        self._color = QColor(color)
        if pulse and not self._pulse:
            self._anim.start()
        elif not pulse and self._pulse:
            self._anim.stop()
            self._t = 0.0
        self._pulse = pulse
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self.width() / 4
        if self._pulse:
            ring = QColor(self._color)
            ring.setAlpha(int(160 * (1 - self._t)))
            p.setPen(Qt.NoPen)
            p.setBrush(ring)
            p.drawEllipse(c, r + r * 1.1 * self._t, r + r * 1.1 * self._t)
        p.setBrush(self._color)
        p.drawEllipse(c, r, r)


class Spinner(QWidget):
    def __init__(self, size=22):
        super().__init__()
        self.setFixedSize(size, size)
        self._a = 0
        self._anim = QVariantAnimation(self, startValue=0, endValue=360, duration=900, loopCount=-1)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_a", int(v)), self.update()))

    def showEvent(self, e):
        self._anim.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self._anim.stop()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, self.width() - 6, self.height() - 6)
        p.setPen(QPen(QColor("#2a2f3d"), 3))
        p.drawEllipse(r)
        p.setPen(QPen(QColor(ACCENT), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, -self._a * 16, 100 * 16)


class StatusIcon(QLabel):
    def set(self, kind):
        sym, col = {"ok": ("✓", OK), "warn": ("!", WARN), "bad": ("✕", BAD), "busy": ("…", ACCENT)}[kind]
        c = QColor(col)
        self.setText(sym)
        self.setStyleSheet(f"background: rgba({c.red()},{c.green()},{c.blue()},40); color:{col}; "
                           f"border-radius:11px; font-weight:800;")
        self.setFixedSize(22, 22)
        self.setAlignment(Qt.AlignCenter)


# ------------------------------------------------------------------------------ toast
class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)
        self.hide()
        self._eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._eff)
        self._fade = QPropertyAnimation(self._eff, b"opacity", self, duration=220)
        self._slide = QPropertyAnimation(self, b"pos", self, duration=260, easingCurve=QEasingCurve.OutBack)
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self._out)

    def show_msg(self, text, kind="info", ms=2800):
        col = {"info": ACCENT, "ok": OK, "warn": WARN, "bad": BAD}[kind]
        self.setStyleSheet(f"QLabel#toast {{ border-left: 4px solid {col}; }}")
        self.setText(text)
        self.adjustSize()
        self.resize(min(max(self.width() + 40, 260), self.parent().width() - 80), 44)
        x = (self.parent().width() - self.width()) // 2
        y_end = self.parent().height() - self.height() - 28
        self.move(x, y_end + 30)
        self.show()
        self.raise_()
        self._fade.stop()
        self._fade.setStartValue(self._eff.opacity() if self._timer.isActive() else 0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._slide.stop()
        self._slide.setStartValue(QPoint(x, y_end + 30))
        self._slide.setEndValue(QPoint(x, y_end))
        self._slide.start()
        self._timer.start(ms)

    def _out(self):
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()
        QTimer.singleShot(240, self.hide)


# ------------------------------------------------------------------------------ páginas com fade
class FadeStack(QStackedWidget):
    def fade_to(self, index):
        if index == self.currentIndex():
            return
        self.setCurrentIndex(index)
        w = self.currentWidget()
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", w, duration=240, easingCurve=QEasingCurve.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.finished.connect(lambda: w.setGraphicsEffect(None))
        anim.start()
        self._anim = anim


class Sidebar(QFrame):
    changed = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(210)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(14, 18, 14, 14)
        self.lay.setSpacing(4)
        self.buttons = []
        self.indicator = QFrame(self)
        self.indicator.setObjectName("navind")
        self.indicator.setFixedWidth(4)
        self._ind_anim = QPropertyAnimation(self.indicator, b"geometry", self, duration=260,
                                            easingCurve=QEasingCurve.OutCubic)

    def add(self, text):
        b = QPushButton(text)
        b.setObjectName("nav")
        b.setCheckable(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        i = len(self.buttons)
        b.clicked.connect(lambda: self.select(i))
        self.buttons.append(b)
        self.lay.addWidget(b)
        return b

    def select(self, i, animate=True):
        for j, b in enumerate(self.buttons):
            b.setChecked(j == i)
        b = self.buttons[i]
        target = QRect(4, b.y() + 8, 4, b.height() - 16)
        if animate and self.indicator.isVisible():
            self._ind_anim.stop()
            self._ind_anim.setStartValue(self.indicator.geometry())
            self._ind_anim.setEndValue(target)
            self._ind_anim.start()
        else:
            self.indicator.setGeometry(target)
        self.indicator.show()
        self.indicator.raise_()
        self.changed.emit(i)

    def current(self):
        for i, b in enumerate(self.buttons):
            if b.isChecked():
                return i
        return 0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, lambda: self.select(self.current(), animate=False) if self.buttons else None)


# ------------------------------------------------------------------------------ controle desenhado
B_UP, B_DOWN, B_LEFT, B_RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
B_START, B_BACK, B_LTHUMB, B_RTHUMB = 0x0010, 0x0020, 0x0040, 0x0080
B_LB, B_RB, B_GUIDE = 0x0100, 0x0200, 0x0400
B_A, B_B, B_X, B_Y = 0x1000, 0x2000, 0x4000, 0x8000


class GamepadView(QWidget):
    """Desenha um controle estilo DualShock com os botões acendendo em tempo real."""

    def __init__(self):
        super().__init__()
        self.state = None
        self.setMinimumSize(250, 160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(170)

    def set_state(self, st):
        if st != self.state:
            self.state = st
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = 260.0, 165.0
        s = min(self.width() / W, self.height() / H)
        p.translate((self.width() - W * s) / 2, (self.height() - H * s) / 2)
        p.scale(s, s)
        st = self.state
        on = st is not None
        b, lt, rt, lx, ly, rx, ry = st if on else (0, 0, 0, 0, 0, 0, 0)
        dim = 1.0 if on else 0.35

        def col(c, a=255):
            q = QColor(c)
            q.setAlpha(int(a * dim))
            return q

        lit = lambda mask: bool(b & mask)

        # gatilhos (barras)
        for x, val, name in ((38, lt, "L2"), (172, rt, "R2")):
            p.setPen(Qt.NoPen)
            p.setBrush(col("#1b1e26"))
            p.drawRoundedRect(QRectF(x, 2, 50, 10), 5, 5)
            if val:
                p.setBrush(col(ACCENT))
                p.drawRoundedRect(QRectF(x, 2, 50 * val / 255, 10), 5, 5)
        # ombros
        for x, mask in ((38, B_LB), (172, B_RB)):
            p.setBrush(col(ACCENT if lit(mask) else "#2a2f3d"))
            p.drawRoundedRect(QRectF(x, 16, 50, 9), 4, 4)
        # corpo
        body = QPainterPath()
        body.setFillRule(Qt.WindingFill)
        body.addRoundedRect(QRectF(22, 28, 216, 82), 34, 34)
        body.addEllipse(QRectF(20, 74, 70, 88))
        body.addEllipse(QRectF(170, 74, 70, 88))
        body = body.simplified()
        g = QLinearGradient(0, 28, 0, 160)
        g.setColorAt(0, col("#2b3040"))
        g.setColorAt(1, col("#1c1f29"))
        p.setBrush(g)
        p.setPen(QPen(col("#3a4152"), 1.5))
        p.drawPath(body)

        # D-pad
        cx, cy = 62, 62
        arms = ((B_UP, QRectF(cx - 8, cy - 26, 16, 20)), (B_DOWN, QRectF(cx - 8, cy + 6, 16, 20)),
                (B_LEFT, QRectF(cx - 26, cy - 8, 20, 16)), (B_RIGHT, QRectF(cx + 6, cy - 8, 20, 16)))
        p.setPen(Qt.NoPen)
        p.setBrush(col("#14161c"))
        p.drawRoundedRect(QRectF(cx - 8, cy - 8, 16, 16), 2, 2)
        for mask, r in arms:
            p.setBrush(col(ACCENT if lit(mask) else "#14161c"))
            p.drawRoundedRect(r, 3, 3)

        # botões de face (cores PlayStation)
        fx, fy = 198, 62
        faces = ((B_Y, (fx, fy - 20), "#40c057", "△"), (B_B, (fx + 20, fy), "#fa5252", "○"),
                 (B_A, (fx, fy + 20), "#5c7cfa", "✕"), (B_X, (fx - 20, fy), "#e64980", "□"))
        f = QFont("Segoe UI Symbol", 9)
        f.setBold(True)
        p.setFont(f)
        for mask, (x, y), c, sym in faces:
            pressed = lit(mask)
            p.setPen(Qt.NoPen)
            p.setBrush(col(c) if pressed else col("#14161c"))
            p.drawEllipse(QPointF(x, y), 10, 10)
            p.setPen(col("#ffffff" if pressed else c))
            p.drawText(QRectF(x - 10, y - 11, 20, 20), Qt.AlignCenter, sym)

        # select / start / analog
        p.setPen(Qt.NoPen)
        for x, mask in ((104, B_BACK), (140, B_START)):
            p.setBrush(col(ACCENT if lit(mask) else "#14161c"))
            p.drawRoundedRect(QRectF(x, 50, 16, 7), 3, 3)
        p.setBrush(col(WARN if lit(B_GUIDE) else "#14161c"))
        p.drawEllipse(QPointF(130, 76), 5, 5)

        # analógicos
        for (cx, cy), x, y, mask in (((96, 108), lx, ly, B_LTHUMB), ((164, 108), rx, ry, B_RTHUMB)):
            p.setBrush(col("#101218"))
            p.setPen(QPen(col("#3a4152"), 1.2))
            p.drawEllipse(QPointF(cx, cy), 19, 19)
            dx, dy = x / 32767 * 9, -y / 32767 * 9
            p.setPen(Qt.NoPen)
            p.setBrush(col(ACCENT if lit(mask) else "#4a5163"))
            p.drawEllipse(QPointF(cx + dx, cy + dy), 11, 11)
            if abs(x) > 3000 or abs(y) > 3000:
                p.setBrush(col(ACCENT, 140))
                p.drawEllipse(QPointF(cx + dx, cy + dy), 4, 4)

        if not on:
            p.setPen(QColor(MUTED))
            p.setFont(QFont("Segoe UI", 10, QFont.Bold))
            p.drawText(QRectF(0, 128, W, 30), Qt.AlignCenter, "desconectado")
