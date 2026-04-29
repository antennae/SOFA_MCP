"""Parent-side orchestrator for `diagnose_scene`.

Two-subprocess architecture (Step 2):
  1. `summarize_scene(content)` — 30s budget; produces structural anomalies
     (the `checks` list from the existing 9 Health Rules) without running init.
  2. `_diagnose_runner.py <scene_path> <steps> <dt> <output_json>` — 90s budget;
     loads the scene, runs SOFA init + animate, writes per-step metrics to a
     tempfile passed on argv.

The two subprocess outputs are merged here. `anomalies` always come from the
summarize pass — keeping rule logic single-sourced in
`_summary_runtime_template.py`.

Encoding: every `subprocess.run` here passes `encoding="utf-8", errors="replace"`.
The locale-default fallback is ASCII in the FastMCP server process, and SOFA's
runtime emits em-dashes in [INFO] lines. Step 3's regex consumers should be
tolerant of `�` characters or strip them before matching non-ASCII patterns.

Tempfile lifecycle: parent creates the path with NamedTemporaryFile(delete=False)
and removes it in `finally`. JSONDecodeError, missing-file, and empty-file all
collapse to the same failure shape — runner crashed before producing payload.
"""

import json
import os
import pathlib
import re
import subprocess
import tempfile
from typing import Any, Dict, List


PYTHON = os.path.expanduser("~/venv/bin/python")
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_diagnose_runner.py")

SUMMARIZE_TIMEOUT_S = 30
RUNNER_TIMEOUT_S = 90

# §6.A.3 displacement-vs-extent thresholds. 10× extent counts as suspicious;
# 100× counts as unphysical. Empirically calibrated against archiv/ scenes
# where the worst clean run was <0.5× extent.
_EXCESSIVE_DISP_WARN_RATIO = 10.0
_EXCESSIVE_DISP_ERROR_RATIO = 100.0

# §Log truncation. 5KB head + 25KB tail. Smell tests must run on the full
# pre-truncation log; truncation happens last in the orchestrator.
_LOG_HEAD_CHARS = 5 * 1024
_LOG_TAIL_CHARS = 25 * 1024
_QP_INFEASIBLE_RE = re.compile(r"QP infeasible")


def _empty_metrics() -> Dict[str, Any]:
    return {
        "nan_first_step": None,
        "max_displacement_per_mo": {},
        "max_force_per_mo": {},
    }


def _empty_scene_summary() -> Dict[str, Any]:
    return {"node_count": 0, "class_counts": {}, "actuators_only": False}


def _empty_step3_fields() -> Dict[str, Any]:
    """Forward-looking payload keys (Step 3) that all early-failure paths
    must include so callers can rely on a uniform response shape."""
    return {
        "extents_per_mo": {},
        "solver_iterations": {},
        "solver_max_iterations": {},
        "objective_series": {},
        "printLog_activated": [],
        "plugin_cache_empty": False,
    }


def _check_excessive_displacement(
    metrics: Dict[str, Any], extents_per_mo: Dict[str, float]
) -> List[Dict[str, Any]]:
    """§6.A.3 — large displacement-to-extent ratio. Two-tier severity.

    Returns one anomaly per offending MO. MOs without an extent (degenerate
    or single-point) are skipped — the displacement still appears in the
    response so the agent can reason about it. The two-tier check replaces
    nan_first_step as the primary numerical-blowup detector since implicit
    ODE solvers rarely produce NaN.
    """
    anomalies: List[Dict[str, Any]] = []
    disps = metrics.get("max_displacement_per_mo") or {}
    for path, disp in disps.items():
        try:
            disp = float(disp)
        except (TypeError, ValueError):
            continue
        extent = extents_per_mo.get(path)
        if extent is None or extent <= 0:
            continue
        ratio = disp / extent
        if ratio >= _EXCESSIVE_DISP_ERROR_RATIO:
            severity = "error"
        elif ratio >= _EXCESSIVE_DISP_WARN_RATIO:
            severity = "warning"
        else:
            continue
        anomalies.append({
            "rule": "excessive_displacement",
            "severity": severity,
            "subject": path,
            "message": (
                f"Max displacement {disp:.4g} is {ratio:.1f}x the mesh extent "
                f"{extent:.4g} on {path} — likely numerical blowup or scene "
                f"misconfiguration."
            ),
            "ratio": ratio,
            "extent": extent,
            "max_displacement": disp,
        })
    return anomalies


