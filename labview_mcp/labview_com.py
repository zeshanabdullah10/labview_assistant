import functools
import os
import re
import shutil
import tempfile
import threading
import time
import pythoncom
import win32com.client
from win32com.client import VARIANT

_EXEC_STATES = {0: "Bad", 1: "Idle", 2: "RunTopLevel", 3: "Running", 4: "Paused"}
_EXEC_PRIORITIES = {
    0: "Normal", 1: "AboveNormal", 2: "BelowNormal",
    3: "High", 4: "Background", 5: "RealTime",
}

_com_init = threading.local()


def _ensure_com():
    if not getattr(_com_init, "done", False):
        pythoncom.CoInitialize()
        _com_init.done = True


def _normalize_path(path: str) -> str:
    if not isinstance(path, str):
        return path
    path = path.replace("/", "\\")
    path = re.sub(r"\\+", lambda m: "\\" if len(m.group(0)) == 1 else "\\", path)
    return path


class LabVIEWCOMError(Exception):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


def _handle_com_error(e):
    code = e.args[0] if e.args else 0
    if code == -2147023170:
        raise LabVIEWCOMError("LabVIEW is not responding. Ensure LabVIEW is running.", code)
    elif code == -2147467259:
        raise LabVIEWCOMError(f"LabVIEW error: {getattr(e, 'exceptext', str(e))}", code)
    else:
        raise LabVIEWCOMError(f"COM error {code}: {e}", code)


class LabVIEWClient:
    def __init__(self):
        self._connected = False
        self._vi_cache = {}

    def connect(self):
        _ensure_com()
        if self._connected:
            return
        try:
            win32com.client.dynamic.Dispatch("LabVIEW.Application")
            self._connected = True
        except Exception as e:
            raise LabVIEWCOMError(f"Cannot connect to LabVIEW: {e}")

    def get_version(self) -> str:
        _ensure_com()
        return win32com.client.dynamic.Dispatch("LabVIEW.Application").Version

    def get_vi(self, path: str):
        _ensure_com()
        path = _normalize_path(path)
        if path in self._vi_cache:
            cached = self._vi_cache[path]
            try:
                cached._vi.Name
                return cached
            except Exception:
                del self._vi_cache[path]
        try:
            lv = win32com.client.dynamic.Dispatch("LabVIEW.Application")
            vi_ref = lv.GetVIReference(path)
        except Exception as e:
            _handle_com_error(e)
        if vi_ref is None:
            raise LabVIEWCOMError(f"Cannot open VI reference: {path}")
        time.sleep(0.3)
        wrapper = VIWrapper(vi_ref, path)
        self._vi_cache[path] = wrapper
        return wrapper

    def clear_vi_cache(self):
        self._vi_cache.clear()


