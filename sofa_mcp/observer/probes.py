"""Parent-side orchestrator for the Step 4 probes.

Two probes:
  - enable_logs_and_run: toggle printLog on user-specified targets,
    animate, return filtered logs.
  - perturb_and_run: apply Data-field overrides before init, animate,
    return per-MO metrics. (Implemented in Task 2.)

Both delegate to a single shared subprocess runner `_probe_runner.py`
that dispatches by --mode argv.
"""

import json
import os
import pathlib
import subprocess
import tempfile
from typing import Any, Dict, List, Union

from sofa_mcp._log_compact import compact_log


PYTHON = os.path.expanduser("~/venv/bin/python")
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_probe_runner.py")

_DEFAULT_TIMEOUT_S = 90


def _run_subprocess(mode: str, scene_path: str, spec: Dict[str, Any], timeout_s: int) -> Dict[str, Any]:
    """Dispatch the runner subprocess and return its parsed JSON payload
    (or a failure-shape dict on timeout / no-payload / decode error).

    The captured stdout+stderr is returned in a separate `_logs_raw` key
    so callers can apply `compact_log` per-probe.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as spec_tmp:
        json.dump(spec, spec_tmp)
        spec_path = spec_tmp.name
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False, encoding="utf-8") as out_tmp:
        output_path = out_tmp.name

    try:
        try:
            result = subprocess.run(
                [PYTHON, RUNNER, mode, str(scene_path), spec_path, output_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
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
                "message": f"probe runner exceeded {timeout_s}s.",
                "_logs_raw": captured,
            }

        logs_raw = (result.stdout or "") + (result.stderr or "")

        try:
            with open(output_path, "r", encoding="utf-8") as f:
                raw = f.read()
            payload = json.loads(raw) if raw.strip() else None
        except (json.JSONDecodeError, OSError) as exc:
            return {
                "success": False,
                "error": f"runner produced no payload (returncode={result.returncode}): {exc}",
                "_logs_raw": logs_raw,
            }

        if payload is None:
            return {
                "success": False,
                "error": f"runner produced empty payload (returncode={result.returncode})",
                "_logs_raw": logs_raw,
            }

        payload["_logs_raw"] = logs_raw
        return payload

    finally:
        for p in (spec_path, output_path):
            try:
                os.remove(p)
            except OSError:
                pass


def enable_logs_and_run(
    scene_path: str,
    log_targets: List[Union[str, Dict[str, Any]]],
    steps: int = 5,
    dt: float = 0.01,
    verbose: bool = False,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Toggle printLog=True on objects matching log_targets, animate for
    `steps` iterations, return captured stdout/stderr (compacted by default).

    log_targets is a list of strings. A string containing '/' is treated as
    a node-path or path fragment (substring match). A bare string is treated
    as a class name (exact match).

    Returns:
        {success, log_targets_activated, log_targets_not_found, logs,
         log_lines_dropped?, error?}
    """
    path = pathlib.Path(scene_path).expanduser()
    if not path.exists() or not path.is_file():
        return {
            "success": False,
            "error": f"Scene file not found: {scene_path}",
            "log_targets_activated": [],
            "log_targets_not_found": list(log_targets),
            "logs": "",
        }

    spec = {"log_targets": list(log_targets), "steps": int(steps), "dt": float(dt)}
    payload = _run_subprocess("enable_logs", str(path), spec, timeout_s)

    logs_raw = payload.pop("_logs_raw", "") or ""
    if verbose:
        logs = logs_raw
        dropped = 0
    else:
        logs, dropped = compact_log(logs_raw)

    response: Dict[str, Any] = {
        "success": bool(payload.get("success")),
        "log_targets_activated": payload.get("log_targets_activated") or [],
        "log_targets_not_found": payload.get("log_targets_not_found") or [],
        "logs": logs,
    }
    if dropped:
        response["log_lines_dropped"] = dropped
    if payload.get("error"):
        response["error"] = payload["error"]
    if payload.get("traceback"):
        response["traceback"] = payload["traceback"]
    return response


def perturb_and_run(
    scene_path: str,
    parameter_changes: Dict[str, Dict[str, Any]],
    steps: int = 50,
    dt: float = 0.01,
    verbose: bool = False,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> Dict[str, Any]:
    """Apply Data-field overrides specified by `parameter_changes`
    (`{"/path": {"field": value, ...}, ...}`) before init, animate for
    `steps` steps, return per-MO metrics.

    Returns:
        {success, parameter_changes_applied, parameter_changes_failed,
         metrics: {nan_first_step, max_displacement_per_mo,
                   max_force_per_mo}, logs, log_lines_dropped?, error?}
    """
    path = pathlib.Path(scene_path).expanduser()
    if not path.exists() or not path.is_file():
        return {
            "success": False,
            "error": f"Scene file not found: {scene_path}",
            "parameter_changes_applied": [],
            "parameter_changes_failed": [],
            "metrics": {"nan_first_step": None, "max_displacement_per_mo": {}, "max_force_per_mo": {}},
            "logs": "",
        }

    spec = {
        "parameter_changes": dict(parameter_changes or {}),
        "steps": int(steps),
        "dt": float(dt),
    }
    payload = _run_subprocess("perturb", str(path), spec, timeout_s)

    logs_raw = payload.pop("_logs_raw", "") or ""
    if verbose:
        logs = logs_raw
        dropped = 0
    else:
        logs, dropped = compact_log(logs_raw)

    response: Dict[str, Any] = {
        "success": bool(payload.get("success")),
        "parameter_changes_applied": payload.get("parameter_changes_applied") or [],
        "parameter_changes_failed": payload.get("parameter_changes_failed") or [],
        "metrics": payload.get("metrics") or {
            "nan_first_step": None,
            "max_displacement_per_mo": {},
            "max_force_per_mo": {},
        },
        "logs": logs,
    }
    if dropped:
        response["log_lines_dropped"] = dropped
    if payload.get("error"):
        response["error"] = payload["error"]
    if payload.get("traceback"):
        response["traceback"] = payload["traceback"]
    return response
