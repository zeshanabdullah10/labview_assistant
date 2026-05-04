# G2 Project — Agent Instructions

## LabVIEW MCP Scripting

This project uses a Python MCP server (`server.py`) to script LabVIEW VI creation via
the DQMH Scripting Server. Before creating any VI, read SKILL.md sections:
- **"MCP Scripting Context"** — how these instructions relate to the style guide
- **"Architecture Planning with LV-Plan"** — mandatory pre-build format
- **"Mid-Build Verification"** — mandatory post-build format for complex VIs
- **"DQMH Scripting — Known Constraints"** — full constraint and error code reference

This file documents the operational workflow and discovered constraints. SKILL.md
documents the format specifications. They are complementary — read both.

---

## Build Process (MANDATORY)

### Step 1 — Write an LV-Plan before building

Before any MCP call, produce an LV-Plan in the format defined in SKILL.md
"Architecture Planning with LV-Plan". The plan must include:
- **Description**: one sentence of what the VI does
- **Nodes**: every object with its logical id, palette name, context (root / loop / case), and type
- **Wires**: every connection as `from_id[terminal] → to_id[terminal]`
- **Constants**: every input constant with terminal index and value
- **Indicators**: every output indicator with terminal index
- **Validation Checklist**: run the checklist from SKILL.md before proceeding

**Never start MCP calls without a completed, validated LV-Plan.**

### Step 2 — Build using Smart Tools

Execute the LV-Plan using the smart tool sequence below. The smart tools handle
terminal resolution, type safety, and error prevention automatically.

**Build sequence (every VI):**

1. **`smart_new_vi`** — creates blank VI, starts module if needed, returns vi_id
2. **`smart_for_loop`** or **`smart_while_loop`** — places loop structure, wires iteration/stop constant,
   returns `loop_object_id` and `inner_diagram_id`
3. **`smart_add_object_inside`** (×N) — places each function node inside the loop structure using
   `parent_object_id` from step 2. Batch all independent placements in parallel.
4. **`smart_feedback_node`** (×N) — places Feedback Nodes with init values inside the loop.
   Must be done BEFORE wiring FN inputs to comparison outputs (to prevent error 1075).
5. **`smart_create_control(constant=True)`** (×N) — creates typed constants on terminal inputs.
   Batch all independent constant creations in parallel. **Never use standalone `Numeric Constant`.**
6. **`smart_connect_objects`** (×N) — wires all connections using logical terminal indices (0-based).
   Batch all independent wires in parallel.
7. **`smart_create_control(is_input=False)`** (×N) — creates output indicators on terminal outputs.
8. **`rename_object`** (×N) — gives indicators meaningful names.
9. **`smart_save_and_finish`** — attempts save (expect Error 1026), stops module.
   Ask user to save manually with Ctrl+S.

**Do not use raw `add_object`, `connect_objects`, or `create_control`** — the smart
prefixed versions handle pinging, terminal resolution, type caching, and error recovery.

### Step 3 — Generate a Build Summary after building

For any VI with 10+ nodes or nested structures, produce a Build Summary immediately
after building completes. Format defined in SKILL.md "Mid-Build Verification". Include:
- Actual object IDs mapped to logical IDs
- Wiring map with from/to confirmed
- Compile check result (clean or error list)
- Front panel screenshot if available (`get_vi_front_panel`)

---

## Tool Selection Guide

| Goal | Use |
|---|---|
| Build a new VI (any loop type) | Smart tool sequence: `smart_new_vi` → `smart_for_loop`/`smart_while_loop` → `smart_add_object_inside` → `smart_feedback_node` → `smart_create_control` → `smart_connect_objects` → `smart_save_and_finish` |
| Place objects inside a structure | `smart_add_object_inside` (resolves sub-diagram automatically) |
| Place a Feedback Node with init | `smart_feedback_node` (creates init constant in one call) |
| Create typed constants | `smart_create_control(constant=True, value=...)` |
| Create output indicators | `smart_create_control(is_input=False)` or `smart_create_control(object_id, terminal_index)` |
| Wire two objects | `smart_connect_objects` (resolves logical→actual terminals) |
| Wire + create constant in one call | `smart_wire(from, to, constant_value=...)` |
| Place a case structure | `smart_case_structure` (resolves all sub-diagram IDs) |
| Inspect what objects are available | `get_available_objects` — see verified/unverified split |
| Debug a failed placement | `ping_labview` first, then retry the smart tool |
| Read a VI's structure | `get_vi_strings`, `get_connector_pane`, `get_type_def_structure` |
| Visually inspect a VI | `get_vi_front_panel`, `get_vi_block_diagram` |
| Run a VI and read results | `run_vi` with `controls` parameter |
| Save a scripted VI | Ask the user to save manually (Ctrl+S) — `save_vi` fails with error 1026 |

