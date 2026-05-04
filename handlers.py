"""Tool handler implementations — one function per MCP tool.

Each handler receives keyword arguments matching the JSON Schema inputs
and returns a dict or string result. Handlers raise LabVIEWCOMError for
COM failures; the server catches these and returns structured error responses.
"""

import ctypes
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import win32com.client
import pythoncom

from labview_com import LabVIEWClient, ScriptingClient, LabVIEWCOMError
from tools import CONFIRMED_PALETTE_NAMES, FORBIDDEN_STANDALONE

_logger = logging.getLogger("labview_mcp.handlers")
_DEBUG_ENABLED = True

lv = LabVIEWClient()
scripting = ScriptingClient()

_TERMINAL_CACHE: dict[str, dict] = {}
_last_vi_id: int = 0


def _debug(tool_name: str, message: str, data: dict = None):
    if _DEBUG_ENABLED:
        _logger.debug(f"[{tool_name}] {message}")
        if data:
            for key, value in data.items():
                _logger.debug(f"  {key}: {value}")


def _ensure_lv():
    lv.connect()


def _dqmh_error(result: list) -> str:
    err = result[0]
    if isinstance(err, tuple) and len(err) >= 2:
        if bool(err[0]):
            code = int(err[1])
            src = str(err[2]) if len(err) > 2 else ""
            return f"Error {code}: {src}"
        return ""
    return str(err) if err else ""


def _parse_terminals(terminal_text: str) -> dict:
    outputs, inputs = [], []
    for m in re.finditer(
        r"Terminal Index:\s*(\d+)\s*---.*?Type:\s*(Input|Output)",
        terminal_text,
    ):
        idx = int(m.group(1))
        if m.group(2) == "Output":
            outputs.append(idx)
        else:
            inputs.append(idx)
    inputs.sort()
    outputs.sort()
    return {"outputs": outputs, "inputs": inputs}


def _query_terminals(obj_id: int) -> dict:
    if obj_id in _TERMINAL_CACHE:
        return _TERMINAL_CACHE[obj_id]
    try:
        result = scripting.call(
            "get_object_terminals.vi",
            ("error out", "timed out?", "result", "wait for reply (T)",
             "error in", "object_id"),
            ("", False, "", True, "", obj_id),
        )
        parsed = _parse_terminals(str(result[2]) if result[2] else "")
    except Exception:
        parsed = {"outputs": [0], "inputs": [1]}
    _TERMINAL_CACHE[obj_id] = parsed
    return parsed


def _resolve_output(obj_id: int, logical_index: int) -> int:
    t = _query_terminals(obj_id)
    if logical_index < len(t["outputs"]):
        return t["outputs"][logical_index]
    return t["outputs"][0] if t["outputs"] else 0


def _resolve_input(obj_id: int, logical_index: int) -> int:
    t = _query_terminals(obj_id)
    if logical_index < len(t["inputs"]):
        return t["inputs"][logical_index]
    return t["inputs"][0] if t["inputs"] else 0


def _cleanup_diagram_sendkeys():
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, "LabVIEW")
        if not hwnd:
            return False
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)

        INPUT_KEYBOARD = 1
        KEYEVENTF_KEYUP = 0x0002
        VK_CONTROL = 0x11
        VK_U = 0x55

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", ctypes.c_ushort),
                         ("wScan", ctypes.c_ushort),
                         ("dwFlags", ctypes.c_ulong),
                         ("time", ctypes.c_ulong),
                         ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class _INPUT_UNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT),
                         ("padding", ctypes.c_byte * 16)]

        class INPUT(ctypes.Structure):
            _anonymous_ = ("_u",)
            _fields_ = [("type", ctypes.c_ulong),
                         ("_u", _INPUT_UNION)]

        inputs = []
        for vk, flags in [(VK_CONTROL, 0), (VK_U, 0),
                           (VK_U, KEYEVENTF_KEYUP), (VK_CONTROL, KEYEVENTF_KEYUP)]:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.ki.wVk = vk
            inp.ki.dwFlags = flags
            inputs.append(inp)

        n = len(inputs)
        arr = (INPUT * n)(*inputs)
        ctypes.windll.user32.SendInput(
            n, ctypes.pointer(arr), ctypes.sizeof(INPUT),
        )
        time.sleep(1.0)
        return True
    except Exception:
        return False


def _auto_ping() -> dict:
    try:
        version = lv.get_version()
        return {"status": "ok", "labview_version": version}
    except Exception as e:
        return {"status": "unreachable", "error": str(e)}


_STRUCTURE_TYPES = {"While Loop #1", "For Loop", "Case Structure", "Feedback Node"}

_available_objects_cache: list[str] | None = None

def _get_cached_palette_names() -> list[str]:
    global _available_objects_cache
    if _available_objects_cache is None:
        _available_objects_cache = list(CONFIRMED_PALETTE_NAMES)
    return _available_objects_cache


def _has_dqmh_error(error_out: str) -> bool:
    return bool(error_out) and error_out.startswith("Error ")


def _verify_object_in_vi(obj_id: int) -> dict:
    try:
        result = scripting.call(
            "get_object_terminals.vi",
            ("error out", "timed out?", "result", "wait for reply (T)",
             "error in", "object_id"),
            ("", False, "", True, "", obj_id),
        )
        error_out = _dqmh_error(result)
        result_text = str(result[2]) if result[2] else ""
        verified = not _has_dqmh_error(error_out) and bool(result_text.strip())
        return {"verified": verified, "error_out": error_out, "result_text": result_text}
    except Exception as e:
        return {"verified": False, "error_out": str(e), "result_text": ""}


