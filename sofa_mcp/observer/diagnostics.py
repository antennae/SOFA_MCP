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
import subprocess
import tempfile
from typing import Any, Dict


PYTHON = os.path.expanduser("~/venv/bin/python")
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_diagnose_runner.py")

SUMMARIZE_TIMEOUT_S = 30
RUNNER_TIMEOUT_S = 90


def _empty_metrics() -> Dict[str, Any]:
    return {
        "nan_first_step": None,
        "max_displacement_per_mo": {},
        "max_force_per_mo": {},
    }


def _empty_scene_summary() -> Dict[str, Any]:
    return {"node_count": 0, "class_counts": {}, "actuators_only": False}


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
                "solver_logs": captured,
                "scene_summary": _empty_scene_summary(),
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
                "anomalies": anomalies,
                "metrics": _empty_metrics(),
                "init_stdout_findings": [],
                "solver_logs": solver_logs,
                "scene_summary": _empty_scene_summary(),
            }

        if not payload.get("success"):
            return {
                "success": False,
                "error": payload.get("error") or "runner reported failure",
                "message": "diagnose_scene runner reported a failure during init or animate.",
                "traceback": payload.get("traceback"),
                "anomalies": anomalies,
                "metrics": payload.get("metrics") or _empty_metrics(),
                "init_stdout_findings": payload.get("init_stdout_findings") or [],
                "solver_logs": solver_logs,
                "scene_summary": payload.get("scene_summary") or _empty_scene_summary(),
            }

        merged = {
            "success": True,
            "metrics": payload.get("metrics") or _empty_metrics(),
            "anomalies": anomalies,
            "init_stdout_findings": payload.get("init_stdout_findings") or [],
            "solver_logs": solver_logs,
            "scene_summary": payload.get("scene_summary") or _empty_scene_summary(),
        }
        if "summarize_error" in summary_part:
            merged["summarize_error"] = summary_part["summarize_error"]
        return merged

    finally:
        try:
            os.remove(output_json_path)
        except OSError:
            pass