---

## Known Constraints and Error Codes

These are confirmed through testing on 28+ complex VIs.

### Fundamental limitations

**A. Smart tools replace `build_vi_from_plan`.**
The smart tools (`smart_new_vi`, `smart_for_loop`, `smart_add_object_inside`, etc.)
are now the primary build tools. They handle terminal resolution, type coercion,
FN init ordering, and error recovery automatically. Use them in the sequence
described in Step 2 above.

**B. `save_vi` fails with error 1026** on all tested path formats and VI types.
Workaround: inform the user and ask them to save manually from LabVIEW (Ctrl+S).
This is a known server-side bug; no path variation has been found to work.

**C. Indicators cannot be placed inside loops via `add_object`.**
Use `smart_create_control` on the function's output terminal instead. It auto-wires
and handles type matching. The smart tools handle this automatically.

**D. `get_object_terminals` returns empty for front panel indicators.**
You cannot wire to indicators created via `add_object`. Use `smart_create_control`
(which auto-wires) or terminal_index=0 as a fallback for some indicator types.

**E. `get_vi_error_list` returns error 1026 on all calls.**
This is a known server-side issue. The error does not indicate a real compile
failure. Use `get_vi_block_diagram` to visually inspect the VI instead.

### Type and wiring errors

**F. Error 1054 — object name not found.**
`smart_add_object_inside` requires exact LabVIEW palette names. Use the confirmed
palette list below as the canonical reference. Known variations:
- Comparison functions: `Greater?` not `Greater` (note trailing `?`)
- Random number: `Random Number (0-1)` (note `(0-1)` suffix)
- While Loop: `While Loop #1` not `While Loop`

**G. Error 1057 — type mismatch on Numeric Constant.**
Standalone `Numeric Constant` objects wired to typed terminals fail with error 1057.
The constant defaults to a generic type that doesn't coerce. **Always use
`smart_create_control(constant=True)` on the target terminal** instead of standalone
constants. The smart tools handle this automatically.

**H. Error 1075 — Feedback Node init terminal type undefined.**
When a Feedback Node's input terminal is wired to a comparison output (e.g. `Greater?`),
the init terminal (terminal_index=2) inherits a void/undefined type and creating the
init constant fails. Workaround: **Use `smart_feedback_node` which creates the init
constant BEFORE any wiring.** Wire the FN to a numeric source (`Add`, `Random Number`,
`Increment`) so it inherits a concrete numeric type first.

**I. Error 1055 — Case Structure nesting depth limit.**
`smart_add_object_inside` fails with error 1055 when adding objects to case_index >= 2
of a Case Structure that is itself nested inside a For Loop. Cases 0 and 1 work at this
depth. Workaround: limit to 2 cases when nesting Case Structures inside For Loops.

### Confirmed working behaviours

**J. `smart_create_control` is the primary terminal attachment tool.**
Works on any function terminal (input or output), inside or outside loops.
For inputs: `constant=False` creates a control, `constant=True` creates a typed constant.
For outputs: creates an indicator. Always prefer over standalone objects for type safety.

**K. Fan-out wiring works.**
A single output terminal can be wired to 5+ inputs without errors. Confirmed in:
- Program 2 (PID Controller): `sub_error[0]` fanned to `mul_p[0]`, `add_int[0]`,
  `sub_deriv[0]`, `fn_prev[0]` — 4 destinations
- Program 1 (EMA Monitor): `ema_add[0]` fanned to `ema_fn[0]`, `gt_high[0]`,
  `gt_low[1]` — 3 destinations
- Program 3 (Fibonacci): `fib_add[0]` fanned to `fn_b[0]`, `mul_alpha[0]`,
  `gt_thresh[0]`, `sub_dev[0]` — 4 destinations

**L. Cross-hierarchy wiring creates tunnels automatically.**
`smart_connect_objects` handles wiring from a parent diagram to an object inside a child
structure (e.g. For Loop sub-diagram → inside a Case Structure). Input data tunnels on the
inner structure are created automatically. No explicit tunnel management is needed.