def _verify_vi_exists(vi_id: int) -> dict:
    try:
        result = scripting.call(
            "get_vi_error_list.vi",
            ("error out", "timed out?", "result", "wait for reply (T)", "error in", "vi_reference"),
            ("", False, "", True, "", vi_id),
        )
        error_out = _dqmh_error(result)
        verified = not _has_dqmh_error(error_out)
        return {"verified": verified, "error_out": error_out}
    except Exception as e:
        return {"verified": False, "error_out": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL LOW-LEVEL FUNCTIONS (not exposed as MCP tools)
# ═══════════════════════════════════════════════════════════════════════════

def _internal_start_module() -> dict:
    try:
        result = scripting.start()
        error_out = _dqmh_error(result)
        return {
            "status": "module started" if not error_out else "error",
            "module_already_running": bool(result[3]) if len(result) > 3 else False,
            "error_out": error_out,
        }
    except LabVIEWCOMError as e:
        return {"status": "error", "error_out": str(e)}


def _internal_cleanup_vi(vi_id: int) -> dict:
    if not vi_id:
        vi_id = _last_vi_id
    try:
        result = scripting.call(
            "cleanup_vi.vi",
            ("error out", "timed out?", "result", "wait for reply (T)", "error in", "vi_reference"),
            ("", False, "", True, "", vi_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def _internal_stop_module() -> dict:
    try:
        result = scripting.call(
            "Stop Module.vi",
            ("error out", "Timeout to Wait for Stop (s) (-1: no timeout)",
             "error in", "Wait for Module to Stop? (F)", "Origin"),
            ("", -1, "", True, "")
        )
        error_out = _dqmh_error(result)
        scripting.mark_module_stopped()
        return {"status": "module stopped", "error_out": error_out}
    except LabVIEWCOMError as e:
        scripting.mark_module_stopped()
        return {"status": "error", "error_out": str(e)}


def _internal_new_vi() -> dict:
    global _last_vi_id
    try:
        result = scripting.call(
            "new_vi.vi",
            ("error out", "timed out?", "result", "vi_id", "wait for reply (T)", "error in"),
            ("", False, "", 0, True, "")
        )
        error_out = _dqmh_error(result)
        vi_id = int(result[3]) if result[3] else 0
        if vi_id:
            _last_vi_id = vi_id
        return {"vi_id": vi_id, "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"vi_id": 0, "error_out": str(e)}


def _internal_add_object(object_name: str, diagram_id: int = 0,
                         position_x: int = 0, position_y: int = 0) -> dict:
    global _last_vi_id
    resolved_diagram_id = diagram_id if diagram_id != 0 else _last_vi_id
    try:
        result = scripting.call(
            "add_object.vi",
            ("error out", "timed out?", "result", "object_id", "wait for reply (T)",
             "position_y", "error in", "object_name", "diagram_id", "position_x"),
            ("", False, "", 0, True, position_y, "", object_name, resolved_diagram_id, position_x)
        )
        error_out = _dqmh_error(result)
        obj_id = int(result[3]) if result[3] else 0
        return {"object_id": obj_id, "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"object_id": 0, "error_out": str(e)}


def _internal_connect_objects(from_ref: int, from_term: int,
                              to_ref: int, to_term: int,
                              vi_ref: int = 0) -> dict:
    try:
        result = scripting.call(
            "connect_objects.vi",
            ("error out", "timed out?", "result", "to_object_terminal_index",
             "from_object_terminal_index", "wait for reply (T)", "to_object_reference",
             "error in", "from_object_reference", "vi_reference"),
            ("", False, "", to_term, from_term,
             True, to_ref, "", from_ref, vi_ref)
        )
        error_out = _dqmh_error(result)
        return {"error_out": error_out}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def _internal_create_control(object_id: int, terminal_index: int,
                             constant: bool = False) -> dict:
    try:
        result = scripting.call(
            "create_control.vi",
            ("error out", "timed out?", "created_object_id", "wait for reply (T)",
             "constant", "error in", "terminal_index", "object_id"),
            ("", False, 0, True, constant, "", terminal_index, object_id)
        )
        error_out = _dqmh_error(result)
        created_id = int(result[2]) if result[2] else 0
        return {"created_object_id": created_id, "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"created_object_id": 0, "error_out": str(e)}


def _internal_set_value(object_id: int, value: str) -> dict:
    try:
        result = scripting.call(
            "set_value.vi",
            ("error out", "timed out?", "wait for reply (T)", "error in", "value", "object_id"),
            ("", False, True, "", value, object_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def _internal_get_structure_diagram(object_id: int, diagram_index: int = 0) -> dict:
    try:
        result = scripting.call(
            "get_structure_diagram.vi",
            ("error out", "timed out?", "diagram_id", "wait for reply (T)",
             "error in", "index", "structure_id"),
            ("", False, 0, True, "", diagram_index, object_id)
        )
        error_out = _dqmh_error(result)
        diag_id = int(result[2]) if result[2] else 0
        return {"diagram_id": diag_id, "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"diagram_id": 0, "error_out": str(e)}


def _internal_get_loop_conditional_terminal(loop_id: int) -> dict:
    try:
        result = scripting.call(
            "get_loop_conditional_terminal.vi",
            ("error out", "timed out?", "conditional_terminal_id", "wait for reply (T)",
             "error in", "loop_id"),
            ("", False, 0, True, "", loop_id)
        )
        error_out = _dqmh_error(result)
        return {"conditional_terminal_id": int(result[2]) if result[2] else 0, "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"conditional_terminal_id": 0, "error_out": str(e)}


def _internal_get_loop_iteration_terminal(loop_id: int) -> dict:
    try:
        result = scripting.call(
            "get_loop_iteration_terminal.vi",
            ("error out", "timed out?", "iteration_terminal_id", "wait for reply (T)",
             "error in", "loop_id"),
            ("", False, 0, True, "", loop_id)
        )
        error_out = _dqmh_error(result)
        return {"iteration_terminal_id": int(result[2]) if result[2] else 0, "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"iteration_terminal_id": 0, "error_out": str(e)}


def _internal_save_vi(path: str, vi_id: int = 0) -> dict:
    global _last_vi_id
    if not vi_id:
        vi_id = _last_vi_id
    save_dir = os.path.dirname(path)
    if save_dir and not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
    try:
        result = scripting.call(
            "save_vi.vi",
            ("error out", "timed out?", "path_out", "wait for reply (T)", "error in", "path", "vi_id"),
            ("", False, "", True, "", path, vi_id)
        )
        error_out = _dqmh_error(result)
        return {"path_out": str(result[2]) if result[2] else "", "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"path_out": "", "error_out": str(e)}


def _internal_delete_object(object_id: int) -> dict:
    try:
        result = scripting.call(
            "delete_object.vi",
            ("error out", "timed out?", "wait for reply (T)", "error in", "object_id"),
            ("", False, True, "", object_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def _internal_rename_object(object_id: int, new_name: str) -> dict:
    try:
        result = scripting.call(
            "rename_object.vi",
            ("error out", "timed out?", "wait for reply (T)",
             "error in", "label_visible", "new_label_name", "object_id"),
            ("", False, True, "", True, new_name, object_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# SMART TOOL HANDLERS (exposed as MCP tools)
# ═══════════════════════════════════════════════════════════════════════════

def handle_smart_new_vi() -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    if not scripting.is_module_ready():
        start_result = _internal_start_module()
        steps.append({"step": "start_module", "status": start_result["status"],
                       "error": start_result.get("error_out", "")})
        if start_result["status"] == "error":
            return {"success": False, "steps": steps, "error": f"start_module failed: {start_result.get('error_out', '')}"}
    else:
        steps.append({"step": "start_module", "status": "already_running"})

    new_result = _internal_new_vi()
    vi_id = new_result.get("vi_id", 0)
    error_out = new_result.get("error_out", "")
    steps.append({"step": "new_vi", "vi_id": vi_id, "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps, "error": f"DQMH error creating VI: {error_out}"}

    if vi_id == 0:
        return {"success": False, "steps": steps, "error": "Failed to create new VI: returned vi_id=0"}

    verify = _verify_vi_exists(vi_id)
    steps.append({"step": "verify_vi", "vi_id": vi_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        return {"success": False, "steps": steps, "error":
                f"VI (id={vi_id}) was NOT confirmed to exist. "
                f"Verify failed: {verify.get('error_out', 'query returned error')}"}

    return {
        "success": True,
        "vi_id": vi_id,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_save_and_finish(path: str, vi_id: int = 0) -> dict:
    global _last_vi_id
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})

    if not vi_id:
        vi_id = _last_vi_id

    save_result = _internal_save_vi(path, vi_id)
    save_error = save_result.get("error_out", "")
    steps.append({"step": "save_vi_dqmh", "path": save_result.get("path_out", path),
                   "error": save_error})

    if _has_dqmh_error(save_error):
        steps.append({"step": "warning", "message": f"DQMH save failed ({save_error}), trying COM fallback"})
        try:
            _ensure_lv()
            lv_app = win32com.client.dynamic.Dispatch("LabVIEW.Application")
            vis = lv_app.VIs
            for i in range(vis.Count):
                vi_ref = vis.Item(i)
                try:
                    vi_name = vi_ref.Name
                except Exception:
                    continue
                steps.append({"step": "com_fallback_candidate", "vi_name": vi_name})
            vi_com = vis.Item(vis.Count - 1)
            vi_name = vi_com.Name
            steps.append({"step": "com_fallback_save", "vi_name": vi_name, "path": path})
            vi_com.Save(path, True, False)
            save_error = ""
            steps.append({"step": "com_fallback_result", "status": "success"})
        except Exception as e:
            steps.append({"step": "com_fallback_result", "status": "failed", "error": str(e)})

    if not _has_dqmh_error(save_error):
        cleanup_result = _internal_cleanup_vi(vi_id)
        steps.append({"step": "cleanup_vi", "error": cleanup_result.get("error_out", "")})

    stop_result = _internal_stop_module()
    steps.append({"step": "stop_module", "status": stop_result["status"],
                   "error": stop_result.get("error_out", "")})

    _TERMINAL_CACHE.clear()
    _last_vi_id = 0

    return {
        "success": not _has_dqmh_error(save_error),
        "saved_path": path if not _has_dqmh_error(save_error) else "",
        "cleanup_done": not _has_dqmh_error(save_error),
        "module_stopped": stop_result["status"] == "module stopped",
        "steps": steps,
    }


def handle_smart_add_object(object_name: str, diagram_id: int = 0,
                            position_x: int = 0, position_y: int = 0) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    palette = _get_cached_palette_names()
    if object_name in FORBIDDEN_STANDALONE:
        return {"success": False, "steps": steps, "error":
                f"'{object_name}' is a constant type — use smart_create_control instead."}
    if object_name not in palette:
        return {"success": False, "steps": steps, "error":
                f"'{object_name}' not in confirmed palette. Call get_available_objects to see valid names."}

    add_result = _internal_add_object(object_name, diagram_id, position_x, position_y)
    obj_id = add_result.get("object_id", 0)
    error_out = add_result.get("error_out", "")
    steps.append({"step": "add_object", "object_id": obj_id, "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps, "object_id": 0,
                "error": f"DQMH error when adding '{object_name}': {error_out}"}

    if obj_id == 0:
        return {"success": False, "steps": steps, "object_id": 0,
                "error": f"Failed to add object '{object_name}': returned object_id=0"}

    verify = _verify_object_in_vi(obj_id)
    steps.append({"step": "verify_object", "object_id": obj_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        if object_name in _STRUCTURE_TYPES:
            steps.append({"step": "warning", "message":
                           f"Structure '{object_name}' verify skipped (no standard terminals). "
                           f"Object ID {obj_id} accepted as valid."})
        else:
            return {"success": False, "steps": steps, "object_id": 0,
                    "error": f"Object '{object_name}' (id={obj_id}) was NOT confirmed in VI. "
                             f"Verify failed: {verify.get('error_out', 'no terminal info returned')}"}

    terminals = _query_terminals(obj_id)
    steps.append({"step": "get_terminals", "object_id": obj_id, "terminals": terminals})

    return {
        "success": True,
        "object_id": obj_id,
        "palette_name": object_name,
        "terminals": terminals,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_add_object_inside(parent_object_id: int, object_name: str,
                                   case_index: int = 0,
                                   position_x: int = 0, position_y: int = 0) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    palette = _get_cached_palette_names()
    if object_name in FORBIDDEN_STANDALONE:
        return {"success": False, "steps": steps, "error":
                f"'{object_name}' is a constant type that cannot be placed standalone. "
                f"Place a function first (e.g. Add), then use smart_create_control with constant=True "
                f"on its terminal to create a constant inside the structure."}
    if object_name not in palette:
        return {"success": False, "steps": steps, "error": f"'{object_name}' not in confirmed palette."}

    diag_result = _internal_get_structure_diagram(parent_object_id, case_index)
    inner_diag_id = diag_result.get("diagram_id", 0)
    diag_error = diag_result.get("error_out", "")
    steps.append({"step": "get_structure_diagram", "parent_object_id": parent_object_id,
                   "case_index": case_index, "diagram_id": inner_diag_id,
                   "error": diag_error})

    if _has_dqmh_error(diag_error):
        return {"success": False, "steps": steps,
                "error": f"DQMH error resolving sub-diagram: {diag_error}"}

    if inner_diag_id == 0:
        return {"success": False, "steps": steps, "error": f"Could not resolve sub-diagram for parent {parent_object_id}"}

    add_result = _internal_add_object(object_name, inner_diag_id, position_x, position_y)
    obj_id = add_result.get("object_id", 0)
    error_out = add_result.get("error_out", "")
    steps.append({"step": "add_object", "object_id": obj_id, "diagram_id": inner_diag_id,
                   "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps,
                "error": f"DQMH error when adding '{object_name}' inside parent: {error_out}"}

    if obj_id == 0:
        return {"success": False, "steps": steps, "error": add_result.get("error_out", "Failed to add object")}

    verify = _verify_object_in_vi(obj_id)
    steps.append({"step": "verify_object", "object_id": obj_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        if object_name in _STRUCTURE_TYPES:
            steps.append({"step": "warning", "message":
                           f"Structure '{object_name}' verify skipped (no standard terminals). "
                           f"Object ID {obj_id} accepted as valid."})
        else:
            return {"success": False, "steps": steps, "object_id": 0,
                    "error": f"Object '{object_name}' (id={obj_id}) inside parent {parent_object_id} "
                             f"was NOT confirmed in VI. Verify failed: {verify.get('error_out', 'no terminal info returned')}"}

    terminals = _query_terminals(obj_id)
    steps.append({"step": "get_terminals", "object_id": obj_id, "terminals": terminals})

    return {
        "success": True,
        "object_id": obj_id,
        "inner_diagram_id": inner_diag_id,
        "palette_name": object_name,
        "terminals": terminals,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_add_with_constants(object_name: str, diagram_id: int = 0,
                                    position_x: int = 0, position_y: int = 0,
                                    input_values: list | None = None,
                                    output_indicators: list | None = None) -> dict:
    steps = []
    input_values = input_values or []
    output_indicators = output_indicators or []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    palette = _get_cached_palette_names()
    if object_name in FORBIDDEN_STANDALONE:
        return {"success": False, "steps": steps, "error": f"'{object_name}' is a constant type."}
    if object_name not in palette:
        return {"success": False, "steps": steps, "error": f"'{object_name}' not in confirmed palette."}

    add_result = _internal_add_object(object_name, diagram_id, position_x, position_y)
    obj_id = add_result.get("object_id", 0)
    error_out = add_result.get("error_out", "")
    steps.append({"step": "add_object", "object_id": obj_id, "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps,
                "error": f"DQMH error when adding '{object_name}': {error_out}"}

    if obj_id == 0:
        return {"success": False, "steps": steps, "error": add_result.get("error_out", "Failed to add object")}

    verify = _verify_object_in_vi(obj_id)
    steps.append({"step": "verify_object", "object_id": obj_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        return {"success": False, "steps": steps, "object_id": 0,
                "error": f"Object '{object_name}' (id={obj_id}) was NOT confirmed in VI. "
                         f"Verify failed: {verify.get('error_out', 'no terminal info returned')}"}

    terminals = _query_terminals(obj_id)
    steps.append({"step": "get_terminals", "object_id": obj_id, "terminals": terminals})

    created_constants = {}
    for iv in input_values:
        logical = iv.get("terminal_index", 0)
        actual = _resolve_input(obj_id, logical)
        cc = _internal_create_control(obj_id, actual, constant=True)
        cid = cc.get("created_object_id", 0)
        if cid:
            _internal_set_value(cid, str(iv.get("value", "0")))
            created_constants[logical] = cid
            steps.append({"step": "input_constant", "logical": logical, "actual": actual,
                           "value": iv.get("value", "0"), "created_id": cid})

    created_indicators = {}
    for oi in output_indicators:
        actual = _resolve_output(obj_id, oi)
        cc = _internal_create_control(obj_id, actual, constant=False)
        cid = cc.get("created_object_id", 0)
        if cid:
            created_indicators[oi] = cid
            steps.append({"step": "output_indicator", "logical": oi, "actual": actual,
                           "created_id": cid})

    return {
        "success": True,
        "object_id": obj_id,
        "palette_name": object_name,
        "terminals": terminals,
        "created_constants": created_constants,
        "created_indicators": created_indicators,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_while_loop(stop_condition: str = "false",
                            position_x: int = 0, position_y: int = 0,
                            diagram_id: int = 0) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    add_result = _internal_add_object("While Loop #1", diagram_id, position_x, position_y)
    loop_id = add_result.get("object_id", 0)
    error_out = add_result.get("error_out", "")
    steps.append({"step": "add_while_loop", "object_id": loop_id, "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps,
                "error": f"DQMH error when adding While Loop: {error_out}"}

    if loop_id == 0:
        return {"success": False, "steps": steps, "error": "Failed to add While Loop"}

    verify = _verify_object_in_vi(loop_id)
    steps.append({"step": "verify_object", "object_id": loop_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        steps.append({"step": "warning", "message":
                       f"While Loop verify skipped (terminal query returned empty). "
                       f"Object ID {loop_id} accepted as valid."})

    terminals = _query_terminals(loop_id)
    steps.append({"step": "get_terminals", "object_id": loop_id, "terminals": terminals})

    cond_result = _internal_get_loop_conditional_terminal(loop_id)
    cond_id = cond_result.get("conditional_terminal_id", 0)
    cond_error = cond_result.get("error_out", "")
    steps.append({"step": "get_conditional_terminal", "conditional_terminal_id": cond_id,
                   "error": cond_error})

    iter_result = _internal_get_loop_iteration_terminal(loop_id)
    iter_id = iter_result.get("iteration_terminal_id", 0)
    iter_error = iter_result.get("error_out", "")
    steps.append({"step": "get_iteration_terminal", "iteration_terminal_id": iter_id,
                   "error": iter_error})

    if _has_dqmh_error(cond_error):
        steps.append({"step": "warning", "message": f"Could not get conditional terminal: {cond_error}"})

    if cond_id:
        cc = _internal_create_control(cond_id, 0, constant=True)
        cid = cc.get("created_object_id", 0)
        if cid:
            _internal_set_value(cid, stop_condition)
            steps.append({"step": "wire_stop_condition", "value": stop_condition, "created_id": cid})

    diag_result = _internal_get_structure_diagram(loop_id, 0)
    inner_diagram_id = diag_result.get("diagram_id", 0)
    steps.append({"step": "get_inner_diagram", "diagram_id": inner_diagram_id})

    return {
        "success": True,
        "object_id": loop_id,
        "inner_diagram_id": inner_diagram_id,
        "conditional_terminal_id": cond_id,
        "iteration_terminal_id": iter_id,
        "terminals": terminals,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_for_loop(iterations: int = 10,
                          position_x: int = 0, position_y: int = 0,
                          diagram_id: int = 0) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    add_result = _internal_add_object("For Loop", diagram_id, position_x, position_y)
    loop_id = add_result.get("object_id", 0)
    error_out = add_result.get("error_out", "")
    steps.append({"step": "add_for_loop", "object_id": loop_id, "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps,
                "error": f"DQMH error when adding For Loop: {error_out}"}

    if loop_id == 0:
        return {"success": False, "steps": steps, "error": "Failed to add For Loop"}

    verify = _verify_object_in_vi(loop_id)
    steps.append({"step": "verify_object", "object_id": loop_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        return {"success": False, "steps": steps, "object_id": 0,
                "error": f"For Loop (id={loop_id}) was NOT confirmed in VI. "
                         f"Verify failed: {verify.get('error_out', 'no terminal info returned')}"}

    terminals = _query_terminals(loop_id)
    steps.append({"step": "get_terminals", "object_id": loop_id, "terminals": terminals})

    count_actual = _resolve_input(loop_id, 0)
    cc = _internal_create_control(loop_id, count_actual, constant=True)
    cid = cc.get("created_object_id", 0)
    if cid:
        _internal_set_value(cid, str(iterations))
        steps.append({"step": "wire_iterations", "iterations": iterations, "created_id": cid})

    iter_result = _internal_get_loop_iteration_terminal(loop_id)
    iter_id = iter_result.get("iteration_terminal_id", 0)
    iter_error = iter_result.get("error_out", "")
    steps.append({"step": "get_iteration_terminal", "iteration_terminal_id": iter_id,
                   "error": iter_error})

    diag_result = _internal_get_structure_diagram(loop_id, 0)
    inner_diagram_id = diag_result.get("diagram_id", 0)
    steps.append({"step": "get_inner_diagram", "diagram_id": inner_diagram_id})

    return {
        "success": True,
        "object_id": loop_id,
        "inner_diagram_id": inner_diagram_id,
        "iterations": iterations,
        "iteration_terminal_id": iter_id,
        "terminals": terminals,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_case_structure(num_cases: int = 2,
                                position_x: int = 0, position_y: int = 0,
                                diagram_id: int = 0) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    add_result = _internal_add_object("Case Structure", diagram_id, position_x, position_y)
    case_id = add_result.get("object_id", 0)
    error_out = add_result.get("error_out", "")
    steps.append({"step": "add_case_structure", "object_id": case_id, "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps,
                "error": f"DQMH error when adding Case Structure: {error_out}"}

    if case_id == 0:
        return {"success": False, "steps": steps, "error": "Failed to add Case Structure"}

    verify = _verify_object_in_vi(case_id)
    steps.append({"step": "verify_object", "object_id": case_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        return {"success": False, "steps": steps, "object_id": 0,
                "error": f"Case Structure (id={case_id}) was NOT confirmed in VI. "
                         f"Verify failed: {verify.get('error_out', 'no terminal info returned')}"}

    terminals = _query_terminals(case_id)
    steps.append({"step": "get_terminals", "object_id": case_id, "terminals": terminals})

    diagram_ids = {}
    for ci in range(num_cases):
        diag_result = _internal_get_structure_diagram(case_id, ci)
        did = diag_result.get("diagram_id", 0)
        diagram_ids[ci] = did
        steps.append({"step": f"case_{ci}_diagram", "diagram_id": did})

    return {
        "success": True,
        "object_id": case_id,
        "diagram_ids": diagram_ids,
        "terminals": terminals,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_feedback_node(init_value: str = "0",
                               position_x: int = 0, position_y: int = 0,
                               diagram_id: int = 0,
                               parent_object_id: int = 0,
                               case_index: int = 0) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    resolved_diagram_id = diagram_id
    if parent_object_id:
        diag_result = _internal_get_structure_diagram(parent_object_id, case_index)
        resolved_diagram_id = diag_result.get("diagram_id", 0)
        diag_error = diag_result.get("error_out", "")
        steps.append({"step": "resolve_parent_diagram", "parent_object_id": parent_object_id,
                       "case_index": case_index, "diagram_id": resolved_diagram_id,
                       "error": diag_error})
        if _has_dqmh_error(diag_error):
            return {"success": False, "steps": steps,
                    "error": f"DQMH error resolving parent diagram: {diag_error}"}

    add_result = _internal_add_object("Feedback Node", resolved_diagram_id, position_x, position_y)
    fn_id = add_result.get("object_id", 0)
    error_out = add_result.get("error_out", "")
    steps.append({"step": "add_feedback_node", "object_id": fn_id, "error": error_out})

    if _has_dqmh_error(error_out):
        return {"success": False, "steps": steps,
                "error": f"DQMH error when adding Feedback Node: {error_out}"}

    if fn_id == 0:
        return {"success": False, "steps": steps, "error": "Failed to add Feedback Node"}

    verify = _verify_object_in_vi(fn_id)
    steps.append({"step": "verify_object", "object_id": fn_id,
                   "verified": verify["verified"], "verify_error": verify.get("error_out", "")})

    if not verify["verified"]:
        steps.append({"step": "warning", "message":
                       f"Feedback Node verify skipped. Object ID {fn_id} accepted as valid."})

    terminals = _query_terminals(fn_id)
    steps.append({"step": "get_terminals", "object_id": fn_id, "terminals": terminals})

    init_actual = _resolve_input(fn_id, 1)
    cc = _internal_create_control(fn_id, init_actual, constant=True)
    cid = cc.get("created_object_id", 0)
    if cid:
        _internal_set_value(cid, init_value)
        steps.append({"step": "set_init_value", "init_value": init_value,
                       "actual_terminal": init_actual, "created_id": cid})

    return {
        "success": True,
        "object_id": fn_id,
        "init_value": init_value,
        "init_terminal_actual": init_actual,
        "terminals": terminals,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_connect_objects(from_object_reference: int, from_object_terminal_index: int,
                                 to_object_reference: int, to_object_terminal_index: int) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    from_terminals = _query_terminals(from_object_reference)
    to_terminals = _query_terminals(to_object_reference)
    steps.append({"step": "query_terminals",
                   "from_object": from_object_reference, "from_terminals": from_terminals,
                   "to_object": to_object_reference, "to_terminals": to_terminals})

    actual_from = _resolve_output(from_object_reference, from_object_terminal_index)
    actual_to = _resolve_input(to_object_reference, to_object_terminal_index)
    steps.append({"step": "resolve_terminals",
                   "from_logical": from_object_terminal_index, "from_actual": actual_from,
                   "to_logical": to_object_terminal_index, "to_actual": actual_to})

    connect_result = _internal_connect_objects(
        from_object_reference, actual_from,
        to_object_reference, actual_to,
    )
    steps.append({"step": "connect_objects", "error": connect_result.get("error_out", "")})

    return {
        "success": not connect_result.get("error_out"),
        "from_object": from_object_reference,
        "from_logical_terminal": from_object_terminal_index,
        "from_actual_terminal": actual_from,
        "from_terminals": from_terminals,
        "to_object": to_object_reference,
        "to_logical_terminal": to_object_terminal_index,
        "to_actual_terminal": actual_to,
        "to_terminals": to_terminals,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_wire(from_object_reference: int, from_object_terminal_index: int,
                      to_object_reference: int, to_object_terminal_index: int,
                      constant_value: str | None = None) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    from_terminals = _query_terminals(from_object_reference)
    to_terminals = _query_terminals(to_object_reference)
    steps.append({"step": "query_terminals",
                   "from_object": from_object_reference, "from_terminals": from_terminals,
                   "to_object": to_object_reference, "to_terminals": to_terminals})

    actual_from = _resolve_output(from_object_reference, from_object_terminal_index)
    actual_to = _resolve_input(to_object_reference, to_object_terminal_index)
    steps.append({"step": "resolve_terminals",
                   "from_logical": from_object_terminal_index, "from_actual": actual_from,
                   "to_logical": to_object_terminal_index, "to_actual": actual_to})

    if constant_value is not None:
        cc = _internal_create_control(to_object_reference, actual_to, constant=True)
        cid = cc.get("created_object_id", 0)
        if cid:
            _internal_set_value(cid, constant_value)
            steps.append({"step": "create_constant", "value": constant_value, "created_id": cid})

    connect_result = _internal_connect_objects(
        from_object_reference, actual_from,
        to_object_reference, actual_to,
    )
    steps.append({"step": "connect_objects", "error": connect_result.get("error_out", "")})

    return {
        "success": not connect_result.get("error_out"),
        "from_object": from_object_reference,
        "from_logical_terminal": from_object_terminal_index,
        "from_actual_terminal": actual_from,
        "to_object": to_object_reference,
        "to_logical_terminal": to_object_terminal_index,
        "to_actual_terminal": actual_to,
        "constant_created": constant_value is not None,
        "ping": ping,
        "steps": steps,
    }


def handle_smart_create_control(object_id: int, terminal_index: int, constant: bool = False,
                               is_input: bool | None = None) -> dict:
    steps = []

    ping = _auto_ping()
    steps.append({"step": "ping", "result": ping["status"]})
    if ping["status"] != "ok":
        return {"success": False, "steps": steps, "error": f"LabVIEW unreachable: {ping.get('error', '')}"}

    terminals = _query_terminals(object_id)
    steps.append({"step": "query_terminals", "object_id": object_id, "terminals": terminals})

    if constant:
        actual = _resolve_input(object_id, terminal_index)
    elif is_input is True:
        actual = _resolve_input(object_id, terminal_index)
    elif is_input is False:
        actual = _resolve_output(object_id, terminal_index)
    else:
        t = _query_terminals(object_id)
        if terminal_index < len(t["inputs"]):
            actual = _resolve_input(object_id, terminal_index)
        elif terminal_index < len(t["outputs"]):
            actual = _resolve_output(object_id, terminal_index)
        elif t["inputs"]:
            actual = _resolve_input(object_id, min(terminal_index, len(t["inputs"]) - 1))
        else:
            actual = _resolve_output(object_id, min(terminal_index, len(t["outputs"]) - 1))
    steps.append({"step": "resolve_terminal", "logical": terminal_index, "actual": actual, "constant": constant})

    create_result = _internal_create_control(object_id, actual, constant)
    created_id = create_result.get("created_object_id", 0)
    steps.append({"step": "create_control", "created_object_id": created_id,
                   "error": create_result.get("error_out", "")})

    return {
        "success": created_id > 0,
        "created_object_id": created_id,
        "parent_object_id": object_id,
        "logical_terminal": terminal_index,
        "actual_terminal": actual,
        "constant": constant,
        "parent_terminals": terminals,
        "ping": ping,
        "steps": steps,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SIMPLE TOOL HANDLERS (exposed as MCP tools)
# ═══════════════════════════════════════════════════════════════════════════

def handle_reset_module() -> dict:
    scripting.mark_module_stopped()
    stop_error = ""
    try:
        with scripting._call_lock:
            scripting._raw_call(
                "Stop Module.vi",
                ("error out", "Timeout to Wait for Stop (s) (-1: no timeout)",
                 "error in", "Wait for Module to Stop? (F)", "Origin"),
                ("", 5, "", True, "")
            )
    except Exception as e:
        stop_error = str(e)

    time.sleep(1.5)

    try:
        version = lv.get_version()
    except Exception as e:
        return {
            "status": "labview_unreachable",
            "message": "LabVIEW COM is not responding. Restart LabVIEW manually.",
            "stop_error": stop_error,
            "com_error": str(e),
        }

    try:
        result = scripting.start()
        error_out = _dqmh_error(result)
        if error_out:
            return {
                "status": "start_failed",
                "message": f"LabVIEW is alive (v{version}) but start_module failed.",
                "stop_error": stop_error,
                "start_error": error_out,
            }
        return {
            "status": "ready",
            "message": f"Module reset and confirmed ready. LabVIEW {version}.",
            "module_was_already_running": bool(result[3]) if len(result) > 3 else False,
            "stop_error": stop_error or None,
        }
    except Exception as e:
        return {
            "status": "start_failed",
            "message": "LabVIEW is alive but module failed readiness probe.",
            "stop_error": stop_error,
            "start_error": str(e),
        }


def handle_ping_labview() -> dict:
    try:
        version = lv.get_version()
        return {"status": "ok", "labview_version": version, "message": "LabVIEW COM bridge is reachable."}
    except Exception as e:
        return {"status": "unreachable", "message": "LabVIEW is not responding via COM.", "error": str(e)}


def handle_delete_object(object_id: int) -> dict:
    result = _internal_delete_object(object_id)
    err = result.get("error_out", "")
    return {"result": "deleted" if not err else "", "error_out": err}


def handle_rename_object(object_id: int, new_name: str) -> dict:
    result = _internal_rename_object(object_id, new_name)
    err = result.get("error_out", "")
    return {"result": "renamed" if not err else "", "error_out": err}


def handle_set_value(object_id: int, value: str) -> dict:
    return _internal_set_value(object_id, value)


def handle_open_vi(path: str) -> dict:
    _ensure_lv()
    try:
        vi = lv.get_vi(path)
        vi.open_in_labview()
        return {"status": "opened", "path": path}
    except LabVIEWCOMError as e:
        return {"status": "error", "path": path, "error": str(e)}


def handle_run_vi(path: str, controls: dict | None = None) -> dict:
    _ensure_lv()
    try:
        vi = lv.get_vi(path)
        if controls:
            for name, value in controls.items():
                try:
                    vi.set_control_value(name, value)
                except Exception:
                    pass
        vi.run(wait_until_done=True)
        return {"status": "completed", "path": path}
    except LabVIEWCOMError as e:
        return {"status": "error", "path": path, "error": str(e)}


def handle_get_vi_error_list(vi_reference: int = 0) -> dict:
    global _last_vi_id
    if not vi_reference:
        vi_reference = _last_vi_id
    try:
        result = scripting.call(
            "get_vi_error_list.vi",
            ("error out", "timed out?", "result", "wait for reply (T)", "error in", "vi_reference"),
            ("", False, "", True, "", vi_reference)
        )
        error_out = _dqmh_error(result)
        return {"result": str(result[2]) if result[2] else "", "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"result": "", "error_out": str(e)}


def handle_get_object_terminals(object_id: int) -> dict:
    try:
        result = scripting.call(
            "get_object_terminals.vi",
            ("error out", "timed out?", "result", "wait for reply (T)", "error in", "object_id"),
            ("", False, "", True, "", object_id)
        )
        error_out = _dqmh_error(result)
        return {"result": str(result[2]) if result[2] else "", "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"result": "", "error_out": str(e)}


def handle_get_object_help(object_id: int) -> dict:
    try:
        result = scripting.call(
            "get_object_help.vi",
            ("error out", "timed out?", "help_string", "wait for reply (T)", "error in", "object_id"),
            ("", False, "", True, "", object_id)
        )
        error_out = _dqmh_error(result)
        return {"result": str(result[2]) if result[2] else "", "error_out": error_out}
    except LabVIEWCOMError as e:
        return {"result": "", "error_out": str(e)}


def handle_add_to_selection(object_id: int) -> dict:
    global _last_vi_id
    try:
        result = scripting.call(
            "add_to_selection.vi",
            ("error out", "timed out?", "wait for reply (T)", "error in", "object_id", "vi_id"),
            ("", False, True, "", object_id, _last_vi_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def handle_remove_from_selection(object_id: int) -> dict:
    global _last_vi_id
    try:
        result = scripting.call(
            "remove_from_selection.vi",
            ("error out", "timed out?", "wait for reply (T)", "error in", "object_id", "vi_id"),
            ("", False, True, "", object_id, _last_vi_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def handle_clear_selection_list() -> dict:
    global _last_vi_id
    try:
        result = scripting.call(
            "clear_selection_list.vi",
            ("error out", "timed out?", "wait for reply (T)", "error in", "vi_id"),
            ("", False, True, "", _last_vi_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def handle_enclose_selection(structure_name: str) -> dict:
    global _last_vi_id
    try:
        result = scripting.call(
            "enclose_selection.vi",
            ("error out", "timed out?", "object_id", "wait for reply (T)",
             "error in", "structure_type", "vi_id"),
            ("", False, 0, True, "", structure_name, _last_vi_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


def handle_connect_to_pane(object_id: int, pane_index: int) -> dict:
    try:
        result = scripting.call(
            "connect_to_pane.vi",
            ("error out", "timed out?", "result", "wait for reply (T)",
             "error in", "pane_index", "object_id"),
            ("", False, "", True, "", pane_index, object_id)
        )
        return {"error_out": _dqmh_error(result)}
    except LabVIEWCOMError as e:
        return {"error_out": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# INSPECTION / READ-ONLY TOOLS
# ═══════════════════════════════════════════════════════════════════════════

def handle_get_vi_details(path: str) -> dict:
    _ensure_lv()
    try:
        vi = lv.get_vi(path)
        result = {
            "name": vi.get_name(),
            "path": vi.get_path(),
            "description": vi.get_description(),
            "revision": vi.get_revision(),
        }
        for key, getter in [
            ("is_reentrant", vi.get_is_reentrant),
            ("exec_state", vi.get_exec_state),
            ("exec_priority", vi.get_exec_priority),
            ("bd_size", vi.get_bd_size),
            ("code_size", vi.get_code_size),
            ("data_size", vi.get_data_size),
        ]:
            try:
                result[key] = getter()
            except Exception:
                pass
        try:
            result["callees"] = vi.get_callees()
        except Exception:
            pass
        return result
    except LabVIEWCOMError as e:
        return {"error": str(e), "path": path}


def handle_get_vi_strings(path: str) -> str:
    _ensure_lv()
    return lv.get_vi(path).export_strings()


def handle_get_vi_block_diagram(path: str) -> dict:
    _ensure_lv()
    try:
        vi = lv.get_vi(path)
        img_bytes = vi.get_block_diagram_image()
        import base64
        return {"format": "png", "data_base64": base64.b64encode(img_bytes).decode("ascii"), "path": path}
    except LabVIEWCOMError as e:
        return {"error": str(e), "path": path}


def handle_get_vi_front_panel(path: str) -> dict:
    _ensure_lv()
    try:
        vi = lv.get_vi(path)
        img_bytes = vi.get_front_panel_image()
        import base64
        return {"format": "png", "data_base64": base64.b64encode(img_bytes).decode("ascii"), "path": path}
    except LabVIEWCOMError as e:
        return {"error": str(e), "path": path}


def handle_get_vi_hierarchy(path: str) -> dict:
    _ensure_lv()
    try:
        vi = lv.get_vi(path)
        result = {}
        try:
            result["callees"] = vi.get_callees()
        except Exception:
            result["callees"] = []
        try:
            result["callers"] = vi.get_callers()
        except Exception:
            result["callers"] = []
        return result
    except LabVIEWCOMError as e:
        return {"error": str(e), "path": path}


def handle_get_vi_call_chain(path: str, depth: int = 3) -> dict:
    _ensure_lv()
    visited = set()

    def build_chain(vi_path, current_depth):
        abs_path = os.path.abspath(vi_path)
        if abs_path in visited or current_depth <= 0:
            return []
        visited.add(abs_path)
        try:
            vi = lv.get_vi(vi_path)
            callees = vi.get_callees()
        except Exception:
            return []
        result = []
        for callee in callees:
            callee_path = callee if os.path.isabs(callee) else os.path.join(os.path.dirname(abs_path), callee)
            entry = {"name": os.path.basename(callee), "path": callee_path, "callees": []}
            if current_depth > 1:
                entry["callees"] = build_chain(callee_path, current_depth - 1)
            result.append(entry)
        return result

    return {"path": os.path.abspath(path), "callees": build_chain(path, depth)}


def handle_get_connector_pane(path: str) -> dict:
    _ensure_lv()
    try:
        xml_str = lv.get_vi(path).export_strings()
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return {"terminals": []}
    connterms = root.find(".//CONNTERMS")
    if connterms is None:
        return {"terminals": []}
    terminals = []
    for cterm in connterms.findall("CTERM"):
        name = cterm.get("name", "")
        ctype = cterm.get("type", "")
        is_input = cterm.get("direction", "input").lower() == "input"
        terminals.append({"name": name, "type": ctype, "is_input": is_input})
    return {"terminals": terminals}


def handle_get_available_objects() -> dict:
    return {
        "objects": [
            {"name": "While Loop #1", "type": "Structure", "note": "Use EXACTLY 'While Loop #1'"},
            {"name": "For Loop", "type": "Structure"},
            {"name": "Case Structure", "type": "Structure"},
            {"name": "Feedback Node", "type": "Node"},
            {"name": "Add", "type": "Function"},
            {"name": "Subtract", "type": "Function"},
            {"name": "Multiply", "type": "Function"},
            {"name": "Divide", "type": "Function"},
            {"name": "Increment", "type": "Function"},
            {"name": "Decrement", "type": "Function"},
            {"name": "Negate", "type": "Function"},
            {"name": "Absolute Value", "type": "Function"},
            {"name": "Square Root", "type": "Function"},
            {"name": "Reciprocal", "type": "Function"},
            {"name": "Round To Nearest", "type": "Function"},
            {"name": "Quotient & Remainder", "type": "Function"},
            {"name": "Compound Arithmetic", "type": "Function"},
            {"name": "Greater?", "type": "Function"},
            {"name": "Less?", "type": "Function"},
            {"name": "Equal?", "type": "Function"},
            {"name": "Not Equal?", "type": "Function"},
            {"name": "In Range and Coerce", "type": "Function"},
            {"name": "Select", "type": "Function"},
            {"name": "And", "type": "Function"},
            {"name": "Or", "type": "Function"},
            {"name": "Not", "type": "Function"},
            {"name": "Xor", "type": "Function"},
            {"name": "Wait (ms)", "type": "Function"},
            {"name": "Tick Count (ms)", "type": "Function"},
            {"name": "Random Number (0-1)", "type": "Function"},
            {"name": "Concatenate Strings", "type": "Function"},
            {"name": "String Length", "type": "Function"},
            {"name": "Format Into String", "type": "Function"},
            {"name": "Scan From String", "type": "Function"},
            {"name": "Build Array", "type": "Function"},
            {"name": "Index Array", "type": "Function"},
            {"name": "Array Size", "type": "Function"},
            {"name": "Split Number", "type": "Function"},
            {"name": "Bundle", "type": "Function"},
            {"name": "Unbundle", "type": "Function"},
            {"name": "Bundle By Name", "type": "Function"},
            {"name": "Unbundle By Name", "type": "Function"},
            {"name": "Type Cast", "type": "Function"},
            {"name": "Numeric Control (modern)", "type": "Control"},
            {"name": "Numeric Indicator (modern)", "type": "Indicator"},
            {"name": "Local Variable", "type": "Variable"},
            {"name": "Global Variable", "type": "Variable"},
        ],
        "note": "Confirmed working palette names. Use smart_add_object or smart_add_with_constants to place."
    }


def handle_get_control(path: str) -> dict:
    _ensure_lv()
    try:
        img_bytes = lv.get_vi(path).get_front_panel_image()
        import base64
        return {"format": "png", "data_base64": base64.b64encode(img_bytes).decode("ascii")}
    except LabVIEWCOMError as e:
        return {"error": str(e), "path": path}


def handle_get_enum(path: str) -> dict:
    _ensure_lv()
    try:
        vi = lv.get_vi(path)
        xml_str = vi.export_strings()
        names = re.findall(r'<CONTROL\s+[^>]*name="([^"]*)"', xml_str)
        control_name = names[0] if names else vi.get_name().replace(".ctl", "")
        try:
            val = vi._oleobj.Invoke(1013, 0, 4, True, control_name)
            if isinstance(val, (list, tuple)):
                return {"elements": [str(v) for v in val]}
        except Exception:
            pass
        strings_matches = re.findall(r'<STRINGS>(.*?)</STRINGS>', xml_str, re.DOTALL)
        if strings_matches:
            items = re.findall(r'<ITEM>(.*?)</ITEM>', strings_matches[0])
            if items:
                return {"elements": items}
        return {"elements": [], "control_name": control_name, "note": "Could not extract enum values"}
    except Exception as e:
        return {"elements": [], "note": f"Could not extract enum values: {e}"}


def handle_get_project(path: str) -> str:
    if not os.path.exists(path):
        return f"File not found: {path}"
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def handle_list_project_files(path: str) -> dict:
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        xml = f.read()
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}"}
    vis, ctls, libs, classes = [], [], [], []
    for item in root.iter("Item"):
        url = item.get("URL", "")
        name = item.get("Name", "")
        if url.endswith(".vi"):
            vis.append({"name": name, "path": url})
        elif url.endswith(".ctl"):
            ctls.append({"name": name, "path": url})
        elif url.endswith(".lvlib"):
            libs.append({"name": name, "path": url})
        elif url.endswith(".lvclass"):
            classes.append({"name": name, "path": url})
    return {"vis": vis, "ctls": ctls, "libs": libs, "classes": classes}


def handle_list_vis(directory: str) -> dict:
    vis, ctls = [], []
    for root, dirs, files in os.walk(directory):
        for f in files:
            full = os.path.join(root, f)
            if f.lower().endswith(".vi"):
                vis.append({"name": f, "path": full})
            elif f.lower().endswith(".ctl"):
                ctls.append({"name": f, "path": full})
    return {"vis": vis, "ctls": ctls}


def handle_search_vi_strings(path: str, pattern: str) -> dict:
    _ensure_lv()
    try:
        xml_str = lv.get_vi(path).export_strings()
    except LabVIEWCOMError as e:
        return {"matches": [], "error": str(e)}
    matches = []
    for m in re.finditer(pattern, xml_str, re.IGNORECASE):
        start = max(0, m.start() - 60)
        end = min(len(xml_str), m.end() + 60)
        context = xml_str[start:end].replace("\n", " ").strip()
        matches.append({"line": m.group(), "context": context})
    return {"matches": matches}


def handle_find_references(directory: str, target: str) -> dict:
    _ensure_lv()
    references = []
    for root, dirs, files in os.walk(directory):
        for f in files:
            if not f.lower().endswith(".vi"):
                continue
            full = os.path.join(root, f)
            try:
                vi = lv.get_vi(full)
                callees = vi.get_callees()
                if any(target in c for c in callees):
                    references.append({"vi": f, "path": full})
            except Exception:
                continue
    return {"references": references}


def handle_get_type_def_structure(path: str) -> dict:
    _ensure_lv()
    try:
        xml_str = lv.get_vi(path).export_strings()
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return {"name": os.path.basename(path), "type": "Unknown", "children": []}

    def parse_node(node):
        name = node.get("name", "")
        ntype = node.get("type", "Unknown")
        result = {"name": name, "type": ntype, "children": []}
        if ntype == "Cluster":
            content = node.find("CONTENT")
            if content is not None:
                for child in content:
                    result["children"].append(parse_node(child))
        elif ntype in ("Enum", "Ring"):
            strings_el = node.find(".//STRINGS")
            if strings_el is not None:
                items = [item.text or "" for item in strings_el.findall("ITEM")]
                result["children"] = items
        elif ntype == "Array":
            content = node.find("CONTENT")
            if content is not None and len(content) > 0:
                result["children"].append(parse_node(content[0]))
        return result

    for control in root.iter("CONTROL"):
        return parse_node(control)
    return {"name": os.path.basename(path), "type": "Unknown", "children": []}


def handle_get_labview_version() -> dict:
    _ensure_lv()
    return {"version": lv.get_version()}


def handle_analyze_project(directory: str) -> dict:
    _ensure_lv()
    files = []
    for root, dirs, fnames in os.walk(directory):
        for f in fnames:
            full = os.path.join(root, f)
            if f.lower().endswith(".vi"):
                entry = {"name": f, "path": full, "type": "vi", "details": {}, "controls": [], "callees": []}
                try:
                    vi = lv.get_vi(full)
                    entry["details"] = {"name": vi.get_name(), "description": vi.get_description()}
                    try:
                        entry["callees"] = vi.get_callees()
                    except Exception:
                        pass
                except Exception:
                    pass
                files.append(entry)
            elif f.lower().endswith(".ctl"):
                files.append({"name": f, "path": full, "type": "ctl", "details": {}, "controls": [], "callees": []})
    return {"files": files}


def handle_echo(text: str) -> str:
    return f"You said: {text}"


# ═══════════════════════════════════════════════════════════════════════════
# HANDLER DISPATCH MAP
# ═══════════════════════════════════════════════════════════════════════════

HANDLER_MAP = {
    "reset_module": handle_reset_module,
    "ping_labview": handle_ping_labview,
    "smart_new_vi": handle_smart_new_vi,
    "smart_save_and_finish": handle_smart_save_and_finish,
    "smart_add_object": handle_smart_add_object,
    "smart_add_object_inside": handle_smart_add_object_inside,
    "smart_add_with_constants": handle_smart_add_with_constants,
    "smart_while_loop": handle_smart_while_loop,
    "smart_for_loop": handle_smart_for_loop,
    "smart_case_structure": handle_smart_case_structure,
    "smart_feedback_node": handle_smart_feedback_node,
    "smart_connect_objects": handle_smart_connect_objects,
    "smart_wire": handle_smart_wire,
    "smart_create_control": handle_smart_create_control,
    "delete_object": handle_delete_object,
    "rename_object": handle_rename_object,
    "set_value": handle_set_value,
    "open_vi": handle_open_vi,
    "run_vi": handle_run_vi,
    "get_vi_error_list": handle_get_vi_error_list,
    "get_object_terminals": handle_get_object_terminals,
    "get_object_help": handle_get_object_help,
    "add_to_selection": handle_add_to_selection,
    "remove_from_selection": handle_remove_from_selection,
    "clear_selection_list": handle_clear_selection_list,
    "enclose_selection": handle_enclose_selection,
    "connect_to_pane": handle_connect_to_pane,
    "get_vi_details": handle_get_vi_details,
    "get_vi_strings": handle_get_vi_strings,
    "get_vi_block_diagram": handle_get_vi_block_diagram,
    "get_vi_front_panel": handle_get_vi_front_panel,
    "get_vi_hierarchy": handle_get_vi_hierarchy,
    "get_vi_call_chain": handle_get_vi_call_chain,
    "get_connector_pane": handle_get_connector_pane,
    "get_available_objects": handle_get_available_objects,
    "get_control": handle_get_control,
    "get_enum": handle_get_enum,
    "get_project": handle_get_project,
    "list_project_files": handle_list_project_files,
    "list_vis": handle_list_vis,
    "search_vi_strings": handle_search_vi_strings,
    "find_references": handle_find_references,
    "get_type_def_structure": handle_get_type_def_structure,
    "get_labview_version": handle_get_labview_version,
    "analyze_project": handle_analyze_project,
    "echo": handle_echo,
}
