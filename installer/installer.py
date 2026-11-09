"""Instalador do PS2 Online (gera um .exe único com o app embutido)."""
import ctypes
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import winreg
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP = "PS2 Online"
VERSION = "1.2"
EXE = "PS2 Online.exe"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PS2Online"
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
PAYLOAD = BASE / "payload.zip"
NO_WINDOW = 0x08000000


def known_folder(csidl):
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value)


DESKTOP = known_folder(0x10)                      # CSIDL_DESKTOPDIRECTORY
START_MENU = known_folder(0x02)                   # CSIDL_PROGRAMS
DEFAULT_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / APP


def vigem_installed() -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\ViGEmBus"))
        return True
    except OSError:
        return False


def install_vigem(dest: Path) -> bool:
    """Roda o instalador do ViGEmBus (que vem junto do app) como administrador e espera terminar."""
    arch = "x64" if sys.maxsize > 2 ** 32 else "x86"
    msi = dest / "_internal" / "vgamepad" / "win" / "vigem" / "install" / arch / f"ViGEmBusSetup_{arch}.msi"
    if not msi.exists():
        raise FileNotFoundError(f"instalador do driver não encontrado: {msi}")

    class SEI(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("fMask", ctypes.c_ulong), ("hwnd", ctypes.c_void_p),
                    ("lpVerb", ctypes.c_wchar_p), ("lpFile", ctypes.c_wchar_p), ("lpParameters", ctypes.c_wchar_p),
                    ("lpDirectory", ctypes.c_wchar_p), ("nShow", ctypes.c_int), ("hInstApp", ctypes.c_void_p),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
                    ("dwHotKey", ctypes.c_ulong), ("hIcon", ctypes.c_void_p), ("hProcess", ctypes.c_void_p)]

    sei = SEI(cbSize=ctypes.sizeof(SEI), fMask=0x40, lpVerb="runas", lpFile="msiexec.exe",
              lpParameters=f'/i "{msi}" /passive /norestart', nShow=1)   # 0x40 = SEE_MASK_NOCLOSEPROCESS
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
        return False   # usuário recusou o pedido de administrador
    ctypes.windll.kernel32.WaitForSingleObject(ctypes.c_void_p(sei.hProcess), 0xFFFFFFFF)
    ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(sei.hProcess))
    return vigem_installed()


def app_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE}", "/NH"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    return EXE.lower() in out.lower()


def make_shortcut(lnk: Path, target: Path):
    lnk.parent.mkdir(parents=True, exist_ok=True)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:PS2_LNK);"
          "$s.TargetPath=$env:PS2_TARGET;$s.WorkingDirectory=$env:PS2_DIR;"
          "$s.IconLocation=$env:PS2_TARGET+',0';$s.Description='Multiplayer do PCSX2 pela internet';$s.Save()")
    env = dict(os.environ, PS2_LNK=str(lnk), PS2_TARGET=str(target), PS2_DIR=str(target.parent))
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, check=True,
                   creationflags=NO_WINDOW)


def write_uninstaller(dest: Path, shortcuts):
    lines = ["@echo off", "chcp 65001 >nul", f"echo Desinstalando {APP}...",
             f'taskkill /im "{EXE}" /f >nul 2>nul', "timeout /t 1 /nobreak >nul"]
    lines += [f'del /f /q "{s}" >nul 2>nul' for s in shortcuts]
    lines.append(f'reg delete "HKCU\\{UNINSTALL_KEY}" /f >nul 2>nul')
    # mesma linha: o cmd já leu tudo antes de apagar a própria pasta
    lines.append(f'cd /d "%TEMP%" & rmdir /s /q "{dest}" & echo {APP} removido. & timeout /t 2 >nul & exit /b')
    (dest / "Desinstalar.cmd").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")


