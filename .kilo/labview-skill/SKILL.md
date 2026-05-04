---
name: labview
description: >
  Expert LabVIEW development assistant covering style, architecture, code review, debugging,
  and best practices for graphical programming in NI LabVIEW. Use this skill whenever the user
  mentions LabVIEW, VIs (Virtual Instruments), block diagrams, front panels, NI hardware, DAQ,
  FPGA targets, Real-Time targets, connector panes, subVIs, typedefs, clusters, shift registers,
  queued message handlers (QMH), Actor Framework, DQMH, data flow programming, or any NI/National
  Instruments instrumentation and test software. Trigger on requests to write, review, refactor,
  explain, or debug LabVIEW code, as well as questions about LabVIEW project structure, style
  guides, design patterns, or NI ecosystem tooling.
---

# LabVIEW Expert Skill

This skill encodes best practices from NI's official LabVIEW Development Guidelines, the
LabVIEW Wiki Style Guide, the DQMH Consortium Style Guide, and community standards. Always
apply these when writing, reviewing, or explaining LabVIEW code.

For large or specialized topics, read the reference files in `references/`:
- `architecture.md` — QMH, Actor Framework, DQMH, producer-consumer
- `realtimeAndFPGA.md` — RT targets, FPGA, timed loops, DMA FIFOs

Note: if these reference files are not accessible in the current context, use the
Architecture Patterns table and inline notes in this file as the authoritative summary.

---

## MCP Scripting Context

When building VIs via the DQMH Scripting Server MCP tools (`server.py`), also read
`AGENTS.md`. That file documents the mandatory build workflow, confirmed working objects,
known error codes, and constraint workarounds that supplement the general style guidelines
here. The two documents are complementary:

- **This file (SKILL.md):** LabVIEW style, architecture, LV-Plan format, Build Summary format
- **AGENTS.md:** MCP operational workflow, tool selection, discovered constraints, error codes

Where these documents appear to conflict (e.g. `Build Array` inside loops), AGENTS.md
describes what the MCP scripting server actually does; this file describes general LabVIEW
best practice. Both are correct in their respective contexts.

---

## Core Principles

LabVIEW is a **dataflow language**. Data flows through wires; execution order is determined by
data dependencies, not line order. Always reason about wires first.

1. **Clarity over cleverness.** Anyone with moderate LabVIEW experience should be able to read
   the block diagram without explanation.
2. **Hierarchy and modularity.** Break large VIs into subVIs at logical boundaries. Aim for
   diagrams that fit on one screen without scrolling in more than one direction.
3. **Consistency beats perfection.** A consistent style across a project matters more than any
   single guideline.
4. **Error handling is not optional.** Wire error clusters through every VI. Disable automatic
   error handling on all VIs (set in `File > VI Properties > Execution`).
5. **Typedef everything you reuse.** Enums, clusters, and ring controls used in more than one
   place must be typedefs to ensure global consistency.

---

## Architecture Planning with LV-Plan

**Write an LV-Plan before every VI build.** This is mandatory when using MCP scripting tools
and strongly recommended for any complex VI designed manually.

An LV-Plan is a structured text document that fully specifies a VI's topology before any
LabVIEW call is made. Its purpose is to catch structural errors (wrong context, missing
init constants, type mismatches) at planning time rather than after 15+ tool calls.

### LV-Plan Format