**M. Multiple Feedback Nodes in one loop work.**
Confirmed: 3 FNs in Program 3 (Fibonacci: fn_a, fn_b, ema_fn), 2 FNs in Program 2
(PID: fn_int, fn_prev). Up to 5 FNs confirmed in prior testing. Each needs its own
init constant via `smart_create_control(constant=True)`.

**N. Feedback Nodes work across Case Structure tunnels.**
A FN placed outside a Case Structure (but inside the same For Loop) can be wired through
the Case Structure's input/output tunnels. The FN reads from the output tunnel and writes
back through the input tunnel with per-case logic in between.

**O. Multi-VI sessions work.**
Multiple `smart_new_vi` calls work in one module session; each returns an incrementing
`vi_id`. No need to stop/restart the module between VIs. `smart_save_and_finish` stops
the module; call `smart_new_vi` again for the next VI.

**P. Build Array inside For Loops — tunnel behaviour.**
`Build Array` works inside loops (confirmed) but the auto-indexing tunnel converts
scalar → array on output. Use `smart_create_control` on the `Build Array` output
terminal to create a scalar indicator showing the last iteration's value. If the full
accumulated array is needed, tunnel it out through the For Loop boundary via an output
tunnel. Note: repeated `Build Array` inside a loop causes O(n²) memory reallocation.

**Q. Nested structures work.**
Case Structure inside For Loop, For Loop inside Case Structure, and chained Case
Structures all work. Use `smart_case_structure` to get sub-diagram IDs for each case.
`smart_add_object_inside` with `parent_object_id` and `case_index` to place inside cases.

**R. Large programs compile clean.**
Programs with 17+ objects, 20+ wires, 5 FNs, and nested Case Structures compile with
zero errors. No practical complexity ceiling found within the confirmed object set.

**S. While Loop works via smart tools.**
`smart_while_loop` places `While Loop #1` (not `While Loop`), wires the stop condition
constant, and returns the sub-diagram ID. Use `parent_object_id` from the while loop to
place child objects inside via `smart_add_object_inside`.

**T. Event Structure works via low-level tools.**
`Event Structure` places and compiles clean via `add_object`. Has 3 terminals:
terminal 0 (Event Registration Refnum in), terminal 1 (Event Registration Refnum out),
terminal 2 (data terminal). Can be placed inside While Loops. Use `get_structure_diagram`
to get sub-diagram references for each event case. Event Structure is NOT supported by
the smart structure tools — use `add_object` + `get_structure_diagram` directly.

### Feedback Node wiring rules (CRITICAL)

Feedback Node terminals are **inverted** relative to normal data flow:
- **Terminal 0 (store/input):** receives the NEW value for next iteration
- **Terminal 1 (recall/output):** provides the PREVIOUS iteration's value
- **Terminal 2 (init):** initial value on first iteration

**Rule 1:** The `(1-α)` multiply in an EMA must receive `FN[1]` (recall/previous),
NEVER the raw source. Wrong: `rng→mul_b[0]`. Correct: `ema_fn[1]→mul_b[0]`.

**Rule 2:** FN output (terminal 1) must feed FORWARD in the diagram (to Add, Multiply,
etc.), never backward to a source generator (Random Number has no inputs).

**Rule 3:** Use `smart_feedback_node(init_value=...)` which creates the init constant
BEFORE any wiring. This prevents error 1075 by ensuring the FN inherits concrete
type before comparison wires are attached.

### Build Array / Concatenate Strings terminal limitation

Build Array and Concatenate Strings are created by the scripting server with
**only 1 input terminal**. They cannot be expanded to multiple terminals via MCP.
Use **separate nodes per input** — one Build Array per column, one Concatenate
Strings per segment.

### Terminal Index Convention

The smart tools use **logical terminal indices** (0-based), and automatically
resolve them to actual LabVIEW terminal IDs:

- **Outputs:** `[0]` = first output, `[1]` = second output (if exists)
- **Inputs:** `[0]` = first input, `[1]` = second input (if exists)
- **Feedback Node outputs:** `[1]` (recall), only one output → logical index `0`
  maps to actual terminal 1
- **Feedback Node inputs:** `[0]` (store), `[2]` (init) → logical index `0` maps
  to actual terminal 0, logical index `1` maps to actual terminal 2

**Fundamental operations** (stop and ask the user if these fail after one retry):
`smart_new_vi`, `smart_for_loop`, `smart_add_object_inside` for a confirmed working
object type, `smart_connect_objects`.

**Non-fundamental** (expected to sometimes fail; retry with variations):
`add_object` for unverified object types (try name variations),
`save_vi` (always fails — do not retry, ask user to save manually).

