"""MCP-transport regression net.

The unit tests in test_summarize_rules.py exercise summarize_scene by calling the
function directly. That path uses the developer-environment Python (UTF-8 default)
and bypasses MCP serialization. Real agents reach the tool through the streamable-HTTP
transport, where the server process may resolve a different default encoding and where
the response goes through a JSON-RPC round trip.

This module spawns a real server subprocess and calls summarize_scene through the
official MCP client SDK to catch:

  - Encoding regressions: rule messages contain em-dashes (U+2014); a non-UTF-8
    fallback in `tempfile.NamedTemporaryFile(mode='w')` makes the wrapper unwriteable
    and every tool call returns an error string.
  - Tool-result envelope changes: confirms the JSON shape (`success`, `checks`,
    `nodes`, legacy booleans) survives the transport.

Skipped when SOFA isn't available, or when the MCP SDK isn't installed in the
test environment.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import pytest

PROJECT_ROOT = "/home/sizhe/workspace/SOFA_MCP"
PYTHON = os.path.expanduser("~/venv/bin/python")
SERVER = os.path.join(PROJECT_ROOT, "sofa_mcp", "server.py")

_REASON_NO_SOFA = "SOFA env (~/venv with SofaPython3) not available"
_REASON_NO_MCP = "MCP client SDK not available"

if not os.path.exists(PYTHON):
    pytest.skip(_REASON_NO_SOFA, allow_module_level=True)

try:
    from mcp import ClientSession  # noqa: F401
    from mcp.client.streamable_http import streamable_http_client  # noqa: F401
except Exception:
    pytest.skip(_REASON_NO_MCP, allow_module_level=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(host: str, port: int, timeout: float = 120.0) -> bool:
    """Poll a TCP connect — any successful connect means uvicorn is accepting.

    Don't use HTTP probing here: FastMCP's streamable-http transport returns 405
    Method Not Allowed for plain GETs, which urllib raises as an exception that
    looks identical to "server not up yet." Raw socket connect is unambiguous.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def mcp_server_url(tmp_path_factory):
    port = _free_port()
    env = {**os.environ, "SOFA_MCP_PORT": str(port)}
    log_path = tmp_path_factory.mktemp("mcp_server") / "server.log"
    log = open(log_path, "w")
    proc = subprocess.Popen(
        [PYTHON, SERVER],
        env=env,
        cwd=PROJECT_ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}/mcp/"
    try:
        if not _wait_until_ready("127.0.0.1", port, timeout=120):
            proc.kill()
            log.close()
            try:
                tail = open(log_path).read()[-2000:]
            except Exception:
                tail = "(no log)"
            pytest.fail(
                f"MCP server failed to start within 120s on port {port}.\n"
                f"--- last 2KB of server log ({log_path}) ---\n{tail}"
            )
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def _call_summarize(url: str, content: str) -> dict:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _go():
        async with streamable_http_client(url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(
                    "summarize_scene", {"script_content": content}
                )

    result = asyncio.run(_go())
    text = "".join(getattr(c, "text", "") for c in result.content)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        # Surface the raw text — encoding regressions appear here as a FastMCP
        # error string ("Error calling tool ...: 'ascii' codec can't encode...").
        raise AssertionError(
            f"summarize_scene over MCP returned non-JSON: {text[:500]}"
        ) from exc


# Scene that triggers Rule 4 with severity=error. The trigger guarantees the wrapper
# emits a non-trivial check entry, but the encoding regression would fail BEFORE the
# checks ever run — the wrapper file itself contains em-dashes throughout.
_TRIGGER_RULE_4 = """
def createScene(rootNode):
    rootNode.gravity = [0, -9.81, 0]
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.AnimationLoop")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.LinearSolver.Direct")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.ODESolver.Backward")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.SolidMechanics.FEM.Elastic")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.StateContainer")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Mass")
    rootNode.addObject("RequiredPlugin", name="Sofa.Component.Topology.Container.Grid")
    rootNode.addObject("DefaultAnimationLoop")
    rootNode.addObject("EulerImplicitSolver")
    rootNode.addObject("SparseLDLSolver", template="CompressedRowSparseMatrixMat3x3d")
    n = rootNode.addChild("body")
    # Implicit ODE solver in this subtree but no linear solver in the same node or
    # descendants; ancestor's solver does NOT count. Rule 4 must fire as error.
    n.addObject("EulerImplicitSolver")
    n.addObject("RegularGridTopology", min=[0,0,0], max=[1,1,1], n=[3,3,3])
    n.addObject("MechanicalObject")
    n.addObject("UniformMass", totalMass=1.0)
    n.addObject("TetrahedronFEMForceField", youngModulus=1e5, poissonRatio=0.3)
"""


def test_summarize_scene_round_trip_over_mcp(mcp_server_url):
    """End-to-end: real subprocess, real MCP client, real JSON-RPC round trip.

    Asserts both the envelope (`success`, legacy booleans, checks shape) and a
    domain expectation (Rule 4 fires for the trigger scene). The test fails if
    encoding falls back to ASCII, if the JSON envelope changes, or if Rule 4
    stops detecting the trigger.
    """
    parsed = _call_summarize(mcp_server_url, _TRIGGER_RULE_4)

    # Envelope.
    assert parsed.get("success") is True, f"expected success, got: {parsed}"
    assert "has_animation_loop" in parsed, "legacy boolean has_animation_loop missing"
    assert "has_time_integration" in parsed
    assert "has_constraint_solver" in parsed

    # Checks list shape.
    checks = parsed.get("checks")
    assert isinstance(checks, list) and checks, "checks should be a non-empty list"
    for c in checks:
        assert {"rule", "severity", "subject", "message"} <= set(c), (
            f"check entry missing required keys: {c}"
        )

    # Domain expectation: Rule 4 fires.
    rule_4 = [c for c in checks if c.get("rule") == "rule_4_linear_solver"]
    assert rule_4, "rule_4_linear_solver not present in checks"
    assert rule_4[0]["severity"] == "error", (
        f"expected rule_4 error, got {rule_4[0]['severity']}"
    )
    assert "linear solver" in rule_4[0]["message"].lower()