```
## LV-Plan: <VI name>

**Description:** <One sentence: what does this VI do?>

**Nodes:**
| id         | palette_name              | type           | context              | notes                    |
|------------|---------------------------|----------------|----------------------|--------------------------|
| loop       | For Loop                  | for_loop       | root                 | iterations=100           |
| rng        | Random Number (0-1)       | function       | loop:loop            |                          |
| ema_fn     | Feedback Node             | feedback_node  | loop:loop            | init=0                   |
| mul_alpha  | Multiply                  | function       | loop:loop            | const@1=0.1 (alpha)      |
| mul_prev   | Multiply                  | function       | loop:loop            | const@1=0.9 (1-alpha)    |
| result     | Add                       | function       | loop:loop            | indicator@0              |

**Wires:**
- rng[0] → mul_alpha[0]
- ema_fn[1] → mul_prev[0]
- mul_alpha[0] → result[0]
- mul_prev[0] → result[1]
- result[0] → ema_fn[0]

**Constants:**
- mul_alpha terminal 1 = 0.1   (alpha)
- mul_prev  terminal 1 = 0.9   (1-alpha)
- loop N = 100

**Indicators:**
- result terminal 0

**Validation Checklist:**
- [ ] Every node has a confirmed palette name (from AGENTS.md verified list or prior test)
- [ ] Every Feedback Node has an init value defined before any wire connects its input
- [ ] No standalone constant objects used — all constants via `smart_create_control(constant=True)`
- [ ] While Loops use `While Loop #1` (not `While Loop`)
- [ ] Event Structures must use low-level tools (`add_object`), not smart structure tools
- [ ] Case Structures nested inside loops have ≤ 2 cases (at deep nesting)
- [ ] Indicators inside loops are via `smart_create_control(is_input=False)` on output terminals
- [ ] All wires use logical terminal indices (0-based) — smart tools resolve actual terminals automatically
- [ ] Fan-out wires (one source → multiple destinations) are listed explicitly per destination
```

### While Loop LV-Plan Example

```
## LV-Plan: While Loop Counter

**Description:** Counts iterations in a While Loop with a 100ms wait.

**Nodes:**
| id         | palette_name              | type           | context              | notes                    |
|------------|---------------------------|----------------|----------------------|--------------------------|
| loop       | While Loop #1             | while_loop     | root                 | stop_condition=false     |
| wait       | Wait (ms)                 | function       | loop:loop            | const@1=100              |
| counter_fn | Feedback Node             | feedback_node  | loop:loop            | init=0                   |
| inc        | Increment                 | function       | loop:loop            | indicator@0              |

**Wires:**
- counter_fn[1] → inc[0]
- inc[0] → counter_fn[0]

**Constants:**
- wait terminal 1 = 100
- loop stop_condition = false

**Indicators:**
- inc terminal 0
```
### LV-Plan → Smart Tools Build Sequence

The LV-Plan maps directly to the smart tool build sequence (see AGENTS.md for
the full operational workflow):

1. `smart_new_vi` — creates blank VI
2. `smart_for_loop(iterations=N)` or `smart_while_loop(stop_condition=...)` — places loop
3. `smart_add_object_inside(parent_object_id=loop_id, object_name=...)` — places each function node
4. `smart_feedback_node(init_value=..., parent_object_id=loop_id)` — places each Feedback Node with init
5. `smart_create_control(constant=True, value=..., object_id=..., terminal_index=...)` — creates each constant
6. `smart_connect_objects(from, from_idx, to, to_idx)` — wires each connection
7. `smart_create_control(is_input=False, object_id=..., terminal_index=...)` — creates each indicator
8. `rename_object(object_id, new_name)` — names indicators
9. `smart_save_and_finish(path)` — saves (expect Error 1026, user must Ctrl+S)

Do not start MCP calls until the Validation Checklist is fully checked.

---

## Mid-Build Verification

For any VI with 10+ nodes or nested structures, produce a Build Summary immediately after
the smart tool sequence completes. This verifies correctness and documents the result.

### Build Summary Format

```
## Build Summary: <VI name>

**Result:** success / failed (<n> errors)

**Object ID Map:**
| logical id | object_id | palette_name              |
|------------|-----------|---------------------------|
| loop       | 4         | For Loop                  |
| rng        | 5         | Random Number (0-1)       |
| ema_fn     | 6         | Feedback Node             |
| ...        | ...       | ...                       |

**Wiring Confirmed:**
- rng[0] → mul_alpha[0]: ✓
- mul_alpha[0] → result[0]: ✓
- result[0] → ema_fn[0]: ✓  (Feedback Node — init constant set before this wire)

**Compile Check:** clean  /  errors: <paste error list>

**Errors Encountered:**
- (none)  /  Node 'X': error 1054 — palette name variation tried: <name>

**Front Panel:** (attach screenshot from get_vi_front_panel if available)