Do not retry a fundamental failure more than once without informing the user of the
blocker and the specific error code.

---

## Confirmed Working Objects (from `get_available_objects` verified list)

**Structures:** `For Loop`, `While Loop #1`, `Case Structure`, `Event Structure`
**Node:** `Feedback Node`
**Arithmetic:** `Add`, `Subtract`, `Multiply`, `Divide`, `Increment`, `Decrement`,
  `Negate`, `Absolute Value`, `Square Root`, `Reciprocal`, `Round To Nearest`,
  `Quotient & Remainder`, `Compound Arithmetic`
**Comparison:** `Greater?`, `Less?`, `Equal?`, `Not Equal?`, `In Range and Coerce`, `Select`
**Boolean:** `And`, `Or`, `Not`, `Xor`
**Timing:** `Wait (ms)`, `Tick Count (ms)`
**Numeric:** `Random Number (0-1)`
**Array:** `Build Array`, `Index Array`, `Array Size`
**String:** `Concatenate Strings`, `String Length`, `Format Into String`, `Scan From String`
**Cluster:** `Bundle`, `Unbundle`, `Bundle By Name`, `Unbundle By Name`
**Type Cast:** `Type Cast`, `Split Number`
**Controls/Indicators:** `Numeric Control (modern)`, `Numeric Indicator (modern)`
**Variables:** `Local Variable`, `Global Variable`

**Forbidden standalone objects** (use `smart_create_control(constant=True)` instead):
`Numeric Constant`, `String Constant`, `Boolean Constant`, `Array Constant`,
`Cluster Constant`, `Path Constant`, `Ring Constant`, `Color Box Constant`,
`Error Cluster Constant`, `Variant Constant`, `Refnum Constant`, `Timestamp Constant`

---

## Reusable Signal Processing Patterns

These are proven building blocks. Each should be expanded into a full LV-Plan before
building. Terminal indices are logical (0-based) as used by the smart tools.

**EMA filter** (exponential moving average):
```
Nodes: rng=Random Number(0-1), mul_alpha=Multiply, mul_prev=Multiply,
       ema_fn=Feedback Node(init=0), result=Add
Wires: rng[0]→mul_alpha[0], alpha_const→mul_alpha[1]
       ema_fn[0]→mul_prev[0], (1-alpha)_const→mul_prev[1]
       mul_alpha[0]→result[0], mul_prev[0]→result[1]
       result[0]→ema_fn[0]
Context: all inside For Loop
```

**PID controller** (2 FNs, error = SP - PV):
```
Nodes: sub=Subtract(SP,PV→error), fn_int=FN(integral,init=0),
       fn_prev=FN(prev_error,init=0), add_int=Add(integral+error),
       sub_deriv=Subtract(error-prev), mul_p=Multiply(Kp,error),
       mul_i=Multiply(Ki,integral), mul_d=Multiply(Kd,deriv),
       add_pi=Add, add_pid=Add
Wires: sub[0]→mul_p[0], sub[0]→add_int[0], sub[0]→sub_deriv[0], sub[0]→fn_prev[0]
       fn_int[0]→add_int[1], add_int[0]→fn_int[0], add_int[0]→mul_i[0]
       fn_prev[0]→sub_deriv[1], sub_deriv[0]→mul_d[0]
       mul_p[0]→add_pi[0], mul_i[0]→add_pi[1], add_pi[0]→add_pid[0], mul_d[0]→add_pid[1]
Context: all inside For Loop
```

**Phase accumulator** (monotonically increasing):
```
Nodes: fn=FN(init=0), add=Add
Wires: fn[0]→add[0], increment_const→add[1], add[0]→fn[0]
Context: inside For Loop
```

**Dual threshold alarm** (high/low):
```
Nodes: gt_high=Greater?(value,high), gt_low=Greater?(low,value)
Wires: value→gt_high[0], high_const→gt_high[1]
       low_const→gt_low[0], value→gt_low[1]
```

**Cross-wired Fibonacci**:
```
Nodes: fn_a=FN(init=0), fn_b=FN(init=1), add=Add
Wires: fn_a[0]→add[0], fn_b[0]→add[1]
       fn_b[0]→fn_a[0], add[0]→fn_b[0]
Context: inside For Loop
```

**Signal scaling** (arbitrary range):
```
Nodes: rng=Random Number(0-1), mul=Multiply, add=Add
Wires: rng[0]→mul[0], scale_const→mul[1], mul[0]→add[0], offset_const→add[1]
```

