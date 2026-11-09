"""Captura do som do PC por processo (Windows 10 2004+ / Windows 11), via WASAPI "process loopback".

Usado pelo host para transmitir o som do jogo SEM o som do próprio PS2 Online (a voz da chamada),
o que evita que os convidados ouçam a própria voz de volta (eco).

    cap = ProcessLoopback(pid=os.getpid(), exclude=True, callback=lambda pcm_bytes: ...)
    cap.start() ... cap.stop()

Entrega PCM 16-bit, 48 kHz, estéreo, em blocos de ~10 ms.
"""
import ctypes
import sys
import threading
import time
from ctypes import HRESULT, POINTER, Structure, Union, byref, c_long, c_ubyte, c_uint32, c_uint64, c_ulong, c_ushort, c_void_p, c_wchar_p

RATE = 48000
CHANNELS = 2

_iface = None


def _interfaces():
    """Define as interfaces COM uma vez (comtypes é importado só dentro da thread de captura)."""
    global _iface
    if _iface:
        return _iface
    from comtypes import COMMETHOD, GUID, IUnknown

    class IActivateAudioInterfaceAsyncOperation(IUnknown):
        _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
        _methods_ = [COMMETHOD([], HRESULT, "GetActivateResult",
                               (["out"], POINTER(c_long), "activateResult"),
                               (["out"], POINTER(POINTER(IUnknown)), "activatedInterface"))]

    class IActivateAudioInterfaceCompletionHandler(IUnknown):
        _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
        _methods_ = [COMMETHOD([], HRESULT, "ActivateCompleted",
                               (["in"], POINTER(IActivateAudioInterfaceAsyncOperation), "operation"))]

    class IAgileObject(IUnknown):
        _iid_ = GUID("{94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90}")
        _methods_ = []

    class WAVEFORMATEX(Structure):
        _pack_ = 1
        _fields_ = [("wFormatTag", c_ushort), ("nChannels", c_ushort), ("nSamplesPerSec", c_ulong),
                    ("nAvgBytesPerSec", c_ulong), ("nBlockAlign", c_ushort), ("wBitsPerSample", c_ushort),
                    ("cbSize", c_ushort)]

    class IAudioClient(IUnknown):
        _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Initialize", (["in"], c_uint32, "ShareMode"), (["in"], c_ulong, "StreamFlags"),
                      (["in"], ctypes.c_longlong, "hnsBufferDuration"), (["in"], ctypes.c_longlong, "hnsPeriodicity"),
                      (["in"], POINTER(WAVEFORMATEX), "pFormat"), (["in"], c_void_p, "AudioSessionGuid")),
            COMMETHOD([], HRESULT, "GetBufferSize", (["out"], POINTER(c_uint32), "n")),
            COMMETHOD([], HRESULT, "GetStreamLatency", (["out"], POINTER(ctypes.c_longlong), "lat")),
            COMMETHOD([], HRESULT, "GetCurrentPadding", (["out"], POINTER(c_uint32), "pad")),
            COMMETHOD([], HRESULT, "IsFormatSupported", (["in"], c_uint32, "m"), (["in"], c_void_p, "f"),
                      (["out"], POINTER(c_void_p), "c")),
            COMMETHOD([], HRESULT, "GetMixFormat", (["out"], POINTER(c_void_p), "f")),
            COMMETHOD([], HRESULT, "GetDevicePeriod", (["out"], POINTER(ctypes.c_longlong), "a"),
                      (["out"], POINTER(ctypes.c_longlong), "b")),
            COMMETHOD([], HRESULT, "Start"),
            COMMETHOD([], HRESULT, "Stop"),
            COMMETHOD([], HRESULT, "Reset"),
            COMMETHOD([], HRESULT, "SetEventHandle", (["in"], c_void_p, "h")),
            COMMETHOD([], HRESULT, "GetService", (["in"], POINTER(GUID), "riid"),
                      (["out"], POINTER(POINTER(IUnknown)), "ppv")),
        ]

    class IAudioCaptureClient(IUnknown):
        _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetBuffer", (["out"], POINTER(POINTER(c_ubyte)), "data"),
                      (["out"], POINTER(c_uint32), "frames"), (["out"], POINTER(c_ulong), "flags"),
                      (["out"], POINTER(c_uint64), "devpos"), (["out"], POINTER(c_uint64), "qpcpos")),
            COMMETHOD([], HRESULT, "ReleaseBuffer", (["in"], c_uint32, "frames")),
            COMMETHOD([], HRESULT, "GetNextPacketSize", (["out"], POINTER(c_uint32), "frames")),
        ]

    class PROCESS_LOOPBACK_PARAMS(Structure):
        _fields_ = [("TargetProcessId", c_ulong), ("ProcessLoopbackMode", c_uint32)]

    class ACTIVATION_PARAMS(Structure):
        _fields_ = [("ActivationType", c_uint32), ("ProcessLoopbackParams", PROCESS_LOOPBACK_PARAMS)]

    class BLOB(Structure):
        _fields_ = [("cbSize", c_ulong), ("pBlobData", c_void_p)]

    class PROPVARIANT(Structure):
        _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("blob", BLOB)]

    _iface = dict(GUID=GUID, IUnknown=IUnknown, Op=IActivateAudioInterfaceAsyncOperation,
                  Handler=IActivateAudioInterfaceCompletionHandler, Agile=IAgileObject,
                  WAVEFORMATEX=WAVEFORMATEX, IAudioClient=IAudioClient, IAudioCaptureClient=IAudioCaptureClient,
                  PARAMS=ACTIVATION_PARAMS, PROPVARIANT=PROPVARIANT)
    return _iface