**Notes:** (any deviations from the LV-Plan, fallbacks used, open issues)
```

If the build reports errors, use the Build Summary to diagnose before
retrying. Do not retry the full sequence blindly — isolate the failing node or wire first
using individual smart tools with `get_vi_block_diagram` after each step.

---

## Feedback Nodes

Feedback Nodes implement iteration-to-iteration memory in LabVIEW loops — they are
the dataflow equivalent of a shift register in a For/While Loop, but allow backward
wiring patterns (the output of one iteration feeds the input of the next).

### Structure

A Feedback Node has three terminals:
- **terminal 0 — input (store):** value written at end of current iteration
- **terminal 1 — output (recall):** value read at start of current iteration (previous value)
- **terminal 2 — init terminal:** initial value on the first iteration (must be a constant)

### Key rules

- Always initialize via `smart_feedback_node(init_value=...)` which creates the init constant
  and sets its value in one call. This also handles the ordering constraint (init before wiring).
- **Create the init constant BEFORE wiring the FN input to any comparison function output.**
  If the FN input inherits a void/undefined type from a comparison wire, the init terminal
  will fail with error 1075. Wire the FN to a numeric source first (e.g. `Add`, `Increment`,
  `Random Number (0-1)`) so it inherits a concrete numeric type before creating the init.
- Up to 5 Feedback Nodes in a single For Loop are confirmed working.
- FNs can be wired through Case Structure tunnels — place the FN outside the Case Structure
  but inside the same For Loop and wire through the boundary tunnels.
- Feedback Nodes are preferable to shift registers in MCP-scripted VIs because shift
  registers require explicit terminal pairing that the scripting server cannot do easily.

### Common patterns

```
Counter:       FN(init=0) output → Increment → FN input
Accumulator:   FN(init=0) output + current → Add → FN input
EMA:           α×current + (1-α)×FN(init=0) output → FN input
Previous value: FN(init=0) stores the value; output used for difference calculation
```

---

## File & Project Organization

### Naming
- Use **Spaced Pascal Case** (Book Title Case) for all files, VIs, libraries, classes, and
  directories: `Acquire Waveform.vi`, `Data Logger.lvlib`.
- Avoid special characters: no `\`, `/`, `:`, `~`, `[`, `]`, `(`, `)`, etc.
- Avoid camelCase and underscores for separation (`readData.vi` → `Read Data.vi`).
- Polymorphic VI instances: `Read File - I32.vi` (space-dash-space + instance designation).
- Typedef naming conventions:
  - `X--enum.ctl`
  - `X--cluster.ctl`
  - `X Argument--cluster.ctl`
  - `X--map.ctl`
  - Constant VIs: `X--constant.vi`, `X path--constant.vi`

### Directory Structure
```
MyApp/
├── MyApp.vi              ← top-level VI at root
├── MyApp.lvproj
├── Configuration/
│   └── (config subVIs)
├── Acquisition/
│   └── (DAQ subVIs)
├── Analysis/
├── File IO/
└── Utilities/
```
- Place top-level VIs directly under the appropriate target in the project.
- Nest libraries in their own subdirectories; keep `.lvlib` member VIs flat in that same folder.
- Never use LLBs for source code (legacy; use `.lvlib` instead).
- Remove all unused files from disk and project.
- Avoid auto-populating folders.
- Keep Windows path lengths under 150 characters (hard limit 260).

### Libraries and Classes
- Place APIs inside a library (`.lvlib`) with public/private virtual folders.
- Mark non-API VIs as **Private**.
- Name classes as **nouns**: `Waveform Reader.lvclass` not `Reads Waveforms.lvclass`.
- Name class member VIs as **verbs**: `Read Value.vi` not `Value.vi`.
- Use **Read** / **Write** (not Get/Set) for data accessor VIs in classes.
- Avoid including the class name in member VI names (LabVIEW provides namespace automatically).

---

## Front Panel Style

### General Rules
- Use **Modern** style controls for subVIs (non-GUI).
- Use **System** style controls for dialog-style VIs.
- Use **consistent** control styles across all UIs in a project.
- Set reasonable default values for controls; use data-type defaults for indicators.
- Arrange controls top-left → bottom-right in order of typical use.
- Use **Path** controls (not String) for file/directory inputs; set browse options correctly.
- Make label backgrounds transparent.
- Use `Size to Text` for single-line labels.
- Use the **Application Font** (default) for all labels.
- Avoid overlapping controls or labels.
- Do not save front panels maximized.

### Labels & Captions
- GUI VIs: **Book Title Case** for labels.
- Non-GUI VIs: **all lowercase** (except proper nouns/acronyms).
- Input/output pairs: add `in` / `out` suffixes (`error in`, `error out` exactly as shown).
- Include units in parentheses in the label: `Time Limit (s)`.
- Do **not** put default values in parentheses in the label.
- Avoid duplicate labels.
- Use `error in` / `error out` for error cluster terminals — no other naming.

### GUI (User-Facing) Front Panels
- Hide the toolbar on deployed UIs.
- Use colors sparingly and logically; prefer system colors.
- Provide keyboard shortcuts and logical tab order (left-to-right, top-to-bottom).
- Use `Panel Close?` filter event to handle window-close cleanly.
- Include a version number visible to the user.
- Disable the **Abort** button; provide a proper Stop/Exit button.
- For touch-screen targets, size controls for finger operation.
- Modal dialogs for critical user input; ensure they cannot be hidden.

### Dialog VIs
- System panel background color.
- System controls only.
- No scroll bars on the full front panel (design to fit).
- Meaningful window title.
- Center on main monitor.
- Set `Window Appearance` to Dialog via `File > VI Properties`.

---

## Connector Pane

- Use the **4-2-2-4 pattern** (12 terminals) for all VIs.
- Left terminals = inputs (controls); right terminals = outputs (indicators).
- **Bottom-left** = `error in`; **bottom-right** = `error out`.
- **Top corners** = paths, references, LabVIEW Class objects.
- Place related in/out pairs at the same relative vertical position.
- Keep empty terminals for future expansion.
- Required inputs: mark as **Required** (`Must Wire`).
- Optional inputs with good defaults: mark as **Recommended**.
- Maintain connector pane consistency across an API (same position = same role).
- Never use connector panes with more than 12 terminals — refactor into clusters first.

---

## VI Icons

- **32×32 pixels** always.
- Text-based icons suffice for most VIs; use glyphs for high-visibility API VIs.
- Font: Small Fonts, size 9, Capitalize, Center, Black.
- Text ≤ 3 lines (with library banner) or ≤ 4 lines (no banner).
- Library banner: 32×9 pixel rectangle at very top, black border.
- No colloquialisms — icons must be internationally understood.
- Match class wire color to class icon banner color.
- No non-ASCII symbols in icons (platform portability).
- In LabVIEW 2020+: use `Ctrl+Space, Ctrl+K` (Quick Drop) to auto-set text icon from filename.

---

## Block Diagram Style

### Layout
- **Left-to-right, top-to-bottom** data flow — always.
- No backward wires unless connected to a Feedback Node; label any exceptions.
- Align control terminals to the far **left**; indicator terminals to the far **right**.
- Align controls along their right edges; indicators along their left edges.
- No wires running under structures or other objects.
- Keep diagrams fitting on the monitor; if impossible, scroll in one direction only.
- Use `Ctrl+Space, Ctrl+F` (Arrange VI Window Quick Drop) to auto-position diagram.
- Do not save block diagram maximized.

### Wiring
- Wire neatly; minimize bends and crossings.
- Avoid long wires — label them if unavoidable.
- Never leave front panel terminals unwired when data should flow (use a wire, not a local var).
- Label wires when content is potentially unclear.
- Label shift registers when data meaning is non-obvious.
- Use **linked input tunnels** for data that passes through all frames of a structure.

### Colors
- Do not color block diagrams decoratively; color distracts.
- Use default colors for structures (Case, Event, etc.).
- If colors are used, apply them sparingly, intentionally, and consistently project-wide.

### Structures
- **Avoid Sequence Structures** — prefer data dependency to enforce order.
- Never use Stacked Sequence Structures.
- Set Case and Event structures wide enough to show the full selector label.
- Save VIs with the most important frame of multi-frame structures visible.
- Wire the Case selector terminal **inside** the structure (not through a tunnel).
- Do not convert non-Boolean types to Booleans just to drive a Case selector.
- For enum-wired Case structures: **no Default case** (add an explicit case for every enum value).
- Use **In Place Element Structure** to modify arrays and clusters without copies.
- Ensure For Loops behave correctly when they iterate zero times; use shift registers.
- Do not mix auto-indexing and explicit N terminal on the same For Loop.
- Use `Event Structure` for UI events — never poll controls.
- Resize Event Data Nodes to contain only necessary data; hide unused nodes entirely (LV 2020+).
- Arrange parallel loops **vertically**.
- Avoid placing control/indicator terminals inside loops unless values update every iteration.

### Functions & SubVIs
- Display the **icon** on the block diagram, not the connector pane.
- Display **terminal** (not icon) for front panel object references.
- Use `Bundle by Name` / `Unbundle by Name` — never unnamed Bundle/Unbundle.
- Use `Path` constants, not `String` constants, for file paths.
- Use built-in string constants (e.g., Space Constant, not a string with a space).
- Show names on Property Nodes, Invoke Nodes, and Call Library Function Nodes.
- Avoid named queues and notifiers — pass references by wire.
- Close every reference you open; pair Open/Close VIs (e.g., `Open`, `Close`).
- Show index display for array constants; display all elements.
- Avoid `Current VI's Path` in code destined for an executable; use `Application Directory` VI instead.
- Do not use `Value Signaling` property for inter-process communication.

