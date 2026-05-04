"""Tool definitions, input/output schemas, and helper constants.

Each tool has a name, description, and JSON Schema for its input parameters.
"""

from typing import Any

TOOLS: list[dict[str, Any]] = [
    # ── Recovery / Health ──────────────────────────────────────────────
    {
        "name": "reset_module",
        "description": "Emergency recovery — use when LabVIEW becomes unreachable. Clears state, stops module with timeout, probes LabVIEW COM, restarts module.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "ping_labview",
        "description": "Health check — verify LabVIEW and the COM bridge are reachable. Returns status='ok' or status='unreachable'.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },

    # ── Smart VI Lifecycle ─────────────────────────────────────────────
    {
        "name": "smart_new_vi",
        "description": (
            "Create a new blank VI with full lifecycle management. "
            "Auto-pings LabVIEW, starts the DQMH module if not already running, "
            "creates a new VI, and returns the vi_id. This is the FIRST call for any new project."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "smart_save_and_finish",
        "description": (
            "Save the current VI, auto-arrange the block diagram (Ctrl+U), and stop the DQMH module. "
            "This is the LAST call when finishing a project. Takes the file path to save to."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to save the .vi file."},
                "vi_id": {"type": "integer", "description": "VI reference ID (default 0 = last created VI).", "default": 0},
            },
            "required": ["path"],
        },
    },

    # ── Smart Object Placement ─────────────────────────────────────────
    {
        "name": "smart_add_object",
        "description": (
            "Add a LabVIEW object with automatic safeguards: pings LabVIEW to verify connectivity, "
            "validates the object_name against the confirmed palette list (caches list on first call), "
            "places the object, queries its terminals, and returns the object_id plus full terminal info. "
            "Use for top-level block diagram objects."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Exact LabVIEW palette name."},
                "diagram_id": {"type": "integer", "description": "Target diagram reference ID (0 = top-level).", "default": 0},
                "position_x": {"type": "integer", "description": "X coordinate on diagram.", "default": 0},
                "position_y": {"type": "integer", "description": "Y coordinate on diagram.", "default": 0},
            },
            "required": ["object_name"],
        },
    },
    {
        "name": "smart_add_object_inside",
        "description": (
            "Place an object INSIDE a structure (loop or case). Auto-pings LabVIEW, "
            "resolves the structure's sub-diagram ID, validates the palette name, "
            "places the object inside, and returns object_id plus terminal info."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_object_id": {"type": "integer", "description": "Object ID of the parent structure (loop/case)."},
                "object_name": {"type": "string", "description": "Exact LabVIEW palette name to place inside."},
                "case_index": {"type": "integer", "description": "Sub-diagram index for Case Structures (default 0).", "default": 0},
                "position_x": {"type": "integer", "description": "X coordinate inside the structure.", "default": 0},
                "position_y": {"type": "integer", "description": "Y coordinate inside the structure.", "default": 0},
            },
            "required": ["parent_object_id", "object_name"],
        },
    },
    {
        "name": "smart_add_with_constants",
        "description": (
            "Add a fully-configured function node in one call: places the object, creates input constants "
            "with values, creates output indicators, and returns all IDs and terminal info. "
            "Pass input_values as list of {terminal_index, value} pairs and output_indicators as list of terminal_index."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Exact LabVIEW palette name."},
                "diagram_id": {"type": "integer", "description": "Target diagram reference ID (0 = top-level).", "default": 0},
                "position_x": {"type": "integer", "description": "X coordinate on diagram.", "default": 0},
                "position_y": {"type": "integer", "description": "Y coordinate on diagram.", "default": 0},
                "input_values": {
                    "type": "array",
                    "description": "Array of {terminal_index: int, value: string} to create input constants.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "terminal_index": {"type": "integer"},
                            "value": {"type": "string"},
                        },
                        "required": ["terminal_index", "value"],
                    },
                },
                "output_indicators": {
                    "type": "array",
                    "description": "Array of terminal_index integers to create output indicators.",
                    "items": {"type": "integer"},
                },
            },
            "required": ["object_name"],
        },
    },

    # ── Smart Structures ───────────────────────────────────────────────
    {
        "name": "smart_while_loop",
        "description": (
            "Add a complete While Loop in one call: places the loop, wires the stop condition constant, "
            "gets the sub-diagram ID for placing inner objects. Returns loop_object_id, diagram_id, and terminals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "stop_condition": {"type": "string", "description": "Stop condition value: 'true' or 'false'.", "default": "false"},
                "position_x": {"type": "integer", "description": "X coordinate on diagram.", "default": 0},
                "position_y": {"type": "integer", "description": "Y coordinate on diagram.", "default": 0},
                "diagram_id": {"type": "integer", "description": "Target diagram reference ID (0 = top-level).", "default": 0},
            },
            "required": [],
        },
    },
    {
        "name": "smart_for_loop",
        "description": (
            "Add a complete For Loop in one call: places the loop, wires the iteration count constant, "
            "gets the sub-diagram ID for placing inner objects. Returns loop_object_id, diagram_id, and terminals."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "iterations": {"type": "integer", "description": "Number of iterations (wired to count terminal).", "default": 10},
                "position_x": {"type": "integer", "description": "X coordinate on diagram.", "default": 0},
                "position_y": {"type": "integer", "description": "Y coordinate on diagram.", "default": 0},
                "diagram_id": {"type": "integer", "description": "Target diagram reference ID (0 = top-level).", "default": 0},
            },
            "required": [],
        },
    },
    {
        "name": "smart_case_structure",
        "description": (
            "Add a Case Structure with all sub-diagram IDs resolved. "
            "Returns the case_object_id and a map of {case_index: diagram_id} for placing objects inside each case."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "num_cases": {"type": "integer", "description": "Number of cases (sub-diagrams to resolve).", "default": 2},
                "position_x": {"type": "integer", "description": "X coordinate on diagram.", "default": 0},
                "position_y": {"type": "integer", "description": "Y coordinate on diagram.", "default": 0},
                "diagram_id": {"type": "integer", "description": "Target diagram reference ID (0 = top-level).", "default": 0},
            },
            "required": [],
        },
    },
    {
        "name": "smart_feedback_node",
        "description": (
            "Add a Feedback Node with initializer value in one call: places the node, creates the init constant, "
            "sets its value. Returns object_id and terminal info. Use parent_object_id to place inside a loop/case."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "init_value": {"type": "string", "description": "Initial value for the feedback node (e.g. '0').", "default": "0"},
                "position_x": {"type": "integer", "description": "X coordinate.", "default": 0},
                "position_y": {"type": "integer", "description": "Y coordinate.", "default": 0},
                "diagram_id": {"type": "integer", "description": "Target diagram reference ID (0 = top-level). Ignored if parent_object_id is set.", "default": 0},
                "parent_object_id": {"type": "integer", "description": "If set, place inside this structure (loop/case). Resolves sub-diagram automatically.", "default": 0},
                "case_index": {"type": "integer", "description": "Sub-diagram index when parent_object_id is a Case Structure (default 0).", "default": 0},
            },
            "required": [],
        },
    },

    # ── Smart Wiring ───────────────────────────────────────────────────
    {
        "name": "smart_connect_objects",
        "description": (
            "Connect two objects with automatic terminal resolution: pings LabVIEW, "
            "queries terminal info for both source and destination objects (caches results), "
            "resolves logical terminal indices to actual terminal indices, then wires them."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_object_reference": {"type": "integer", "description": "Object ID of the source."},
                "from_object_terminal_index": {"type": "integer", "description": "Logical output terminal index on source (0-based)."},
                "to_object_reference": {"type": "integer", "description": "Object ID of the destination."},
                "to_object_terminal_index": {"type": "integer", "description": "Logical input terminal index on destination (0-based)."},
            },
            "required": ["from_object_reference", "from_object_terminal_index", "to_object_reference", "to_object_terminal_index"],
        },
    },
    {
        "name": "smart_wire",
        "description": (
            "Connect source to destination AND optionally create a constant on a destination input terminal. "
            "If constant_value is provided, creates a constant on the destination's to_terminal, sets the value, "
            "then connects from_object to to_object. IMPORTANT: from_object and to_object must be DIFFERENT objects. "
            "To create a constant on a terminal without wiring, use smart_create_control(constant=True, value='...') instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_object_reference": {"type": "integer", "description": "Object ID of the source. Must be different from to_object_reference."},
                "from_object_terminal_index": {"type": "integer", "description": "Logical output terminal on source."},
                "to_object_reference": {"type": "integer", "description": "Object ID of the destination. Must be different from from_object_reference."},
                "to_object_terminal_index": {"type": "integer", "description": "Logical input terminal on destination."},
                "constant_value": {"type": "string", "description": "If provided, creates a constant with this value on to_terminal before wiring."},
            },
            "required": ["from_object_reference", "from_object_terminal_index", "to_object_reference", "to_object_terminal_index"],
        },
    },
    {
        "name": "smart_create_control",
        "description": (
            "Create a control/indicator/constant with automatic terminal resolution: pings LabVIEW, "
            "queries the parent node's terminals, resolves the terminal index, creates the control, "
            "and returns the created_object_id with terminal details. "
            "When constant=True, use the 'value' parameter to set the constant's value in one call."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the node."},
                "terminal_index": {"type": "integer", "description": "Logical terminal index on the node (0-based). For inputs this indexes into the inputs list; for outputs this indexes into the outputs list."},
                "constant": {"type": "boolean", "description": "If True, creates a constant (inputs only).", "default": False},
                "is_input": {"type": "boolean", "description": "If True, resolve as input terminal (control). If False, resolve as output terminal (indicator). Auto-detects when omitted.", "default": None},
                "value": {"type": "string", "description": "If provided, sets the created control/constant to this value (e.g. '100', 'true', '0')."},
            },
            "required": ["object_id", "terminal_index"],
        },
    },

    # ── Object Editing ─────────────────────────────────────────────────
    {
        "name": "delete_object",
        "description": "Delete an object from a VI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the object to delete."},
            },
            "required": ["object_id"],
        },
    },
    {
        "name": "rename_object",
        "description": "Rename a control/indicator on a VI front panel or block diagram.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the object to rename."},
                "new_name": {"type": "string", "description": "New name for the object."},
            },
            "required": ["object_id", "new_name"],
        },
    },
    {
        "name": "set_value",
        "description": "Set the value of a constant, control, or indicator.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the object."},
                "value": {"type": "string", "description": "Value to set (number as string, e.g. '2')."},
            },
            "required": ["object_id", "value"],
        },
    },

    # ── VI Operations ──────────────────────────────────────────────────
    {
        "name": "open_vi",
        "description": "Open a VI in LabVIEW so it becomes compatible with COM operations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to the .vi or .ctl file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_vi",
        "description": "Run a VI with optional control values. Returns control values after execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to the .vi file."},
                "controls": {"type": "object", "description": "Optional dict of control name -> value pairs."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_vi_error_list",
        "description": "Get the compilation error list for a VI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vi_reference": {"type": "integer", "description": "Reference ID of the VI (default 0).", "default": 0},
            },
            "required": [],
        },
    },
    {
        "name": "get_object_terminals",
        "description": "Get the terminal names, types, and indices for an object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the object."},
            },
            "required": ["object_id"],
        },
    },
    {
        "name": "get_object_help",
        "description": "Get detailed help/documentation for a LabVIEW object.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the object."},
            },
            "required": ["object_id"],
        },
    },

    # ── Selection Operations ───────────────────────────────────────────
    {
        "name": "add_to_selection",
        "description": "Add an object to the current LabVIEW selection list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the object to select."},
            },
            "required": ["object_id"],
        },
    },
    {
        "name": "remove_from_selection",
        "description": "Remove an object from the current LabVIEW selection list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the object to deselect."},
            },
            "required": ["object_id"],
        },
    },
    {
        "name": "clear_selection_list",
        "description": "Clear all objects from the current LabVIEW selection list.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "enclose_selection",
        "description": "Enclose the currently selected objects in a structure.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "structure_name": {"type": "string", "description": "Type of structure (e.g., 'Case Structure', 'While Loop #1')."},
            },
            "required": ["structure_name"],
        },
    },

    # ── Connector Pane ─────────────────────────────────────────────────
    {
        "name": "connect_to_pane",
        "description": "Wire a terminal to the VI connector pane.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_id": {"type": "integer", "description": "Reference ID of the front panel control/indicator."},
                "pane_index": {"type": "integer", "description": "Connector pane terminal index."},
            },
            "required": ["object_id", "pane_index"],
        },
    },

    # ── Inspection / Read-Only Tools ──────────────────────────────────
    {
        "name": "get_vi_details",
        "description": "Takes a VI path (.vi or .ctl). Returns description and metadata of the VI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi or .ctl file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_vi_strings",
        "description": "Exports full XML structure of a VI or .ctl file including all control names, types, descriptions, default values, and connector pane details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi or .ctl file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_vi_block_diagram",
        "description": "Returns a PNG screenshot of a VI's block diagram.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_vi_front_panel",
        "description": "Returns a PNG screenshot of a VI's front panel. Works on .vi and .ctl files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi or .ctl file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_vi_hierarchy",
        "description": "Returns subVIs called (callees) and VIs that call this one (callers).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_vi_call_chain",
        "description": "Get recursive callees (dependency tree) up to a given depth.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi file."},
                "depth": {"type": "integer", "description": "Maximum recursion depth (default 3).", "default": 3},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_connector_pane",
        "description": "Parse the connector pane info from a VI's XML export.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_available_objects",
        "description": "Returns a list of all objects that can be added. Use EXACT names from this list.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_control",
        "description": "Returns a screenshot of the content (front panel) of a .ctl file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .ctl file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_enum",
        "description": "Returns the elements of an enum stored in a .ctl file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .ctl file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_project",
        "description": "Returns the XML content of a LabVIEW Project- or Library-File.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to project/library file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_project_files",
        "description": "Parses a .lvproj and returns structured lists of all VIs, CTLs, and libraries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .lvproj file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_vis",
        "description": "Recursively scan a directory for all .vi and .ctl files.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory path to scan."},
            },
            "required": ["directory"],
        },
    },
    {
        "name": "search_vi_strings",
        "description": "Search for a text pattern (regex) within a VI's XML export.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .vi file."},
                "pattern": {"type": "string", "description": "Regex pattern to search for."},
            },
            "required": ["path", "pattern"],
        },
    },
    {
        "name": "find_references",
        "description": "Search all VIs in a directory for ones that reference a given file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to search in."},
                "target": {"type": "string", "description": "Target filename to find references to."},
            },
            "required": ["directory", "target"],
        },
    },
    {
        "name": "get_type_def_structure",
        "description": "Parse a .ctl typedef into a nested JSON structure.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Full path to .ctl file."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "get_labview_version",
        "description": "Return the LabVIEW version info.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "analyze_project",
        "description": "One-call full project scan. Finds all .vi and .ctl files, extracts name, description, and callees.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to scan."},
            },
            "required": ["directory"],
        },
    },

    # ── Utility ────────────────────────────────────────────────────────
    {
        "name": "echo",
        "description": "Echo test — returns 'You said: {text}'. No LabVIEW call required.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo back."},
            },
            "required": ["text"],
        },
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}
TOOL_MAP = {t["name"]: t for t in TOOLS}