def _check_solver_iter_cap_hit(
    solver_iterations: Dict[str, List[int]],
    solver_max_iterations: Dict[str, int],
) -> List[Dict[str, Any]]:
    """§6.A.6 (NNCG/BGS path) — `currentIterations >= maxIterations` on any
    step means the constraint solver hit its iteration cap and likely did
    not converge. Exact equality counts as a hit; the rare false-positive
    of converging exactly on the last allowed iteration is accepted.

    CG/LCP regex path is deferred — no verified log pattern in this build.
    """
    anomalies: List[Dict[str, Any]] = []
    for path, iters in solver_iterations.items():
        cap = solver_max_iterations.get(path)
        if cap is None or cap <= 0 or not iters:
            continue
        steps_hit = [i for i, c in enumerate(iters) if c >= cap]
        if not steps_hit:
            continue
        anomalies.append({
            "rule": "solver_iter_cap_hit",
            "severity": "warning",
            "subject": path,
            "message": (
                f"Constraint solver {path} hit its iteration cap "
                f"({cap}) on {len(steps_hit)}/{len(iters)} step(s) — "
                f"likely failed to converge."
            ),
            "max_iterations": cap,
            "steps_hit_cap": steps_hit,
        })
    return anomalies


def _check_inverse_objective_not_decreasing(
    objective_series: Dict[str, List[float]], window: int = 5
) -> List[Dict[str, Any]]:
    """§6.A.13 — for each QP solver's objective series, the last `window`
    transitions must be non-increasing (within tolerance) AND the final
    value must exceed 1e-6.

    Tolerance is relative (1e-6 * |obj[i]|) with an absolute floor of
    1e-9 — eats numerical noise without making the rule unit-system
    sensitive. The at-optimum guard avoids firing on a series flat at
    1e-7 or below where the small relative tolerance would otherwise
    let any noise count as 'not decreasing'.
    """
    anomalies: List[Dict[str, Any]] = []
    for path, series in objective_series.items():
        if not series or len(series) < window:
            continue
        tail = series[-window:]
        # Last value must exceed the at-optimum threshold.
        if tail[-1] <= 1e-6:
            continue
        non_decreasing = True
        for i in range(len(tail) - 1):
            tol_abs = max(1e-9, 1e-6 * abs(tail[i]))
            if tail[i + 1] < tail[i] - tol_abs:
                non_decreasing = False
                break
        if not non_decreasing:
            continue
        anomalies.append({
            "rule": "inverse_objective_not_decreasing",
            "severity": "warning",
            "subject": path,
            "message": (
                f"QP objective at {path} did not decrease over the last "
                f"{window} steps (final={tail[-1]:.4g}); inverse solver "
                f"may be stuck or not converging."
            ),
            "objective_tail": list(tail),
        })
    return anomalies


def _check_qp_infeasible_in_log(solver_logs: str) -> List[Dict[str, Any]]:
    """§6.B.2 — `QP infeasible` in the captured log. SOFA emits this via
    msg_warning/msg_error from QPInverseProblemImpl when qpOASES rejects
    the QP as infeasible (e.g., conflicting hard bounds). Per-step bucketing
    is deferred; we ship a count, which gives the agent the same diagnostic
    value without the fragile step-boundary parsing.
    """
    if not solver_logs:
        return []
    matches = _QP_INFEASIBLE_RE.findall(solver_logs)
    if not matches:
        return []
    return [{
        "rule": "qp_infeasible_in_log",
        "severity": "error",
        "subject": "QPInverseProblemSolver",
        "message": (
            f"'QP infeasible' was logged {len(matches)} time(s) — "
            f"the QP solver rejected the problem; check actuator bounds, "
            f"hard equalities, and contact constraints."
        ),
        "match_count": len(matches),
    }]


