"""Integração com o PCSX2: localizar, abrir jogos, configurar controles e achar a janela."""
import ctypes
import os
import shutil
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

DEFAULT_EXE = r"C:\Program Files\PCSX2\pcsx2-qt.exe"
GAME_EXTS = {".iso", ".chd", ".cso", ".zso", ".gz", ".cue", ".elf", ".mdf", ".img"}

# Seções de controle usadas pelos convidados, por modo de multitap.
# Ordem das seções no PCSX2: Pad1=1A, Pad2=2A, Pad3=1B, Pad4=1C, Pad5=1D, Pad6=2B, Pad7=2C, Pad8=2D
MULTITAP_MODES = {
    "off": {"label": "Sem multitap (até 2 jogadores)", "slots": ["Pad2"], "mt1": False, "mt2": False},
    "port1": {"label": "Multitap na porta 1 (até 4)", "slots": ["Pad3", "Pad4", "Pad5"], "mt1": True, "mt2": False},
    "port2": {"label": "Multitap na porta 2 (até 4)", "slots": ["Pad2", "Pad6", "Pad7"], "mt1": False, "mt2": True},
}
SLOT_NAMES = {"Pad1": "1A", "Pad2": "2A", "Pad3": "1B", "Pad4": "1C", "Pad5": "1D",
              "Pad6": "2B", "Pad7": "2C", "Pad8": "2D"}

DS2_BINDINGS = [
    ("Up", "DPadUp"), ("Right", "DPadRight"), ("Down", "DPadDown"), ("Left", "DPadLeft"),
    ("Triangle", "FaceNorth"), ("Circle", "FaceEast"), ("Cross", "FaceSouth"), ("Square", "FaceWest"),
    ("Select", "Back"), ("Start", "Start"), ("L1", "LeftShoulder"), ("L2", "+LeftTrigger"),
    ("R1", "RightShoulder"), ("R2", "+RightTrigger"), ("L3", "LeftStick"), ("R3", "RightStick"),
    ("LUp", "-LeftY"), ("LRight", "+LeftX"), ("LDown", "+LeftY"), ("LLeft", "-LeftX"),
    ("RUp", "-RightY"), ("RRight", "+RightX"), ("RDown", "+RightY"), ("RLeft", "-RightX"),
    ("Analog", "Guide"), ("LargeMotor", "LargeMotor"), ("SmallMotor", "SmallMotor"),
]


# ---------------------------------------------------------------- caminhos / ini
def find_ini(exe_path: str) -> Path:
    exe_dir = Path(exe_path).parent
    if (exe_dir / "portable.ini").exists() or (exe_dir / "portable.txt").exists():
        return exe_dir / "inis" / "PCSX2.ini"
    docs = Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents" / "PCSX2" / "inis" / "PCSX2.ini"
    return docs


def _read_sections(path: Path):
    """Lê o ini preservando chaves repetidas. Retorna lista [(nome, [linhas])]."""
    sections = [("", [])]
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            sections.append((s[1:-1], []))
        else:
            sections[-1][1].append(line)
    return sections


def _write_sections(path: Path, sections):
    out = []
    for name, lines in sections:
        if name:
            out.append(f"[{name}]")
        out.extend(lines)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _set_key(lines, key, value):
    for i, l in enumerate(lines):
        if l.split("=", 1)[0].strip() == key:
            lines[i] = f"{key} = {value}"
            return
    # insere antes das linhas em branco finais
    idx = len(lines)
    while idx > 0 and not lines[idx - 1].strip():
        idx -= 1
    lines.insert(idx, f"{key} = {value}")


def game_folders(exe_path: str):
    ini = find_ini(exe_path)
    if not ini.exists():
        return []
    folders = []
    for name, lines in _read_sections(ini):
        if name == "GameList":
            for l in lines:
                if "=" in l:
                    k, v = (x.strip() for x in l.split("=", 1))
                    if k in ("Paths", "RecursivePaths") and v:
                        folders.append(v)
    return folders


def scan_games(folders):
    games = []
    seen = set()
    for f in folders:
        p = Path(f)
        if not p.is_dir():
            continue
        try:
            for file in p.rglob("*"):
                if file.suffix.lower() in GAME_EXTS and file.is_file():
                    key = str(file).lower()
                    if key not in seen:
                        seen.add(key)
                        games.append(str(file))
        except OSError:
            pass
    return sorted(games, key=lambda x: Path(x).stem.lower())