def register(dest: Path, size_kb: int):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        exe = str(dest / EXE)
        for name, val in (("DisplayName", APP), ("DisplayVersion", VERSION), ("Publisher", APP),
                          ("DisplayIcon", exe), ("InstallLocation", str(dest)),
                          ("UninstallString", f'"{dest / "Desinstalar.cmd"}"')):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def install(dest: Path, desktop=True, shortcuts=True, registry=True, progress=lambda f, t: None):
    dest.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(dest / "_internal", ignore_errors=True)       # atualização limpa
    with zipfile.ZipFile(PAYLOAD) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        total = len(members)
        size = 0
        for i, m in enumerate(members, 1):
            rel = Path(*Path(m.filename).parts[1:])                  # tira a pasta "PS2 Online/"
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            size += m.file_size
            if i % 10 == 0 or i == total:
                progress(i, total)
    created = []
    if shortcuts:
        sm = START_MENU / f"{APP}.lnk"
        make_shortcut(sm, dest / EXE)
        created.append(sm)
        if desktop:
            dk = DESKTOP / f"{APP}.lnk"
            make_shortcut(dk, dest / EXE)
            created.append(dk)
    write_uninstaller(dest, created)
    if registry:
        register(dest, size // 1024)


# ----------------------------------------------------------------------------- interface
BG, CARD, FG, MUTED, ACCENT = "#14161c", "#1c1f27", "#e6e8ee", "#8c93a6", "#4c6ef5"


class InstallerUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Instalar {APP}")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        try:
            self.root.iconbitmap(str(BASE / "icon.ico"))
        except tk.TclError:
            pass
        st = ttk.Style(self.root)
        st.theme_use("clam")
        st.configure("TProgressbar", troughcolor=CARD, background=ACCENT, bordercolor=CARD,
                     lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)
        st.configure("TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 10))
        st.map("TCheckbutton", background=[("active", BG)], indicatorcolor=[("selected", ACCENT), ("!selected", CARD)])

        pad = dict(padx=24)
        tk.Label(self.root, text="PS2", fg=FG, bg=BG, font=("Segoe UI Black", 22)).grid(row=0, column=0, sticky="w",
                                                                                        padx=(24, 0), pady=(20, 0))
        tk.Label(self.root, text="Online", fg=ACCENT, bg=BG, font=("Segoe UI Black", 22)).grid(row=0, column=1,
                                                                                               sticky="w", pady=(20, 0))
        tk.Label(self.root, text="Multiplayer local do PCSX2 pela internet", fg=MUTED, bg=BG,
                 font=("Segoe UI", 10)).grid(row=1, column=0, columnspan=3, sticky="w", **pad)

        tk.Label(self.root, text="Pasta de instalação:", fg=FG, bg=BG, font=("Segoe UI", 10)).grid(
            row=2, column=0, columnspan=3, sticky="w", padx=24, pady=(18, 4))
        self.dir = tk.StringVar(value=str(DEFAULT_DIR))
        e = tk.Entry(self.root, textvariable=self.dir, width=52, bg=CARD, fg=FG, insertbackground=FG,
                     relief="flat", font=("Segoe UI", 10))
        e.grid(row=3, column=0, columnspan=2, sticky="we", padx=(24, 6), ipady=5)
        self.btn_dir = tk.Button(self.root, text="Alterar…", command=self.choose, bg=CARD, fg=FG, relief="flat",
                                 activebackground="#262b38", activeforeground=FG, font=("Segoe UI", 10), padx=10)
        self.btn_dir.grid(row=3, column=2, sticky="e", padx=(0, 24))

        self.desktop = tk.BooleanVar(value=True)
        self.launch = tk.BooleanVar(value=True)
        self.has_vigem = vigem_installed()
        self.vigem = tk.BooleanVar(value=not self.has_vigem)
        ttk.Checkbutton(self.root, text="Criar atalho na Área de Trabalho", variable=self.desktop).grid(
            row=4, column=0, columnspan=3, sticky="w", padx=24, pady=(14, 2))
        vtext = ("Driver de controle virtual (ViGEmBus) — já instalado ✓" if self.has_vigem else
                 "Instalar driver de controle virtual (ViGEmBus) — necessário para HOSPEDAR")
        cb = ttk.Checkbutton(self.root, text=vtext, variable=self.vigem)
        cb.grid(row=5, column=0, columnspan=3, sticky="w", padx=24, pady=2)
        if self.has_vigem:
            cb.state(["disabled"])
        ttk.Checkbutton(self.root, text=f"Abrir o {APP} ao terminar", variable=self.launch).grid(
            row=6, column=0, columnspan=3, sticky="w", padx=24, pady=2)
        tk.Label(self.root, text="O driver é de código aberto (licença BSD). O Windows vai pedir permissão de "
                                 "administrador para instalá-lo.", fg=MUTED, bg=BG, font=("Segoe UI", 8),
                 wraplength=460, justify="left").grid(row=7, column=0, columnspan=3, sticky="w", padx=24)

        self.bar = ttk.Progressbar(self.root, length=460, mode="determinate", style="TProgressbar")
        self.bar.grid(row=8, column=0, columnspan=3, padx=24, pady=(16, 4), sticky="we")
        self.status = tk.Label(self.root, text="Pronto para instalar.", fg=MUTED, bg=BG, font=("Segoe UI", 9),
                               wraplength=460, justify="left")
        self.status.grid(row=9, column=0, columnspan=3, sticky="w", padx=24)

        row = tk.Frame(self.root, bg=BG)
        row.grid(row=10, column=0, columnspan=3, sticky="e", padx=24, pady=(14, 20))
        self.btn_cancel = tk.Button(row, text="Cancelar", command=self.root.destroy, bg=CARD, fg=FG, relief="flat",
                                    activebackground="#262b38", activeforeground=FG, font=("Segoe UI", 10),
                                    padx=16, pady=4)
        self.btn_cancel.pack(side="left", padx=(0, 8))
        self.btn_ok = tk.Button(row, text="Instalar", command=self.start, bg=ACCENT, fg="white", relief="flat",
                                activebackground="#3b5bdb", activeforeground="white",
                                font=("Segoe UI Semibold", 10), padx=20, pady=4)
        self.btn_ok.pack(side="left")
        self.done = False

    def choose(self):
        d = filedialog.askdirectory(initialdir=str(Path(self.dir.get()).parent))
        if d:
            self.dir.set(str(Path(d) / APP))

    def start(self):
        if self.done:
            self.finish()
            return
        if app_running():
            messagebox.showwarning(APP, f"Feche o {APP} antes de instalar ou atualizar.")
            return
        for w in (self.btn_ok, self.btn_dir, self.btn_cancel):
            w.configure(state="disabled")
        self.status.configure(text="Instalando…")
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        dest = Path(self.dir.get())

        def prog(i, t):
            self.root.after(0, lambda: (self.bar.configure(maximum=t, value=i),
                                        self.status.configure(text=f"Copiando arquivos… {i * 100 // t}%")))

        try:
            install(dest, desktop=self.desktop.get(), progress=prog)
        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda: self._failed(msg))
            return
        driver_note = ""
        if self.vigem.get() and not self.has_vigem:
            self.root.after(0, lambda: self.status.configure(
                text="Instalando o driver ViGEmBus… (aceite o pedido de administrador do Windows)"))
            try:
                ok = install_vigem(dest)
            except Exception as e:
                ok = False
                driver_note = f" Driver: {e}"
            if not ok and not driver_note:
                driver_note = (" O driver não foi instalado — sem ele dá para ENTRAR em salas, mas não hospedar. "
                               "O app oferece instalar de novo ao clicar em Abrir sala.")
        self.root.after(0, lambda: self._ok(driver_note))

    def _failed(self, msg):
        messagebox.showerror(APP, f"Não foi possível instalar:\n{msg}")
        for w in (self.btn_ok, self.btn_dir, self.btn_cancel):
            w.configure(state="normal")
        self.status.configure(text="Falhou.")

    def _ok(self, note=""):
        self.done = True
        self.bar.configure(value=self.bar["maximum"])
        self.status.configure(text=f"{APP} instalado! Para remover: Configurações → Aplicativos instalados."
                              + note, fg="#e8a33d" if note else MUTED)
        self.btn_ok.configure(state="normal", text="Concluir")

    def finish(self):
        if self.launch.get():
            exe = Path(self.dir.get()) / EXE
            subprocess.Popen([str(exe)], cwd=str(exe.parent))
        self.root.destroy()

    def run(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        self.root.geometry(f"+{(self.root.winfo_screenwidth() - w) // 2}+{(self.root.winfo_screenheight() - h) // 3}")
        self.root.mainloop()


def main():
    args = sys.argv[1:]
    if "--silent" in args:          # usado para testes: --silent --dir <pasta> [--no-shortcuts]
        dest = Path(args[args.index("--dir") + 1]) if "--dir" in args else DEFAULT_DIR
        no_sc = "--no-shortcuts" in args
        install(dest, shortcuts=not no_sc, registry=not no_sc)
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    InstallerUI().run()


if __name__ == "__main__":
    main()
