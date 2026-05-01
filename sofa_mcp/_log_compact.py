"""Compact-log filter for SOFA stdout/stderr capture.

Hybrid allowlist + tail-anchor strategy. Used by `diagnose_scene`,
`validate_scene`, and `summarize_scene` to slim the captured SOFA log
when their `verbose` kwarg is False.

Lines are kept if:
  - they match any allowlist pattern (signal: errors, warnings, plugin
    loads, convergence summaries, tracebacks, runtime-template sentinels),
  - they are inside a multi-line traceback block opened by an allowlist
    hit, or
  - they fall within the final `tail_lines` lines (safety anchor for
    end-of-log signals the allowlist might miss).

The function returns a `(filtered_text, dropped_count)` tuple so callers
can attach the dropped-line count to their response shape — that's the
agent's cue that a retry with `verbose=True` might be warranted.
"""

import re
from typing import Tuple


_KEEP_PATTERNS = (
    re.compile(r"\[ERROR\]"),
    re.compile(r"\[WARNING\]"),
    re.compile(r"\[FATAL\]"),
    re.compile(r"\[DEPRECATED\]"),
    re.compile(r"\[SUGGESTION\]"),
    re.compile(r"Loaded plugin", re.IGNORECASE),
    re.compile(r"Convergence after \d+", re.IGNORECASE),
    re.compile(r"did not converge", re.IGNORECASE),
    re.compile(r"\b\d+\s+iterations?\b", re.IGNORECASE),
    re.compile(r"\bresidual\s*[=:]", re.IGNORECASE),
    re.compile(r"QP infeasible"),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r'^\s*File ".*", line \d+'),
    re.compile(r"SCENE_SUMMARY_JSON:"),
    re.compile(r"SUCCESS:"),
    re.compile(r"__SOFA_MCP_"),
)

QP_INFEASIBLE_RE = re.compile(r"QP infeasible")
_TRACEBACK_OPEN_RE = re.compile(r"Traceback \(most recent call last\)")


def _is_signal(line: str) -> bool:
    return any(pat.search(line) for pat in _KEEP_PATTERNS)


def compact_log(text: str, *, tail_lines: int = 20) -> Tuple[str, int]:
    """Filter `text` to a compact subset; return (filtered_text, dropped).

    Behaviour:
      - Empty input → ("", 0).
      - Input shorter than `tail_lines` → returned verbatim with 0 dropped.
      - Otherwise, allowlist + multi-line traceback state + tail anchor.
    """
    if not text:
        return text, 0

    lines = text.splitlines()
    n = len(lines)
    if n <= tail_lines:
        return text, 0

    keep = [False] * n

    in_traceback = False
    for i, line in enumerate(lines):
        if _is_signal(line):
            keep[i] = True
            if _TRACEBACK_OPEN_RE.search(line):
                in_traceback = True
            continue
        if in_traceback:
            if line.strip() == "":
                in_traceback = False
                continue
            if line.startswith((" ", "\t")):
                keep[i] = True
                continue
            # Non-indented, non-blank: the exception line. Keep, then close.
            keep[i] = True
            in_traceback = False

    tail_start = max(0, n - tail_lines)
    for i in range(tail_start, n):
        keep[i] = True

    kept_lines = [lines[i] for i in range(n) if keep[i]]
    dropped = n - len(kept_lines)

    out = "\n".join(kept_lines)
    if text.endswith("\n"):
        out += "\n"
    return out, dropped