class VIWrapper:
    def __init__(self, vi_ref, path: str):
        self._vi = vi_ref
        self._oleobj = vi_ref._oleobj_
        self._path = path

    def get_name(self) -> str:
        try:
            return self._vi.Name
        except Exception as e:
            _handle_com_error(e)

    def get_path(self) -> str:
        try:
            return self._vi.Path
        except Exception as e:
            _handle_com_error(e)

    def get_description(self) -> str:
        try:
            return self._vi.Description or ""
        except Exception as e:
            _handle_com_error(e)

    def get_revision(self) -> int:
        try:
            return self._vi.RevisionNumber
        except Exception as e:
            _handle_com_error(e)

    def get_is_reentrant(self) -> bool:
        try:
            return bool(self._vi.IsReentrant)
        except Exception as e:
            _handle_com_error(e)

    def get_exec_state(self) -> str:
        try:
            return _EXEC_STATES.get(self._vi.ExecState, str(self._vi.ExecState))
        except Exception as e:
            _handle_com_error(e)

    def get_exec_priority(self) -> str:
        try:
            return _EXEC_PRIORITIES.get(self._vi.ExecPriority, str(self._vi.ExecPriority))
        except Exception as e:
            _handle_com_error(e)

    def get_bd_size(self) -> int:
        try:
            return self._vi.BDSize
        except Exception as e:
            _handle_com_error(e)

    def get_code_size(self) -> int:
        try:
            return self._vi.CodeSize
        except Exception as e:
            _handle_com_error(e)

    def get_data_size(self) -> int:
        try:
            return self._vi.DataSize
        except Exception as e:
            _handle_com_error(e)

    def get_callees(self) -> list:
        try:
            return list(self._vi.Callees)
        except Exception as e:
            _handle_com_error(e)

    def get_callers(self) -> list:
        try:
            return list(self._vi.Callers)
        except Exception as e:
            _handle_com_error(e)

    def get_history(self) -> str:
        try:
            return self._vi.HistoryText or ""
        except Exception as e:
            _handle_com_error(e)

    def export_strings(self) -> str:
        tmp = os.path.join(tempfile.gettempdir(), f"lv_{os.urandom(8).hex()}.xml")
        try:
            self._oleobj.Invoke(1204, 0, pythoncom.DISPATCH_METHOD, True, tmp, 1)
            if not os.path.exists(tmp):
                raise LabVIEWCOMError("ExportVIStringsUTF8 produced no output file")
            with open(tmp, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except LabVIEWCOMError:
            raise
        except Exception as e:
            _handle_com_error(e)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _print_to_image(self, panel: int) -> bytes:
        tmpdir = tempfile.mkdtemp(prefix="lv_mcp_")
        try:
            basename = os.path.splitext(os.path.basename(self._path))[0]
            html_path = os.path.join(tmpdir, f"{basename}.html")
            self._oleobj.Invoke(1006, 0, pythoncom.DISPATCH_METHOD, True, html_path, panel)
            for f in os.listdir(tmpdir):
                if f.lower().endswith(".png"):
                    with open(os.path.join(tmpdir, f), "rb") as fh:
                        return fh.read()
            raise LabVIEWCOMError("PrintVIToHTML produced no PNG output")
        except LabVIEWCOMError:
            raise
        except Exception as e:
            _handle_com_error(e)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def get_front_panel_image(self) -> bytes:
        return self._print_to_image(0)

    def get_block_diagram_image(self) -> bytes:
        return self._print_to_image(1)

    def get_control_value(self, name: str):
        try:
            return self._vi.GetControlValue(name)
        except Exception as e:
            _handle_com_error(e)

    def set_control_value(self, name: str, value):
        try:
            self._vi.SetControlValue(name, value)
        except Exception as e:
            _handle_com_error(e)

    def run(self, wait_until_done: bool = True):
        try:
            self._vi.Run(wait_until_done)
        except Exception as e:
            _handle_com_error(e)

    def open_in_labview(self):
        self._oleobj.Invoke(1080, 0, pythoncom.DISPATCH_METHOD, True)

    def save_as(self, path: str, overwrite: bool = True):
        try:
            import win32com.client
            path = _normalize_path(path)
            save_dir = os.path.dirname(path)
            if save_dir and not os.path.exists(save_dir):
                os.makedirs(save_dir, exist_ok=True)
            self._vi.Save(path, overwrite, False)
        except Exception as e:
            _handle_com_error(e)


class ScriptingClient:
    _MODULE_STARTUP_WAIT = 0.5
    _MODULE_STARTUP_RETRIES = 4

    def __init__(self, server_path: str = None):
        if server_path is None:
            server_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "Scripting Server"
            )
        self._server_path = server_path
        self._call_lock = threading.RLock()
        self._module_ready = False

    def _get_vi_path(self, vi_name: str) -> str:
        return os.path.join(self._server_path, vi_name)

    def _raw_call(self, vi_name: str, param_names: tuple, param_values: tuple) -> list:
        _ensure_com()
        lv_app = win32com.client.dynamic.Dispatch("LabVIEW.Application")
        vi_path = _normalize_path(self._get_vi_path(vi_name))
        vi_ref = lv_app.GetVIReference(vi_path, "", False, 0)
        if vi_ref is None:
            raise LabVIEWCOMError(f"Cannot open scripting VI reference: {vi_path}")
        vi_ref._FlagAsMethod("Call2")

        names = VARIANT(
            pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_BSTR,
            param_names
        )
        values = VARIANT(
            pythoncom.VT_BYREF | pythoncom.VT_ARRAY | pythoncom.VT_VARIANT,
            param_values
        )
        vi_ref.Call2(names, values, False, False, False, False)
        raw = values.value if hasattr(values, "value") else values
        if not isinstance(raw, (list, tuple)):
            raw = list(raw) if hasattr(raw, "__iter__") else [raw]
        return list(raw)

    def mark_module_stopped(self):
        with self._call_lock:
            self._module_ready = False

    def is_module_ready(self) -> bool:
        return self._module_ready

    def start(self) -> list:
        with self._call_lock:
            self._module_ready = False
            result = self._raw_call(
                "Start Module.vi",
                ("error out", "Wait for Event Sync?", "Scripting Server Broadcast Events",
                 "Module Was Already Running?", "Module Name",
                 "Show Main VI Diagram on Init (F)", "error in"),
                ("", False, "", False, "", False, "")
            )
            time.sleep(self._MODULE_STARTUP_WAIT * 2)
            self._module_ready = True
            return result

    def call(self, vi_name: str, param_names: tuple, param_values: tuple) -> list:
        with self._call_lock:
            if not self._module_ready and vi_name not in ("Start Module.vi", "Stop Module.vi"):
                raise LabVIEWCOMError(
                    "DQMH scripting module is not ready. "
                    "Call start_module first, or use reset_module if LabVIEW is stuck."
                )
            try:
                return self._raw_call(vi_name, param_names, param_values)
            except LabVIEWCOMError:
                raise
            except Exception as e:
                _handle_com_error(e)