def supported() -> bool:
    v = sys.getwindowsversion()
    return v.major >= 10 and v.build >= 20348


class ProcessLoopback:
    def __init__(self, pid, exclude=True, callback=None):
        self.pid = pid
        self.exclude = exclude
        self.callback = callback or (lambda b: None)
        self.running = False
        self.error = None
        self._ready = threading.Event()
        self._thread = None

    def start(self, timeout=5):
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        if self.error:
            raise RuntimeError(self.error)
        if not self._ready.is_set():
            raise RuntimeError("tempo esgotado ao iniciar a captura de áudio")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(2)

    def _run(self):
        sys.coinit_flags = 0  # MTA nesta thread
        try:
            import comtypes
            from comtypes import COMObject
            comtypes.CoInitializeEx(0)
            I = _interfaces()
            done = threading.Event()

            class Handler(COMObject):
                _com_interfaces_ = [I["Handler"], I["Agile"]]

                def ActivateCompleted(self, operation):
                    done.set()
                    return 0

            params = I["PARAMS"]()
            params.ActivationType = 1  # AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK
            params.ProcessLoopbackParams.TargetProcessId = self.pid
            params.ProcessLoopbackParams.ProcessLoopbackMode = 1 if self.exclude else 0
            pv = I["PROPVARIANT"]()
            pv.vt = 65  # VT_BLOB
            pv.blob.cbSize = ctypes.sizeof(params)
            pv.blob.pBlobData = ctypes.cast(byref(params), c_void_p)

            handler = Handler()
            fn = ctypes.WinDLL("Mmdevapi").ActivateAudioInterfaceAsync
            fn.restype = c_long
            fn.argtypes = [c_wchar_p, POINTER(I["GUID"]), c_void_p, c_void_p, POINTER(POINTER(I["Op"]))]
            op = POINTER(I["Op"])()
            hptr = handler.QueryInterface(I["Handler"])
            iid = I["IAudioClient"]._iid_
            hr = fn("VAD\\Process_Loopback", byref(iid), byref(pv), hptr, byref(op))
            if hr < 0:
                raise OSError(f"ActivateAudioInterfaceAsync falhou (0x{hr & 0xFFFFFFFF:08X})")
            if not done.wait(5):
                raise OSError("ativação de áudio não respondeu")
            hr2, unk = op.GetActivateResult()
            if (hr2 or 0) < 0:
                raise OSError(f"ativação de áudio falhou (0x{hr2 & 0xFFFFFFFF:08X})")
            client = unk.QueryInterface(I["IAudioClient"])
            fmt = I["WAVEFORMATEX"](1, CHANNELS, RATE, RATE * CHANNELS * 2, CHANNELS * 2, 16, 0)
            # LOOPBACK | AUTOCONVERTPCM | SRC_DEFAULT_QUALITY ; buffer de 100 ms
            client.Initialize(0, 0x00020000 | 0x80000000 | 0x08000000, 1_000_000, 0, byref(fmt), None)
            svc = client.GetService(byref(I["IAudioCaptureClient"]._iid_))
            cap = svc.QueryInterface(I["IAudioCaptureClient"])
            client.Start()
            self._ready.set()
            block = CHANNELS * 2
            while self.running:
                n = cap.GetNextPacketSize()
                if not n:
                    time.sleep(0.005)
                    continue
                while n and self.running:
                    data, frames, flags, _, _ = cap.GetBuffer()
                    if frames:
                        if flags & 0x2:  # AUDCLNT_BUFFERFLAGS_SILENT
                            chunk = bytes(frames * block)
                        else:
                            chunk = ctypes.string_at(data, frames * block)
                        try:
                            self.callback(chunk)
                        except Exception:
                            pass
                    cap.ReleaseBuffer(frames)
                    n = cap.GetNextPacketSize()
            client.Stop()
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            self._ready.set()
