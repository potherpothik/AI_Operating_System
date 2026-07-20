# Phase 17 — Engineering & Calculation Agents
### Calculation Agent · Cutlist Optimization Agent · AutoCAD Agent

---

## Prerequisites (read before implementation)

| Doc | Why |
|---|---|
| [`docs/README.md`](README.md) | Doc index and before-you-code checklist |
| [`phase-6-shell-git-manager.md`](phase-6-shell-git-manager.md) | Shell Executor sandbox — the execution mechanism every real calculation/solve routes through |
| [`phase-9-documentation-erp-knowledge-engine.md`](phase-9-documentation-erp-knowledge-engine.md) | Formula registration (Costing Agent, Phase 14) — Calculation Agent reads real registered formulas, not invented ones |
| [`phase-15-operations-agents.md`](phase-15-operations-agents.md) | Manufacturing Agent — Cutlist Optimization Agent is its already-named future delegate target |

---

## 0. Priority Decision: Why This Phase Now

**Why it exists here:** the master roadmap's own framing for this batch — none of these three agents let the model assert a numeric or layout result from its own generation. Language models are a known weak point for arithmetic and combinatorial optimization; the roadmap's explicit fix is that every calculation routes through an actual deterministic function or solver, executed via Shell Executor's sandbox (Phase 6), with the agent explaining a real result rather than computing one in free text. This is the first batch whose entire reason for existing is a shared integrity constraint on the model itself, not a new domain to reason about.

**Why these three together:** all three need the exact same underlying mechanism — real, reviewed, deterministic Python scripts, invoked through Shell Executor's existing sandboxed subprocess execution (Phase 6), never through the model's own arithmetic. Building the mechanism once and reusing it three times is more honest than three bespoke integrity stories.

**Alternatives considered**
- *Let the agent's `answer_or_proposal` field state a computed number directly, same as every other agent's free-text answer* — rejected outright, this is exactly what the roadmap names as the failure mode to avoid. A model computing `847.32 * 1.15` in its own generation is not verifiably correct even when it happens to be right.
- *Use Python's built-in `eval()` on a model-supplied expression string* — rejected. `eval()` executes arbitrary code, not just arithmetic; a model-controlled string reaching `eval()` is a real code-execution vector, the same class of risk this project's SQL-parameterization discipline (Phase 7) and command-allowlisting discipline (Phase 6) already refuse to accept elsewhere. Real fix: a restricted AST-walking evaluator that only recognizes numeric literals, named variables, and arithmetic operators — structurally incapable of calling a function, importing a module, or executing anything beyond arithmetic, regardless of what string reaches it.
- *Use an external optimization library (e.g. OR-tools) for the cutlist solver* — rejected for v1. A hand-written, real, deterministic first-fit-decreasing (FFD) bin-packing heuristic needs no new dependency, is honestly documented as a heuristic (not globally optimal), and is still a genuine algorithm producing a genuine result — not a model guess. Swapping in a real ILP solver later is a contained change to one script, not a redesign.
- *Skip AutoCAD Agent or fake DWG support* — rejected. The master doc names the Linux/DWG constraint explicitly as a real, honest limitation rather than something to assume away. This phase implements real DXF (an open, documented format) parsing via `ezdxf` — genuinely real for DXF input, honestly `not_configured`/out-of-scope for native `.dwg`, which has no open-source parser and no Linux-native Autodesk tooling.

**Trade-offs:** three new small, reviewed, non-agent-editable Python scripts land in the codebase (`services/execution/execution/shell_executor/scripts/`) — a new kind of artifact this system hasn't had before (static deterministic tools rather than governed agent actions). Mitigated by keeping every script's logic small, pure-stdlib-plus-one-dependency, and fully unit tested independent of any live model.

**Security implications:** the restricted-AST formula evaluator is this phase's actual security surface — a model-controlled expression string reaching real code execution would be a genuine vulnerability if the evaluator accepted anything beyond arithmetic. Structurally scoped (Section 1) rather than defended by convention.

**Performance implications:** each real calculation is one sandboxed subprocess call (same cost class as any other Shell Executor invocation already in this system) — negligible for the arithmetic/solver sizes this phase targets.