### Labels & Comments
- Document non-obvious constants with an attached or free label.
- Use comments to explain non-obvious code; prefer attached labels over free labels.
- Use subdiagram labels on structure frames.
- Do not include default values in constant labels.
- Use light yellow (default) for free label comments.
- Only use line feeds in labels to separate paragraphs.
- Connect comments to the code they describe when possible.
- Use default text and background colors for labels.

---

## Data Types

- Use **Enums** (not Ring controls) for named sets of values; always make them typedefs.
- Use **typedef clusters** for any cluster used in more than one place.
- Use **Strict Type Definitions** only when appearance must be identical across all uses.
- Do not create clusters with duplicate element names.
- Use consistent data types across all modules; decide up front.
- Avoid type coercions (coercion dots = red flag); use explicit conversion VIs when needed.
- Prefer `DBL` for floating-point; use `SGL` only when memory is a constraint.
- Use `I32` as the default integer; use `U32` for counts/indices.
- Use `Boolean` arrays only when semantics truly require bit-level operations; otherwise use Enum.
- Use **Map** and **Set** (LV 2019+) where appropriate for keyed lookups.

---

## Error Handling

- Wire `error in` / `error out` through every VI.
- **Disable Automatic Error Handling** on all VIs (`File > VI Properties > Execution`).
- Handle errors at the appropriate level — log, retry, terminate, or notify.
- Avoid showing error dialogs from low-level subVIs; propagate to the caller.
- Use descriptive, user-friendly error messages; convert obscure codes.
- Custom error codes live in NI-reserved ranges:
  - `-8999` through `-8000`
  - `5000` through `9999`
  - `500000` through `599999`
