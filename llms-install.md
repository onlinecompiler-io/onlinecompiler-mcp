# Installing the OnlineCompiler MCP server (for AI agents)

This server is hosted, so there is nothing to install or build. Add it to the client's MCP settings as a remote server (streamable HTTP) at:

```
https://api.onlinecompiler.io/mcp
```

## Cline

Add this to the MCP settings file (`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "onlinecompiler": {
      "type": "streamableHttp",
      "url": "https://api.onlinecompiler.io/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

Replace `YOUR_API_KEY` with the user's key (see below). Clients that support MCP sign-in (OAuth), such as Claude Code, Codex and Gemini CLI, can leave the `headers` block out and sign in instead.

## API key

Ask the user for a key and do not invent one. A free key (100,000 runs a month) is on the API Keys page: https://api.onlinecompiler.io/compilers/api-keys/ . Send it as `Authorization: Bearer <key>`. A wrong or disabled key gets HTTP 401.

## Check that it works

Call `list_compilers`. It returns the available compiler ids (for example `python-3.14`, `gcc-15`). Then call `run_code` with `compiler` set to `python-3.14` and `code` set to `print("hello")`; the result has `output` "hello\n" and `exit_code` 0.

## Tools

`list_compilers`, `run_code`, `run_tests` and `judge_problem`. Parameters are in README.md.
