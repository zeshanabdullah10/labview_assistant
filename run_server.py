"""Pure Python MCP server for LabVIEW automation.

Implements JSON-RPC 2.0 over stdio (stdin/stdout). All logging goes to stderr.
Supports MCP protocol: initialize, tools/list, tools/call, notifications, ping.
"""

import json
import logging
import os
import sys
import traceback
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools import TOOLS, TOOL_MAP
from handlers import HANDLER_MAP
from labview_com import LabVIEWCOMError

_logger = logging.getLogger("labview_mcp.server")

SERVER_NAME = "LabVIEW-MCP-Python"
SERVER_VERSION = "1.0.0"

INSTRUCTIONS = """MCP server for LabVIEW automation via COM.

=== SMART TOOL WORKFLOW (recommended) ===
1. smart_new_vi           — Auto-starts module + creates VI (FIRST call)
2. smart_add_object        — Places node, validates palette, returns terminals
3. smart_add_object_inside — Places node inside a loop/case structure
4. smart_add_with_constants — Places node + creates all constants + indicators
5. smart_while_loop        — Complete While Loop (stop condition + inner diagram ID)
6. smart_for_loop          — Complete For Loop (iteration count + inner diagram ID)
7. smart_case_structure    — Complete Case Structure (all diagram IDs)
8. smart_feedback_node     — Feedback Node with init value
9. smart_connect_objects   — Wire nodes (auto-resolves terminal indices)
10. smart_wire             — Wire + optionally create constant on destination
11. smart_create_control   — Create constant/indicator (auto-resolves terminal)
12. smart_save_and_finish  — Save + cleanup + stop module (LAST call)

All smart tools auto-ping LabVIEW, validate inputs, cache terminals, and resolve logical→actual terminal indices.
Use logical terminal indices (0, 1, 2...) — the smart tools map them to LabVIEW's actual terminal IDs automatically.
"""


def _log(message: str):
    _logger.info(message)
    sys.stderr.flush()


def _make_response(request_id: Any, result: Any) -> str:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }, default=str)


def _make_error(request_id: Any, code: int, message: str, data: Any = None) -> str:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": err,
    }, default=str)


def _send(message: str):
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def handle_request(request: dict) -> str | None:
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return _make_response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "instructions": INSTRUCTIONS,
        })

    elif method == "notifications/initialized":
        return None

    elif method == "ping":
        return _make_response(req_id, {})

    elif method == "tools/list":
        return _make_response(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name not in HANDLER_MAP:
            return _make_error(req_id, -32601, f"Unknown tool: {tool_name}")

        try:
            handler = HANDLER_MAP[tool_name]
            result = handler(**arguments)

            if isinstance(result, str):
                content = [{"type": "text", "text": result}]
            elif isinstance(result, dict):
                if "data_base64" in result and "format" in result:
                    content = [
                        {"type": "image", "data": result["data_base64"], "mimeType": f"image/{result['format']}"},
                        {"type": "text", "text": json.dumps({k: v for k, v in result.items() if k not in ("data_base64", "format")})},
                    ]
                else:
                    content = [{"type": "text", "text": json.dumps(result, default=str, indent=2)}]
            else:
                content = [{"type": "text", "text": str(result)}]

            return _make_response(req_id, {
                "content": content,
            })

        except LabVIEWCOMError as e:
            _log(f"LabVIEWCOMError in {tool_name}: {e}")
            return _make_response(req_id, {
                "content": [{"type": "text", "text": json.dumps({"error": str(e), "code": e.code}, default=str)}],
                "isError": True,
            })

        except Exception as e:
            _log(f"Exception in {tool_name}: {e}\n{traceback.format_exc()}")
            return _make_response(req_id, {
                "content": [{"type": "text", "text": json.dumps({"error": str(e), "type": type(e).__name__}, default=str)}],
                "isError": True,
            })

    else:
        return _make_error(req_id, -32601, f"Method not found: {method}")


def serve():
    """Main loop: read JSON-RPC messages from stdin, write responses to stdout."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    _log(f"{SERVER_NAME} v{SERVER_VERSION} starting on stdio")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            _log(f"JSON parse error: {e}")
            continue

        try:
            response = handle_request(request)
            if response is not None:
                _send(response)
        except Exception as e:
            _log(f"Unhandled server error: {e}\n{traceback.format_exc()}")
            req_id = request.get("id")
            if req_id is not None:
                _send(_make_error(req_id, -32603, f"Internal error: {e}"))


if __name__ == "__main__":
    serve()