- Maintain a centralized error code registry (spreadsheet or `.txt` file).
- Consider creating a custom error file (`.txt`) for the application.
- Merge errors carefully: give priority to the **first** error (top input to Merge Errors function).
- Log **all** errors to file for post-analysis.
- Use error tunnels (not shift registers) on event loops to prevent stale errors from previous iterations.

---

## Performance

- Avoid memory reallocation inside loops — no `Build Array` or `Concatenate Strings` inside loops.
  *(MCP scripting note: `Build Array` compiles inside For Loops via the scripting server but
  causes O(n²) reallocation for large N — acceptable for small iteration counts in scripted
  test VIs, not acceptable in application code. See AGENTS.md constraint O.)*
- Open and close resources (DAQ, File I/O, references) **outside** loops.
- Separate application timing from execution timing — every continuous loop needs a wait or blocking call.
- Avoid time-consuming code inside an Event Structure; use producer-consumer or similar.
- Use `In Place Element Structure` to modify compound data types without copies.
- Use `Local Variable` (not Value property) to update front panel controls at runtime.
- Use `Get/Set Control Values by Index` for bulk front panel updates.
- Avoid marking complex VIs as inline (can cause compile degradation).
- Avoid unnecessary data copies, especially large arrays.
- Consider For Loop iteration parallelism where appropriate.
- Use inlining and subroutine priority strategically.
- Avoid coercion of large arrays.
- Use subroutine priority + `Skip Subroutine Call If Busy` for RT shared-resource subVIs.

---

## Documentation

### VI Descriptions
- Write a VI description for every VI intended for external use: `File > VI Properties > Documentation`.
- Include: purpose, inputs/outputs explanation, usage notes.
- Proofread in the Context Help window (`Ctrl+H`).

### Control/Indicator Descriptions
- Right-click > `Description and Tip` for all public API controls and indicators.
- Include: purpose, data type, valid range, default value, special values.
- Designate Required / Recommended / Optional on connector pane.

### Front Panel Instructions
- Place usage instructions in a prominent label or scrollable string on the front panel.
- Link to a help file via `VI Properties > Documentation` help path.

