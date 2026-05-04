# LabVIEW Assistant — Enhanced MCP Server

> An enhanced [Model Context Protocol](https://modelcontextprotocol.io/) server that enables AI assistants (Claude Desktop, Cursor, Kilo, etc.) to programmatically create and manipulate LabVIEW VIs through structured tool calls.

**Fork of [CalmyJane/labview_assistant](https://github.com/CalmyJane/labview_assistant)** with a completely rewritten Python layer featuring smart tool abstractions, terminal caching, structure-aware verification, and COM fallback error recovery.

---

## Key Differences from Upstream

| Feature | Upstream (CalmyJane) | This Fork |
|---|---|---|
| Architecture | Single `main.py` auto-generated from LabVIEW | Modular Python package (`labview_mcp/`) with dedicated handlers, tools, and COM client |
| Tool abstraction | Raw DQMH calls exposed directly | **Smart tools** with auto-ping, verification, caching, error recovery |
| Terminal resolution | Manual terminal index tracking | **Automatic logical↔actual terminal mapping** with cache |
| Structure support | Basic add/wire | **While Loops, For Loops, Case Structures, Feedback Nodes** with inner placement |
| Error handling | Pass-through DQMH errors | **COM fallback** for save operations, structure-aware verification |
| Object placement | Top-level only | **Objects inside structures** (loops, cases) via `smart_add_object_inside` |
| VI inspection | None | **Screenshots, XML export, error list, hierarchy, call chain** |
| Save | DQMH-only | **DQMH + COM fallback** for new VIs |
| Controls/indicators | Manual create + wire | **Auto-wiring** controls and indicators with `smart_create_control` |

---

## Prerequisites

- **Windows 10/11** (LabVIEW COM requires Windows)
- **LabVIEW 2021+** installed and licensed (tested with LabVIEW 2025)
- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** package manager (recommended) or `pip`
- An MCP-compatible AI client (Claude Desktop, Cursor, Kilo CLI, etc.)

---

## Installation

### Option A: Quick Setup with `uv` (Recommended)

```bash
# 1. Clone the repo
git clone https://github.com/zeshanabdullah10/labview_assistant.git
cd labview_assistant

# 2. Install dependencies
uv sync

# 3. Install as MCP server in Claude Desktop
uv run mcp install labview_mcp/run_server.py

# 4. Restart Claude Desktop (right-click tray icon → Quit, then reopen)
```

### Option B: Manual Setup with `pip`

```bash
# 1. Clone the repo
git clone https://github.com/zeshanabdullah10/labview_assistant.git
cd labview_assistant

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install mcp[cli] pywin32

# 4. Install as MCP server
mcp install labview_mcp/run_server.py
```

### Option C: Using with Kilo CLI

Add to your Kilo MCP configuration (`kilo.json` or `.kilo/config.json`):

```json
{
  "mcpServers": {
    "LabVIEW-MCP": {
      "command": "uv",
      "args": ["--directory", "D:/labview_assistant", "run", "labview_mcp/run_server.py"],
      "type": "stdio"
    }
  }
}
```

### Option D: Using with Cursor IDE

Add to your Cursor MCP settings (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "LabVIEW-MCP": {
      "command": "uv",
      "args": ["--directory", "D:/labview_assistant", "run", "labview_mcp/run_server.py"]
    }
  }
}
```

---

## Usage

Once installed, the AI assistant can use the MCP tools automatically. Here's a typical workflow:

1. **AI calls `smart_new_vi`** — creates a blank VI in LabVIEW
2. **AI places objects** — `smart_add_object`, `smart_while_loop`, `smart_for_loop`, `smart_case_structure`
3. **AI wires and configures** — `smart_create_control`, `smart_connect_objects`, `set_value`, `rename_object`
4. **AI verifies** — `get_vi_error_list` to check for compilation errors
5. **AI saves** — `smart_save_and_finish`

Example prompt for your AI assistant:

> Create a LabVIEW VI that takes two numbers as inputs, adds them together, and displays the result. Use front panel controls for inputs and an indicator for the output.

---

## Build Workflow — LV-Plan First

This project uses a **structured build workflow** that produces better results than ad-hoc VI construction. Every VI starts with an **LV-Plan** — a text document fully specifying the VI's topology before any LabVIEW call is made.

### Typical AI Build Sequence

```
1. AI writes LV-Plan (structured text) → 2. smart_new_vi → 3. smart_for_loop
4. smart_add_object_inside × N         → 5. smart_feedback_node × N
6. smart_create_control(constant=True) × N → 7. smart_connect_objects × N
8. smart_create_control(is_input=False) × N → 9. rename_object × N
10. smart_save_and_finish → User saves manually (Ctrl+S)
```

### Verified Example Programs

The following VIs have been built and verified end-to-end:

**Example 1: EMA Temperature Monitor** (50 iterations)
- Random temperature (20-30°C) → EMA filter (α=0.2) → dual alarm (>28°C high, <22°C low)
- 10 nodes, 9 wires, 1 Feedback Node
- Indicators: `EMA Temperature`, `High Alarm`, `Low Alarm`

**Example 2: PID Controller Simulation** (100 iterations)
- Random PV (0-100) vs setpoint (50) → P/I/D terms → PID output
- 12 nodes, 15 wires, 2 Feedback Nodes (integral accumulator + previous error)
- Fan-out: error signal goes to 4 destinations simultaneously
- Indicators: `Error`, `PID Output`

**Example 3: Fibonacci Generator with EMA** (20 iterations)
- Cross-wired Fibonacci (fn_a=0, fn_b=1) → EMA smoothing (α=0.3) → deviation + threshold
- 9 nodes, 12 wires, 3 Feedback Nodes
- Indicators: `Fibonacci Number`, `EMA of Fibonacci`, `Threshold Exceeded`, `Deviation`

The `AGENTS.md` file in this repo contains the full LV-Plan for each example.

### Documentation Files

| File | Purpose |
|---|---|
| `AGENTS.md` | Agent instructions: smart tool build workflow, constraints, verified objects, signal processing patterns, and 3 fully-documented example programs with LV-Plans |
| `.kilo/labview-skill/SKILL.md` | LabVIEW style guide: LV-Plan format, Feedback Node rules, architecture patterns, front panel/block diagram conventions, error handling, and code review checklist |

These files are designed to be read by the AI assistant during build sessions. The AI should write an LV-Plan before any VI construction, following the Validation Checklist in `SKILL.md`.

---

## Available Tools (40+)

### VI Lifecycle
| Tool | Description |
|---|---|
| `smart_new_vi` | Create a new blank VI with full lifecycle management |
| `smart_save_and_finish` | Save VI, auto-arrange diagram (Ctrl+U), stop module |
| `open_vi` | Open an existing VI from disk |
| `run_vi` | Run a saved VI with optional control values |

### Object Placement
| Tool | Description |
|---|---|
| `smart_add_object` | Place any palette object on the block diagram |
| `smart_add_object_inside` | Place an object inside a structure (loop/case) |
| `smart_add_with_constants` | One-call: place function + create constants + create indicators |

### Structures
| Tool | Description |
|---|---|
| `smart_while_loop` | Add a While Loop with stop condition and inner diagram ID |
| `smart_for_loop` | Add a For Loop with iteration count and iteration terminal |
| `smart_case_structure` | Add a Case Structure with all sub-diagram IDs resolved |
| `smart_feedback_node` | Add a Feedback Node with init value (supports placement inside loops) |

### Wiring
| Tool | Description |
|---|---|
| `smart_connect_objects` | Wire two objects with automatic terminal resolution |
| `smart_wire` | Wire + optionally create a constant on the destination |
| `smart_create_control` | Create control/indicator/constant with auto-wiring |

### Editing
| Tool | Description |
|---|---|
| `delete_object` | Delete an object from a VI |
| `rename_object` | Rename a control/indicator |
| `set_value` | Set the value of a constant/control/indicator |

### Inspection
| Tool | Description |
|---|---|
| `get_vi_error_list` | Get compilation errors for a VI |
| `get_object_terminals` | Get terminal names, types, and indices |
| `get_object_help` | Get help documentation for an object |
| `get_vi_block_diagram` | Screenshot of a VI's block diagram |
| `get_vi_front_panel` | Screenshot of a VI's front panel |
| `get_vi_details` | VI metadata (name, path, description, etc.) |
| `get_vi_strings` | Full XML export of VI structure |
| `get_vi_hierarchy` | SubVIs called (callees) and callers |
| `get_available_objects` | List all placeable object names |

### Selection & Connector Pane
| Tool | Description |
|---|---|
| `add_to_selection` / `remove_from_selection` / `clear_selection_list` | Manage object selection |
| `enclose_selection` | Enclose selected objects in a structure |
| `connect_to_pane` | Wire a terminal to the VI connector pane |

### Project Analysis
| Tool | Description |
|---|---|
| `analyze_project` | Full project scan: VIs, CTLs, callees |
| `list_vis` | Recursively scan directory for .vi/.ctl files |
| `list_project_files` | Parse .lvproj for all VIs, CTLs, libraries |
| `find_references` | Find VIs that reference a given file |
| `search_vi_strings` | Regex search within a VI's XML export |
| `get_type_def_structure` | Parse .ctl typedef into nested JSON |
| `get_enum` | Extract enum values from a .ctl file |

---

## Architecture

```
labview_assistant/
├── .kilo/                           # Kilo CLI configuration
│   └── labview-skill/                # LabVIEW skill package
│       └── SKILL.md                 # LabVIEW style guide & LV-Plan format
├── AGENTS.md                        # Agent instructions & verified examples
├── Scripting Server/                # DQMH module VIs (LabVIEW side)
│   ├── __init__.py
│   ├── run_server.py               # MCP server entry point
│   ├── tools.py                    # Tool schemas (JSON Schema definitions)
│   ├── handlers.py                 # Tool handler implementations
│   ├── labview_com.py              # LabVIEW COM client + DQMH scripting client
│   └── Scripting Server/           # DQMH module VIs (LabVIEW side)
│       ├── Main.vi                 # DQMH main module
│       ├── add_object.vi           # Place objects on diagram
│       ├── connect_objects.vi      # Wire terminals
│       ├── create_control.vi       # Create controls/indicators
│       ├── save_vi.vi              # Save VIs
│       ├── get_object_terminals.vi # Query terminal info
│       ├── get_structure_diagram.vi # Get sub-diagram IDs
│       ├── get_loop_iteration_terminal.vi
│       ├── get_loop_conditional_terminal.vi
│       └── ... (180+ VIs)
├── LabVIEW_Server/                 # Original DQMH module (reference)
├── Tools/                          # LabVIEW tool VIs for code generation
├── pyproject.toml                  # Project config
├── config.json                     # LabVIEW allowed paths config
└── README.md
```

### How It Works

1. **Python MCP Server** (`run_server.py`) starts and exposes tools via stdio transport
2. **AI Client** (Claude/Cursor/Kilo) calls tools through the MCP protocol
3. **Handler Layer** (`handlers.py`) implements smart logic: verification, caching, error recovery
4. **DQMH Scripting Client** (`labview_com.py`) communicates with LabVIEW via COM automation
5. **LabVIEW DQMH Module** (in `Scripting Server/`) runs inside LabVIEW, executing VI scripting operations

---

## Available Palette Objects

The following objects are confirmed working with `smart_add_object`:

**Structures:** `While Loop #1`, `For Loop`, `Case Structure`, `Feedback Node`

**Math:** `Add`, `Subtract`, `Multiply`, `Divide`, `Increment`, `Decrement`, `Negate`, `Absolute Value`, `Square Root`, `Reciprocal`, `Round To Nearest`, `Quotient & Remainder`, `Compound Arithmetic`

**Comparison:** `Greater?`, `Less?`, `Equal?`, `Not Equal?`, `In Range and Coerce`, `Select`

**Boolean:** `And`, `Or`, `Not`, `Xor`

**Timing:** `Wait (ms)`, `Tick Count (ms)`

**Random:** `Random Number (0-1)`

**String:** `Concatenate Strings`, `String Length`, `Format Into String`, `Scan From String`

**Array:** `Build Array`, `Index Array`, `Array Size`

**Cluster:** `Bundle`, `Unbundle`, `Bundle By Name`, `Unbundle By Name`

**Other:** `Split Number`, `Type Cast`, `Numeric Control (modern)`, `Numeric Indicator (modern)`, `Local Variable`, `Global Variable`

Use `get_available_objects` from your AI assistant to get the current list.

---

## Troubleshooting

### "LabVIEW unreachable"
- Ensure LabVIEW is running and the LabVIEW IDE is open
- Check that LabVIEW is not showing a modal dialog (close any popups)
- Try `reset_module` to recover

### Save fails (Error 1026)
- The DQMH save may fail for newly created VIs — the server automatically falls back to a COM-based save
- Ensure the target directory exists and is writable
- Check `config.json` for allowed paths

### While Loop verification warning
- While Loops don't expose standard terminals, so verification is relaxed — this is expected
- Objects can still be placed inside While Loops via `smart_add_object_inside`

### "Module not ready"
- Run `reset_module` to restart the DQMH scripting module
- If that fails, restart LabVIEW

---

## Development

### Running Tests

The `Scripting Server/` directory contains test VIs:
- `Test_Connect_Connector_Pane.vi`
- `Test_Create_Control.vi`
- `Test_EncloseSelection.vi`
- `Test_Rename_And_Set_Value.vi`
- `Test_StructureSubdiagramsAndDeleteObject.vi`
- `Test_WireLoops.vi`
- `Test Scripting Server API.vi`

### Adding New Tools

1. Create a new DQMH Request VI in the `Scripting Server/` directory
2. Add the tool schema to `labview_mcp/tools.py`
3. Add the handler to `labview_mcp/handlers.py`
4. Register in the `HANDLER_MAP` dict
5. Run `mcp install labview_mcp/run_server.py` and restart your AI client

### Modifying LabVIEW Server VIs

Open `AI Assistant for LabVIEW.vipb` in LabVIEW to edit the DQMH module. After changes, run `Generate Python Code.vi` from the `Tools/` directory if you want to update the original-style auto-generated code (the enhanced handlers use manual implementations).

---

## License

This project follows the same license as the upstream [CalmyJane/labview_assistant](https://github.com/CalmyJane/labview_assistant) repository.

---

## Acknowledgments

- [CalmyJane](https://github.com/CalmyJane) — Original LabVIEW MCP server and DQMH scripting module
- [LabVIEW](https://www.ni.com/en/shop/labview.html) — National Instruments
- [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic
