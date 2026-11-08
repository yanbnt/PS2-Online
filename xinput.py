"""Leitura de controles XInput (Xbox, ou PlayStation via DS4Windows/Steam) via ctypes."""
import ctypes
from ctypes import wintypes


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", ctypes.c_ubyte),
        ("bRightTrigger", ctypes.c_ubyte),
        ("sThumbLX", ctypes.c_short),
        ("sThumbLY", ctypes.c_short),
        ("sThumbRX", ctypes.c_short),
        ("sThumbRY", ctypes.c_short),
    ]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", wintypes.WORD), ("wRightMotorSpeed", wintypes.WORD)]


_dll = None
for _name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
    try:
        _dll = ctypes.WinDLL(_name)
        break
    except OSError:
        continue

# Botões (iguais no XInput e no ViGEm/XUSB)
DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT = 0x0001, 0x0002, 0x0004, 0x0008
START, BACK, LTHUMB, RTHUMB = 0x0010, 0x0020, 0x0040, 0x0080
LB, RB, GUIDE = 0x0100, 0x0200, 0x0400
A, B, X, Y = 0x1000, 0x2000, 0x4000, 0x8000


def get_state(index: int):
    """Retorna (buttons, lt, rt, lx, ly, rx, ry) ou None se desconectado."""
    if _dll is None:
        return None
    st = XINPUT_STATE()
    if _dll.XInputGetState(index, ctypes.byref(st)) != 0:
        return None
    g = st.Gamepad
    return (g.wButtons, g.bLeftTrigger, g.bRightTrigger, g.sThumbLX, g.sThumbLY, g.sThumbRX, g.sThumbRY)


def set_vibration(index: int, large: int, small: int):
    if _dll is None:
        return
    v = XINPUT_VIBRATION(min(65535, large * 257), min(65535, small * 257))
    _dll.XInputSetState(index, ctypes.byref(v))


def connected():
    return [i for i in range(4) if get_state(i) is not None]
