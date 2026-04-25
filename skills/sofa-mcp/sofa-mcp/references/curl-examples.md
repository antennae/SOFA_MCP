# Raw HTTP examples for SOFA MCP

Most agents talk to the MCP server through the standard MCP transport — they don't need to construct JSON-RPC envelopes by hand. These examples are for human debugging only.

## Request envelope

Every request is JSON-RPC 2.0. The `Accept: application/json` header is required (without it the server returns 406):

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"<method>","params":<params>}'
```

## List available tools

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Call a tool

`tools/call` takes `name` and `arguments`:

```bash
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"validate_scene","arguments":{"script_content":"<full createScene script>"}}}'
```

For each tool's argument shape, use `tools/list` (above) — every schema lives there.

## Common gotchas

- **Forgetting `Accept: application/json`** → 406 Not Acceptable.
- **Server not yet ready on first launch** → connection refused for ~30 seconds while the plugin cache builds.
- **Tool returns `success: false` with a long C++ traceback** → SOFA failed during init or animate. Read the traceback alongside `summarize_scene` output to localize the problem.