**While Loop with stop condition** (smart tools):
```
smart_while_loop(stop_condition="false") → returns loop_object_id, inner_diagram_id
Then use smart_add_object_inside(parent_object_id=loop_object_id, ...) for children.
Set stop_condition=false for infinite loop, true to stop immediately.
```

**While Loop + Event Structure** (low-level tools only):
```
Steps: smart_while_loop() → get loop_object_id
       add_object("Event Structure", diagram_id=inner_diagram_id) →
       get_structure_diagram(Event Structure) for event cases
Terminals: Event Structure has 3 terminals:
  0 = Event Registration Refnum (input)
  1 = Event Registration Refnum (output)
  2 = data terminal
```

---

## Example Programs (End-to-End Verified)

### Example 1: EMA Temperature Monitor with Dual Alarm

**LV-Plan:**
```
## LV-Plan: EMA Temperature Monitor

**Description:** Generates simulated temperatures (20-30°C), applies EMA filter (α=0.2), and checks dual thresholds (high > 28°C, low < 22°C).

**Nodes:**
| id         | palette_name              | type           | context              | notes                    |
|------------|---------------------------|----------------|----------------------|--------------------------|
| loop       | For Loop                  | for_loop       | root                 | iterations=50            |
| rng        | Random Number (0-1)       | function       | loop:loop            |                          |
| mul_scale  | Multiply                  | function       | loop:loop            | const@1=10               |
| add_offset | Add                       | function       | loop:loop            | const@1=20               |
| ema_fn     | Feedback Node             | feedback_node  | loop:loop            | init=25                  |
| mul_alpha  | Multiply                  | function       | loop:loop            | const@1=0.2              |
| mul_prev   | Multiply                  | function       | loop:loop            | const@1=0.8              |
| ema_add    | Add                       | function       | loop:loop            | indicator@0              |
| gt_high    | Greater?                  | function       | loop:loop            | const@1=28, indicator@0  |
| gt_low     | Greater?                  | function       | loop:loop            | const@0=22, indicator@0  |

**Wires:**
- rng[0] → mul_scale[0]
- mul_scale[0] → add_offset[0]
- add_offset[0] → mul_alpha[0]
- ema_fn[0] → mul_prev[0]
- mul_alpha[0] → ema_add[0]
- mul_prev[0] → ema_add[1]
- ema_add[0] → ema_fn[0]
- ema_add[0] → gt_high[0]
- ema_add[0] → gt_low[1]

**Constants:** mul_scale@1=10, add_offset@1=20, mul_alpha@1=0.2, mul_prev@1=0.8, gt_high@1=28, gt_low@0=22
**FN inits:** ema_fn=25
**Indicators:** ema_add@0, gt_high@0, gt_low@0
```

**Build steps used:** `smart_new_vi` → `smart_for_loop(50)` → `smart_add_object_inside` ×8 → `smart_feedback_node(init=25)` → `smart_create_control(constant=True)` ×6 → `smart_connect_objects` ×9 → `smart_create_control(is_input=False)` ×3 → `rename_object` ×3 → `smart_save_and_finish`

**Result:** All placements, wirings, and indicators created successfully. 10 nodes, 9 wires, 1 FN, clean compilation.

---

### Example 2: PID Controller Simulation

**LV-Plan:**
```
## LV-Plan: PID Controller Simulation

**Description:** Simulates a PID controller tracking setpoint=50 against a random PV scaled 0-100, with P=0.5, I=0.1, D=0.2.

**Nodes:**
| id         | palette_name              | type           | context              | notes                    |
|------------|---------------------------|----------------|----------------------|--------------------------|
| loop       | For Loop                  | for_loop       | root                 | iterations=100           |
| rng        | Random Number (0-1)       | function       | loop:loop            |                          |
| mul_pv     | Multiply                  | function       | loop:loop            | const@1=100              |
| sub_error  | Subtract                  | function       | loop:loop            | const@0=50, indicator@0  |
| fn_int     | Feedback Node             | feedback_node  | loop:loop            | init=0                   |
| fn_prev    | Feedback Node             | feedback_node  | loop:loop            | init=0                   |
| add_int    | Add                       | function       | loop:loop            |                          |
| sub_deriv  | Subtract                  | function       | loop:loop            |                          |
| mul_p      | Multiply                  | function       | loop:loop            | const@1=0.5              |
| mul_i      | Multiply                  | function       | loop:loop            | const@1=0.1              |
| mul_d      | Multiply                  | function       | loop:loop            | const@1=0.2              |
| add_pi     | Add                       | function       | loop:loop            |                          |
| add_pid    | Add                       | function       | loop:loop            | indicator@0              |

**Wires (15):**
- rng[0] → mul_pv[0]
- mul_pv[0] → sub_error[1]
- sub_error[0] → mul_p[0]
- sub_error[0] → add_int[0]
- sub_error[0] → sub_deriv[0]
- sub_error[0] → fn_prev[0]
- fn_int[0] → add_int[1]
- add_int[0] → fn_int[0]
- add_int[0] → mul_i[0]
- fn_prev[0] → sub_deriv[1]
- sub_deriv[0] → mul_d[0]
- mul_p[0] → add_pi[0]
- mul_i[0] → add_pi[1]
- add_pi[0] → add_pid[0]
- mul_d[0] → add_pid[1]

**Constants:** mul_pv@1=100, sub_error@0=50, mul_p@1=0.5, mul_i@1=0.1, mul_d@1=0.2
**FN inits:** fn_int=0, fn_prev=0
**Indicators:** sub_error@0 (Error), add_pid@0 (PID Output)
```