---

## Source Code Control

- Use **Git** for all projects, no matter the size.
- Keep a `README` in the repo with setup instructions and dependency locations.
- Include a project-specific `.vipc` (VI Package Configuration) file.
- Do not commit binary installers or build artifacts.
- Commit meaningful, atomic groups of files with descriptive messages (what changed, and **why**).
- Pull/sync before starting work each session.
- Use source code control for all project-related artifacts: requirements, specs, test plans.

---

## Architecture Patterns

The following are inline summaries. If `references/architecture.md` is accessible,
read it for full guidance on QMH, Actor Framework, DQMH, and Producer-Consumer.

| Pattern | When to Use |
|---|---|
| **Simple Loop + State Machine** | Single-loop scripts, instrument control |
| **Producer-Consumer** | Decoupling UI events from processing |
| **Queued Message Handler (QMH)** | Single-module applications with multiple states |
| **DQMH** | Multi-module applications; teams; open-source consortium standard |
| **Actor Framework (AF)** | Large, highly parallel, object-oriented applications |

### QMH — Inline Summary
A single While Loop containing a dequeue-driven Case Structure. Each case represents a
state. Messages are strings or enums enqueued by the UI producer or by cases themselves
for state transitions. Use a Functional Global Variable (FGV) for module-level data.
Structure: `Dequeue → Case Structure (states) → re-enqueue next state or wait`.

### DQMH — Inline Summary
Multi-module architecture. Each module is a QMH-like loop with a dedicated Request-Response
queue and a Broadcast notifier. Modules communicate only via these channels — never by
shared variables or direct VI references. Each module has a Main VI, Helper Loop, and
Broadcast Listener. The Scripting Server (used by the MCP tools in this project) is itself
a DQMH module.

### Producer-Consumer — Inline Summary
Two parallel loops connected by a queue. Producer loop handles UI events and enqueues data.
Consumer loop dequeues and processes. Use when UI responsiveness must be decoupled from
processing time.

General rules regardless of pattern:
- Avoid global variables — prefer queues, FGVs, or class private data.
- Avoid race conditions; use appropriate synchronization (queues, DVRs, semaphores).
- Avoid Value Signaling property for IPC.
- Low-level API calls must not open dialogs on error — return error cluster to caller.
- Use configuration files (`.ini`) for values that may change; never hard-code them.

---

## DQMH Scripting — Known Constraints

This section is a quick reference. The full operational details with error codes and
workarounds are in `AGENTS.md`. Read AGENTS.md before starting any MCP VI build.

| Error | Cause | Fix |
|---|---|---|
| 1054 | Object palette name not found | Use exact name: `While Loop #1`, `Greater?`, `Random Number (0-1)`, `Numeric Indicator (modern)` |
| 1055 | Nesting depth limit in Case inside For Loop | Limit to 2 cases at that depth |
| 1057 | Numeric Constant type mismatch | Use `smart_create_control(constant=True)` on terminal instead |
| 1075 | Feedback Node init terminal type undefined | Use `smart_feedback_node(init_value=...)` to create init BEFORE wiring |
| 1026 | save_vi always fails; get_vi_error_list always returns this | Ask user to save manually (Ctrl+S); ignore for compile checks |

`While Loop #1` via `smart_while_loop` **works** — use the smart tool for placement,
stop condition wiring, and sub-diagram resolution. For While Loops containing Event
Structures, use `smart_while_loop` for the loop and low-level `add_object` for the
Event Structure.

`Event Structure` via `add_object` **works** — use low-level tools. Has 3 terminals:
0 (Event Registration Refnum in), 1 (Event Registration Refnum out), 2 (data terminal).
Can be placed inside While Loops. NOT supported by smart structure tools.

Indicators inside loops via `add_object` are **broken** — use `smart_create_control` on output terminal.

`smart_feedback_node` handles error 1075 and FN init ordering automatically.
Use it as the primary Feedback Node placement tool.

---

## VI Analyzer Integration

LabVIEW's VI Analyzer can automatically enforce many of the above guidelines. Items marked
`(VI Analyzer)` in the LabVIEW Wiki Style Guide are auto-checkable. Best practices:

