"""Phase 7: the scene-running tools run as MCP background tasks
(io.modelcontextprotocol/tasks, spec 2026-07-28) when the client opts in.

Uses the in-memory FastMCP client, which registers the tasks client
extension automatically. The legacy (non-opt-in) blocking path is covered
by test/test_architect/test_mcp_transport.py, whose bare `mcp` ClientSession
never declares the extension.
"""

import asyncio
import os

from fastmcp import Client
from fastmcp_tasks.client import call_tool_task

import sofa_mcp.server as srv

FIXTURE = os.path.join(
    os.path.dirname(__file__), "test_observer", "fixtures", "m5_units_mismatch.py"
)


def _payload(result):
    return result.data if result.data is not None else result.structured_content


def test_diagnose_scene_runs_as_task_and_server_status_sees_it():
    async def main():
        async with Client(srv.mcp) as c:
            task = await call_tool_task(
                c, "diagnose_scene", {"scene_path": FIXTURE, "steps": 3, "dt": 0.01}
            )
            assert task.task_id

            # While the task runs, server_status must show it in flight.
            # Poll briefly: the docket worker picks the task up asynchronously.
            seen = None
            for _ in range(50):
                status = _payload(await c.call_tool("server_status", {"log_tail": 1}))
                running = status["runs_in_flight"]["running"]
                if any(r["tool"] == "diagnose_scene" for r in running):
                    seen = running
                    break
                await asyncio.sleep(0.1)
            assert seen, "diagnose_scene never appeared in runs_in_flight"
            assert seen[0]["scene_path"] == FIXTURE

            final = _payload(await task.result())
            assert "anomalies" in final
            assert "metrics" in final

            after = _payload(await c.call_tool("server_status", {"log_tail": 1}))
            assert after["runs_in_flight"]["count"] == 0

    asyncio.run(main())


def test_perturb_and_run_transparent_call_resolves_task():
    """client.call_tool on a task-capable tool polls to completion itself."""
    async def main():
        async with Client(srv.mcp) as c:
            res = _payload(await c.call_tool(
                "perturb_and_run",
                {"scene_path": FIXTURE, "parameter_changes": {}, "steps": 2, "dt": 0.01},
            ))
            assert isinstance(res, dict)
            assert "success" in res

    asyncio.run(main())