def _truncate_log(
    text: str,
    head_chars: int = _LOG_HEAD_CHARS,
    tail_chars: int = _LOG_TAIL_CHARS,
) -> str:
    """Cap a log string at head_chars + tail_chars + separator. Counts the
    number of newlines in the elided segment for an accurate hint to the
    reader. Returns the input unchanged when shorter than the budget.
    """
    if not text or len(text) <= head_chars + tail_chars:
        return text
    head = text[:head_chars]
    tail = text[-tail_chars:]
    elided = text[head_chars:-tail_chars]
    elided_lines = elided.count("\n")
    sep = f"\n... <{elided_lines} lines elided> ...\n"
    return head + sep + tail


def _summarize_anomalies(content: str) -> Dict[str, Any]:
    """Return {anomalies, summarize_error?}. Defensive against summarize_scene
    failure modes (timeout, runtime error) — the no-checks shape uses .get().
    """
    from sofa_mcp.architect import scene_writer

    summary = scene_writer.summarize_scene(content, timeout_s=SUMMARIZE_TIMEOUT_S)
    anomalies = summary.get("checks") or []
    out: Dict[str, Any] = {"anomalies": anomalies}
    if not summary.get("success"):
        out["summarize_error"] = summary.get("error") or summary.get("message")
    return out