def configure_guest_pads(exe_path: str, sdl_base: int, mode: str, n_guests: int):
    """Liga as portas dos convidados aos controles virtuais SDL-<base+i>. Faz backup do ini."""
    ini = find_ini(exe_path)
    if not ini.exists():
        raise FileNotFoundError(f"Não achei o PCSX2.ini em {ini}. Abra o PCSX2 uma vez primeiro.")
    backup = ini.with_name("PCSX2.ini.bak-ps2online")
    shutil.copy2(ini, backup)
    sections = _read_sections(ini)
    by_name = {n: l for n, l in sections}
    m = MULTITAP_MODES[mode]

    pad = by_name.get("Pad")
    if pad is None:
        pad = []
        sections.append(("Pad", pad))
    _set_key(pad, "MultitapPort1", "true" if m["mt1"] else "false")
    _set_key(pad, "MultitapPort2", "true" if m["mt2"] else "false")

    done = []
    for i, slot in enumerate(m["slots"][:n_guests]):
        dev = f"SDL-{sdl_base + i}"
        lines = ["Type = DualShock2", "Deadzone = 0", "AxisScale = 1.33",
                 "LargeMotorScale = 1", "SmallMotorScale = 1", "PressureModifier = 0.5"]
        lines += [f"{k} = {dev}/{v}" for k, v in DS2_BINDINGS]
        lines += ["", ""]
        if slot in by_name:
            by_name[slot][:] = lines
        else:
            sections.append((slot, lines))
        done.append((slot, dev))
    _write_sections(ini, sections)
    return ini, backup, done


# ---------------------------------------------------------------- processo
def is_running() -> bool:
    return bool(find_pids())


def launch(exe_path: str, game: str | None, fullscreen=False):
    args = [exe_path]
    if fullscreen:
        args.append("-fullscreen")
    if game:
        args += ["--", game]
    return subprocess.Popen(args, cwd=str(Path(exe_path).parent))


# ---------------------------------------------------------------- janelas (Win32)
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
psapi.EnumProcesses.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]


def _proc_name(pid: int) -> str:
    h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def find_pids(name="pcsx2"):
    arr = (wintypes.DWORD * 4096)()
    needed = wintypes.DWORD()
    psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed))
    count = needed.value // ctypes.sizeof(wintypes.DWORD)
    return {arr[i] for i in range(count) if arr[i] and _proc_name(arr[i]).startswith(name)}


def _client_rect_screen(hwnd):
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = r.right - r.left, r.bottom - r.top
    if w < 64 or h < 64:
        return None
    return {"left": pt.x, "top": pt.y, "width": w, "height": h}


def window_title(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def find_game_area(game_area_only=True):
    """Acha a região de tela (left, top, width, height) da imagem do jogo no PCSX2.

    Retorna (rect, hwnd) ou (None, None). Prefere a maior janela-filha nativa
    (superfície de renderização) dentro da maior janela do PCSX2.
    """
    pids = find_pids()
    if not pids:
        return None, None
    tops = []

    def cb(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            rc = _client_rect_screen(hwnd)
            if rc:
                tops.append((rc["width"] * rc["height"], hwnd, rc))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not tops:
        return None, None
    # Prefere a janela cujo título não é só "PCSX2" (janela com jogo rodando) e maior área
    tops.sort(key=lambda t: t[0], reverse=True)
    _, top_hwnd, top_rc = tops[0]
    if not game_area_only:
        return top_rc, top_hwnd

    children = []

    def ccb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            rc = _client_rect_screen(hwnd)
            if rc:
                children.append((rc["width"] * rc["height"], hwnd, rc))
        return True

    user32.EnumChildWindows(top_hwnd, WNDENUMPROC(ccb), 0)
    top_area = top_rc["width"] * top_rc["height"]
    good = [c for c in children if c[0] >= 0.35 * top_area]
    if good:
        good.sort(key=lambda t: t[0], reverse=True)
        return good[0][2], good[0][1]
    return top_rc, top_hwnd


def is_window_minimized(hwnd) -> bool:
    return bool(hwnd and user32.IsIconic(hwnd))