- Create a `.viancfg` (or `.cfg` in older LV) per project.
- Create a custom spell-check dictionary.
- Run VI Analyzer before every code review.
- DQMH Consortium VI Analyzer Tests Suite adds additional checks — install via VIPM.
- Remove all breakpoints before distributing (`VI Analyzer > Remove Breakpoints`).
- Disable debugging before building executables.

---

## Recommended LabVIEW INI Tokens

Add to `LabVIEW.ini` for consistent team environment:

```ini
; Disable automatic error handling for all new VIs — wire error clusters explicitly
defaultErrorHandlingForNewVIs=False

; New VIs default to source-only (no compiled code committed to git)
sourceOnlyDefaultForNewVIs=True

; Speed up Quick Drop searches
QuickDropFastSearch=True

; New terminals default to Required wiring
reqdTermsByDefault=True

; defaultControlStyle=0 → Modern style for all new controls
defaultControlStyle=0

; FancyFPTerms=False → connector pane terminals show as simple squares
FancyFPTerms=False

; Show VI library and resource in bookmark manager
bookmarkmanager.showvilib=True
bookmarkmanager.showresource=True

; Standard workspace dimensions for a 1536×864 display
VIWin.DisplayWorkspaceRight=1536
VIWin.DisplayWorkspaceBottom=824
```

---

## Code Review Checklist

### VI Level
- [ ] VI description written and visible in Context Help
- [ ] Connector pane uses 4-2-2-4 pattern; error in/out at bottom corners
- [ ] Icon is 32×32, text or glyph, library banner applied
- [ ] Automatic error handling disabled
- [ ] No breakpoints left in VI
- [ ] File saved with correct window size (not maximized, fits on 1536×824)

### Front Panel
- [ ] Controls use correct style (Modern for subVIs, System for dialogs)
- [ ] All controls/indicators have labels (Book Title Case for GUI, lowercase for non-GUI)
- [ ] All controls/indicators have descriptions (for public APIs)
- [ ] Label backgrounds transparent; Application Font used
- [ ] Default values are sensible; indicators use data-type defaults
- [ ] Path controls used for file/directory inputs
- [ ] `error in` / `error out` at bottom left/right of connector pane

### Block Diagram
- [ ] Left-to-right data flow; no unexplained backward wires
- [ ] Control terminals far left; indicator terminals far right
- [ ] No wires running under objects
- [ ] Diagram fits on screen (one direction scroll max)
- [ ] No Sequence Structures
- [ ] Enum-wired Case structures have no Default case
- [ ] Error wire threaded through all nodes
- [ ] No unused local/global variables; data passes by wire
- [ ] No memory allocation inside loops (Build Array, Concat String)
- [ ] Every opened reference is closed
- [ ] Continuous loops have a wait or blocking call
- [ ] Event structures used for UI events (no polling)
- [ ] Subdiagram labels on structures
- [ ] Constants documented with labels where non-obvious
- [ ] Typedefs used for all enums and clusters
- [ ] No coercion dots (or all are intentional and explained)
- [ ] No calls to deprecated/obsolete VIs

---

## Quick Reference: Common Gotchas

| Symptom | Likely Cause | Fix |
|---|---|---|
| VI runs at 100% CPU | Loop has no wait | Add `Wait (ms)` or blocking call |
| Race condition on shared data | Global variable reads/writes in parallel | Use FGV, DVR, or queue |
| Memory grows unbounded | Build Array/Concat String inside loop | Pre-allocate, use In Place Element |
| Error lost silently | Auto error handling enabled | Disable; wire error cluster |
| SubVI icon shows connector pane | Terminals visible setting on | Right-click > Visible Items > uncheck Terminals |
| Coercion dot on wire | Data type mismatch | Add explicit conversion VI |
| `Current VI's Path` fails in EXE | Build changes path | Use `Application Directory.vi` |
| For Loop returns defaults on 0 iters | Tunnel used instead of shift register | Replace tunnel with shift register |
| Enum case structure has Default | Default catches unhandled enum values silently | Remove Default; add explicit case per value |
| Numeric Constant fails to coerce | Constant defaults to generic untyped numeric | Use `smart_create_control(constant=True)` on terminal instead (error 1057 in MCP context) |
| Feedback Node init fails with 1075 | FN input typed from comparison output first | Create init constant before wiring FN to comparison; wire FN to numeric source first |
| `While Loop` fails with 1054 | Wrong palette name used | Use `While Loop #1` (not `While Loop`) |