**Build steps used:** `smart_new_vi` → `smart_for_loop(100)` → `smart_add_object_inside` ×10 → `smart_feedback_node` ×2 → `smart_create_control(constant=True)` ×5 → `smart_connect_objects` ×15 → `smart_create_control(is_input=False)` ×2 → `rename_object` ×2 → `smart_save_and_finish`

**Result:** All placements, wirings, and indicators created successfully. 12 nodes, 15 wires, 2 FNs, fan-out of sub_error[0] to 4 destinations. Clean compilation.

---

### Example 3: Fibonacci Generator with EMA and Deviation Alert

**LV-Plan:**
```
## LV-Plan: Fibonacci Generator with EMA and Deviation Alert

**Description:** Generates Fibonacci numbers via cross-wired Feedback Nodes, applies EMA smoothing (α=0.3), computes deviation from EMA, and checks threshold > 100.

**Nodes:**
| id         | palette_name              | type           | context              | notes                    |
|------------|---------------------------|----------------|----------------------|--------------------------|
| loop       | For Loop                  | for_loop       | root                 | iterations=20            |
| fn_a       | Feedback Node             | feedback_node  | loop:loop            | init=0                   |
| fn_b       | Feedback Node             | feedback_node  | loop:loop            | init=1                   |
| fib_add    | Add                       | function       | loop:loop            | indicator@0              |
| ema_fn     | Feedback Node             | feedback_node  | loop:loop            | init=0                   |
| mul_alpha  | Multiply                  | function       | loop:loop            | const@1=0.3              |
| mul_prev   | Multiply                  | function       | loop:loop            | const@1=0.7              |
| ema_add    | Add                       | function       | loop:loop            | indicator@0              |
| gt_thresh  | Greater?                  | function       | loop:loop            | const@1=100, indicator@0 |
| sub_dev    | Subtract                  | function       | loop:loop            | indicator@0              |

**Wires (12):**
- fn_a[0] → fib_add[0]
- fn_b[0] → fib_add[1]
- fn_b[0] → fn_a[0]       (cross-wire: fn_b prev → fn_a input)
- fib_add[0] → fn_b[0]
- fib_add[0] → mul_alpha[0]
- ema_fn[0] → mul_prev[0]
- mul_alpha[0] → ema_add[0]
- mul_prev[0] → ema_add[1]
- ema_add[0] → ema_fn[0]
- fib_add[0] → gt_thresh[0]
- fib_add[0] → sub_dev[0]
- ema_add[0] → sub_dev[1]

**Constants:** mul_alpha@1=0.3, mul_prev@1=0.7, gt_thresh@1=100
**FN inits:** fn_a=0, fn_b=1, ema_fn=0
**Indicators:** fib_add@0, ema_add@0, gt_thresh@0, sub_dev@0
```

**Build steps used:** `smart_new_vi` → `smart_for_loop(20)` → `smart_add_object_inside` ×6 → `smart_feedback_node` ×3 → `smart_create_control(constant=True)` ×3 → `smart_connect_objects` ×12 → `smart_create_control(is_input=False)` ×4 → `rename_object` ×4 → `smart_save_and_finish`

**Result:** All placements, wirings, and indicators created successfully. 9 nodes, 12 wires, 3 FNs, cross-wired Fibonacci pattern with EMA filter overlay. Clean compilation.

---

## Lint / Typecheck

No automated lint or typecheck commands are configured for this project.