CONFIRMED_PALETTE_NAMES = {
    "For Loop", "While Loop #1", "Case Structure",
    "Feedback Node",
    "Add", "Subtract", "Multiply", "Divide", "Increment", "Decrement",
    "Negate", "Absolute Value", "Square Root", "Reciprocal",
    "Round To Nearest", "Quotient & Remainder", "Compound Arithmetic",
    "Greater?", "Less?", "Equal?", "Not Equal?", "In Range and Coerce", "Select",
    "And", "Or", "Not", "Xor",
    "Wait (ms)", "Tick Count (ms)",
    "Random Number (0-1)",
    "Build Array", "Index Array", "Array Size", "Split Number",
    "Concatenate Strings", "String Length", "Format Into String", "Scan From String",
    "Bundle", "Unbundle", "Bundle By Name", "Unbundle By Name",
    "Type Cast",
    "Numeric Control (modern)", "Numeric Indicator (modern)",
    "Local Variable", "Global Variable",
}

FORBIDDEN_STANDALONE = {
    "Numeric Constant", "String Constant", "Boolean Constant",
    "Array Constant", "Cluster Constant", "Path Constant",
    "Ring Constant", "Color Box Constant", "Error Cluster Constant",
    "Variant Constant", "Refnum Constant", "Timestamp Constant",
}