**Future scalability:** the sandboxed-script pattern (a real script under `shell_executor/scripts/`, invoked via an allowlisted `python3 <script> <args>` pattern, never the model's own arithmetic) generalizes to any future agent needing a verified, non-asserted numeric or structural result.

**Estimated complexity:** Medium-high. Three real deterministic scripts plus one new bridge each, but no new service and no new governance primitive — pure extension of Phase 6's existing sandbox.

---

## 1. The Shared Mechanism: Real Sandboxed Deterministic Execution

**Why a new kind of artifact, not just another tool call:** every prior tool call (`db.read`, `git.diff`, `review.check_callers`, …) asks an EXISTING service to do something it already does. This phase is different — there is no existing service that evaluates a formula or runs a cutting-stock solver. The real computation has to live somewhere, and it must be a REAL, reviewed, non-agent-editable artifact — never code the model generates and asks to have run, which would just relocate the "don't trust model arithmetic" problem instead of solving it.

**The scripts** (`services/execution/execution/shell_executor/scripts/`):
- `eval_formula.py` — `argv: <expression> <inputs_json>`. Evaluates a numeric expression using a restricted `ast`-based walker: only `Constant`/`Num`, `Name` (resolved against `inputs_json`'s keys), `BinOp` (`+ - * / % **`), and `UnaryOp` (`+ -`) node types are permitted — no calls, no attribute access, no imports, no comprehensions, structurally incapable of anything beyond arithmetic regardless of the input string. Prints `{"result": <number>}` or a clean `{"error": "..."}` with a non-zero exit code.
- `cutlist_solver.py` — `argv: <stock_length> <cut_lengths_json> [kerf]`. A real first-fit-decreasing (FFD) 1D cutting-stock heuristic: sorts required cut lengths descending, packs each into the first bin (stock length) with enough remaining room (accounting for blade kerf between cuts), opening a new bin only when none fits. Prints `{"bins": [[...]], "bins_used": N, "waste_total": X, "algorithm": "first_fit_decreasing"}` — the `algorithm` field is there so nothing downstream can mistake a heuristic for a proven-optimal result.
- `dxf_parse.py` — `argv: <dxf_file_path>`. Uses `ezdxf` (a real, PyPI-installed DXF-parsing library) to open a real DXF file and extract layers, entity type counts, the real drawing extents (bounding box), and any `TEXT`/`MTEXT`/`DIMENSION` entity content — genuine structured data pulled from the actual file, not an LLM's guess about what a drawing "probably" contains.

**Invocation:** each new bridge (Section 2) calls `clients.shell_execute(command="python3", args=[script_path, ...])` — the exact same Shell Executor path `shell_bridge.py` (Phase 10) already established, with a new, narrowly-scoped allowlist entry per agent (`python3 <scripts_dir>/eval_formula.py *`, etc.). `working_dir` is a real directory under `SANDBOX_ROOT`, same confinement every other sandboxed command already gets; the script path itself is a fixed, reviewed file, never model-supplied.

**Configuration:** `CALC_SCRIPTS_DIR` — a real absolute path to `shell_executor/scripts/` (the same "real local path, single-host dev convention" `PROPOSAL_REPO_PATH`/`DEMO_ERP_DATABASE_URL` already use, Phase 6/7). No default — a bridge with it unset reports the tool call as `not_configured`, honestly, rather than guessing a path.

**Failure handling:** a malformed expression, an unresolvable variable name, or a disallowed AST node type in `eval_formula.py` is a clean, structured error — never a partial or guessed number. `cutlist_solver.py` refuses a cut length longer than the stock length outright (clean error, not an infinite bin). `dxf_parse.py` reports a clean parse failure for a corrupted or non-DXF file, matching Documentation Engine's own "unparseable documents fail explicitly" posture (Phase 9).

---

## 2. Calculation Agent

```yaml
capability: calculation_agent
brain: erp
allowed_actions:
  - calc.apply_formula
  - calc.explain_formula
forbidden_actions:
  - calc.assert_unverified_number
requires_approval: []
classification_ceiling: internal
integrity_requirement: numeric results must come from executed code (eval_formula.py, via Shell Executor's sandbox), never asserted directly by the model — enforced structurally by calc_bridge.py's tool-call shape, not just prompt wording
```

**Distinctive scope:** `calc.apply_formula` is a real, non-terminal tool call — the model names a `formula_ref` (fetched fresh from ERP Knowledge Engine's real `GET /erp-knowledge/formula/{id}` registration, Phase 9/14, never invented) and real `inputs_json` values; `calc_bridge.py` runs `eval_formula.py` via Shell Executor and feeds the REAL computed number back for the model's next turn. `calc.explain_formula` reasons over retrieved context (the formula's registered business-meaning prose) without needing a fresh computation. Read/calculate actions never require human approval — results are deterministic and verifiable, not a judgment call; only a formula CHANGE (Costing Agent's existing `costing.propose_formula_change` path, Phase 14) requires approval, and Calculation Agent has no write action of its own at all.

**Refuses:** asserting a number it didn't get from `eval_formula.py`'s real output — a structural, not just prompted, refusal: there is no code path in this system that lets a `calc.apply_formula` response reach `completed` status without a tool-call round trip having actually happened first.

**Found live, not by inspection:** an early version of this agent's own template showed a plain-language JSON example (`` `{"base_cost": 420}` ``) in prose — Prompt Builder's `render()` (Phase 4) calls Python's `str.format()` directly on the raw template body, which tried to resolve `"base_cost"` as a format field name and raised a real `500` on every single render for this agent, not just the one demonstrating a formula. Fixed by escaping the literal braces (`{{`/`}}`); every other Phase 1–17 template was checked and had no literal braces to begin with. Worth remembering for any future template wanting to show a JSON example in its own prose.

---

## 3. Cutlist Optimization Agent

```yaml
capability: cutlist_optimization_agent
brain: erp
allowed_actions:
  - cutlist.gather_parameters
  - cutlist.run_optimizer
  - cutlist.explain_result
forbidden_actions:
  - cutlist.generate_layout_direct
requires_approval:
  - cutlist.run_optimizer  # only when the result explicitly feeds a downstream production-schedule change — see failure handling below
classification_ceiling: internal
integrity_requirement: layout results come from cutlist_solver.py's real first-fit-decreasing algorithm, never asserted by the model
```

**Distinctive scope:** `cutlist.gather_parameters` is conversational — the agent's real job (per the master doc) is gathering real input parameters (stock length, required cut lengths, kerf) through the conversation before ever proposing a solve, not generating a cutlist as free text. `cutlist.run_optimizer` is the real, non-terminal tool call — real parameters trigger `cutlist_solver.py` via Shell Executor, and the real bin/waste result feeds back for the model's next turn. `cutlist.explain_result` reports that real result in plain language, always citing `bins_used`/`waste_total` from the actual solver output.

**Approval nuance, honestly scoped:** the master doc's own conditional ("only if the resulting cutlist feeds a downstream production-schedule change") isn't a distinction this system can structurally detect from a `cutlist.run_optimizer` call alone — there's no existing signal for "this result is about to become a schedule change" versus "this is exploratory." This phase keeps `cutlist.run_optimizer` itself `require_approval` unconditionally (the conservative reading), and reasoning about whether a given result actually changes a schedule is Manufacturing Agent's job (Phase 15) when it consumes a cutlist result, not something this agent decides about itself. Documented as a deliberate scope simplification, not silently narrowed.

**Refuses:** generating a layout directly (`cutlist.generate_layout_direct`) — every layout comes from the real solver, never asserted. **Delegates:** production-schedule implications to Manufacturing Agent (Phase 15), which already names Cutlist Optimization Agent as its own future delegate target for the reverse direction.

---

## 4. AutoCAD Agent

```yaml
capability: autocad_agent
brain: coding
allowed_actions:
  - autocad.explain_drawing
  - autocad.propose_annotation
forbidden_actions:
  - autocad.modify_drawing_direct
requires_approval:
  - autocad.propose_annotation
classification_ceiling: internal
known_constraint: AutoCAD's native .dwg format and tooling aren't Linux-native or open-source; this phase implements real DXF (an open, documented format) parsing via ezdxf and assumes a DWG→DXF conversion step happened upstream — native .dwg support remains a named, honest gap, not something worked around or assumed away
```

**Distinctive scope:** `autocad.explain_drawing` is a real, non-terminal tool call — the model names a real `dxf_path`, `dxf_parse.py` runs via Shell Executor against the actual file, and the REAL parsed structure (layers, entity counts, extents, text/dimension content) feeds back for the model's next turn; the agent explains from that converted, parsed representation, never from guessing what a drawing "probably" shows. `autocad.propose_annotation` reuses `execution_bridge.materialize_propose_change()` completely unchanged — a proposed annotation is a plain-language document for a human to review, same shape as every other `propose_*` action in this system.

**Refuses:** modifying a drawing directly — this agent only ever reads (via real parsing) and proposes (via the existing git-review path), never writes to a CAD file.

---

## 5. How the Shared Mechanism Fits In

```
Calculation Agent → calc.apply_formula(formula_ref="rush_order_surcharge", inputs={"base_cost": 420})
        │
        ▼
GET /erp-knowledge/formula/{id} (Phase 9/14, existing) → real formula_ref text
        │
        ▼
Shell Executor: python3 eval_formula.py "base_cost * 1.05" '{"base_cost": 420}'
        │
        ▼
restricted AST evaluator → real number: 441.0 → fed back into context
        │
        ▼
calc.apply_formula (final turn) → answer grounded in the real 441.0, never asserted


Cutlist Optimization Agent → cutlist.run_optimizer(stock_length=96, cuts=[42,42,30,24,18])
        │
        ▼
Shell Executor: python3 cutlist_solver.py 96 "[42,42,30,24,18]" 0.125
        │
        ▼
real FFD heuristic → real {"bins_used": 2, "waste_total": 6.75, ...} → fed back
        │
        ▼
requires human approval before cutlist.run_optimizer's result is treated as final


AutoCAD Agent → autocad.explain_drawing(dxf_path="/real/file.dxf")
        │
        ▼
Shell Executor: python3 dxf_parse.py /real/file.dxf
        │
        ▼
real ezdxf-parsed structure (layers, entities, extents, text) → fed back
        │
        ▼
autocad.explain_drawing (final turn) → explanation grounded in the real parse
```

---

## 6. Minimal Data Model

No new tables this phase — every real computation is stateless (a sandboxed subprocess call and its stdout), and every durable record (formula registrations, proposal documents, approvals) already lives in existing tables from Phase 1/6/9/14.

---

## 7. Folder Structure

```
services/agents/agents/
├── calculation_agent/
│   ├── capability.yaml
│   └── template.md
├── cutlist_optimization_agent/
│   ├── capability.yaml
│   └── template.md
└── autocad_agent/
    ├── capability.yaml
    └── template.md

services/agents/agents/reasoning_engine/
├── calc_bridge.py         # new — calc.apply_formula tool call
├── cutlist_bridge.py      # new — cutlist.run_optimizer tool call
└── autocad_bridge.py      # new — autocad.explain_drawing tool call

services/execution/execution/shell_executor/scripts/
├── eval_formula.py        # new — restricted AST arithmetic evaluator
├── cutlist_solver.py      # new — real first-fit-decreasing bin-packing heuristic
└── dxf_parse.py           # new — real ezdxf-based DXF structure extraction

services/execution/execution/shell_executor/allowlists/
├── calculation_agent.yaml
├── cutlist_optimization_agent.yaml
└── autocad_agent.yaml
```

---

## 8. Explicitly Out of Scope

Native `.dwg` parsing (proprietary format, no open-source parser, no Linux-native Autodesk tooling — a real, honestly-named constraint, not a gap to work around). A globally-optimal cutting-stock solver (ILP/OR-tools) — FFD is a real, deterministic heuristic, honestly labeled as such; swapping in an exact solver later is a contained change to one script. Formula authoring — Calculation Agent only ever evaluates formulas Costing Agent has already registered (Phase 14); it has no write path of its own. 2D/3D CAD rendering or visualization — this phase extracts structured data, it doesn't render drawings.

---

## Next

Phase 18: Cross-Cutting Agents (Python Agent, Documentation Agent, Security Agent, Research Agent) — Documentation Agent explicitly names Reverse Engineering Agent (Phase 16) as its delegate target when nothing is written down at all, and Security Agent is a natural next consumer of Phase 16's approval-review attachment mechanism.