def diagnose_scene(
    scene_path: str,
    complaint: str = None,
    steps: int = 50,
    dt: float = 0.01,
) -> Dict[str, Any]:
    """Run the diagnose-scene sanity report on a scene file.

    Args:
        scene_path: Path to a Python scene file defining createScene(rootNode).
        complaint: Free-form agent hint; accepted but unused in Step 2 (Step 5
            playbook will use it to bias which probe runs next).
        steps: Number of animation steps to run.
        dt: Time step.

    Returns:
        Sanity report dict — see the Step 2 contract in docs/plan.md.
    """
    del complaint  # accepted for forward-compat; unused in Step 2.

    path = pathlib.Path(scene_path).expanduser()
    if not path.exists() or not path.is_file():
        return {
            "success": False,
            "error": f"Scene file not found: {scene_path}",
            "message": "diagnose_scene requires a path to an existing scene file.",
            "anomalies": [],
            "metrics": _empty_metrics(),
            "init_stdout_findings": [],
            "solver_logs": "",
            "scene_summary": _empty_scene_summary(),
            **_empty_step3_fields(),
        }

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "success": False,
            "error": f"Could not read scene file: {exc}",
            "message": "diagnose_scene failed to read the scene file.",
            "anomalies": [],
            "metrics": _empty_metrics(),
            "init_stdout_findings": [],
            "solver_logs": "",
            "scene_summary": _empty_scene_summary(),
            **_empty_step3_fields(),
        }

    summary_part = _summarize_anomalies(content)
    anomalies = summary_part["anomalies"]

    # Tempfile created with delete=False so the runner subprocess can write to it
    # while we hold no handle. We remove it in `finally` regardless of outcome.
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as tmp:
        output_json_path = tmp.name

    try:
        try:
            result = subprocess.run(
                [PYTHON, RUNNER, str(path), str(int(steps)), str(float(dt)), output_json_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=RUNNER_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            captured = ""
            if exc.stdout:
                captured += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", errors="replace")
            if exc.stderr:
                captured += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", errors="replace")
            return {
                "success": False,
                "error": "Timeout",
                "message": f"diagnose_scene runner exceeded {RUNNER_TIMEOUT_S}s.",
                "anomalies": anomalies,
                "metrics": _empty_metrics(),
                "init_stdout_findings": [],
                "solver_logs": _truncate_log(captured),
                "scene_summary": _empty_scene_summary(),
                **_empty_step3_fields(),
            }

        solver_logs = (result.stdout or "") + (result.stderr or "")

        # Read payload. JSONDecodeError, missing file, empty file all collapse to
        # one failure shape — runner crashed before producing payload.
        payload = None
        read_err = None
        try:
            with open(output_json_path, "r", encoding="utf-8") as f:
                raw = f.read()
            if raw.strip():
                payload = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            read_err = str(exc)

        if payload is None:
            return {
                "success": False,
                "error": f"runner produced no payload (returncode={result.returncode}{f'; read_err={read_err}' if read_err else ''})",
                "message": "diagnose_scene runner did not write a JSON payload.",
                "anomalies": anomalies + _check_qp_infeasible_in_log(solver_logs),
                "metrics": _empty_metrics(),
                "init_stdout_findings": [],
                "solver_logs": _truncate_log(solver_logs),
                "scene_summary": _empty_scene_summary(),
                **_empty_step3_fields(),
            }

        # Step 3 smell tests — runner-supplied state plus the full
        # pre-truncation log. Run regardless of payload.success so that
        # structural anomalies surface even when init or animate failed.
        runner_metrics = payload.get("metrics") or _empty_metrics()
        smell_anomalies: List[Dict[str, Any]] = []
        smell_anomalies.extend(payload.get("structural_anomalies") or [])
        smell_anomalies.extend(_check_excessive_displacement(
            runner_metrics, payload.get("extents_per_mo") or {}
        ))
        smell_anomalies.extend(_check_solver_iter_cap_hit(
            payload.get("solver_iterations") or {},
            payload.get("solver_max_iterations") or {},
        ))
        smell_anomalies.extend(_check_inverse_objective_not_decreasing(
            payload.get("objective_series") or {}
        ))
        smell_anomalies.extend(_check_qp_infeasible_in_log(solver_logs))

        truncated_logs = _truncate_log(solver_logs)

        if not payload.get("success"):
            return {
                "success": False,
                "error": payload.get("error") or "runner reported failure",
                "message": "diagnose_scene runner reported a failure during init or animate.",
                "traceback": payload.get("traceback"),
                "anomalies": anomalies + smell_anomalies,
                "metrics": runner_metrics,
                "init_stdout_findings": payload.get("init_stdout_findings") or [],
                "solver_logs": truncated_logs,
                "scene_summary": payload.get("scene_summary") or _empty_scene_summary(),
                "extents_per_mo": payload.get("extents_per_mo") or {},
                "solver_iterations": payload.get("solver_iterations") or {},
                "solver_max_iterations": payload.get("solver_max_iterations") or {},
                "objective_series": payload.get("objective_series") or {},
                "printLog_activated": payload.get("printLog_activated") or [],
                "plugin_cache_empty": payload.get("plugin_cache_empty", False),
            }

        merged = {
            "success": True,
            "metrics": runner_metrics,
            "anomalies": anomalies + smell_anomalies,
            "init_stdout_findings": payload.get("init_stdout_findings") or [],
            "solver_logs": truncated_logs,
            "scene_summary": payload.get("scene_summary") or _empty_scene_summary(),
            "extents_per_mo": payload.get("extents_per_mo") or {},
            "solver_iterations": payload.get("solver_iterations") or {},
            "solver_max_iterations": payload.get("solver_max_iterations") or {},
            "objective_series": payload.get("objective_series") or {},
            "printLog_activated": payload.get("printLog_activated") or [],
            "plugin_cache_empty": payload.get("plugin_cache_empty", False),
        }
        if "summarize_error" in summary_part:
            merged["summarize_error"] = summary_part["summarize_error"]
        return merged

    finally:
        try:
            os.remove(output_json_path)
        except OSError:
            pass
