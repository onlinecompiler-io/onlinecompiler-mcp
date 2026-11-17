# OnlineCompiler MCP Server

An [MCP](https://modelcontextprotocol.io) server that lets AI assistants execute code in 46 programming languages via [OnlineCompiler.io](https://onlinecompiler.io).

Each run starts a fresh gVisor sandbox (512 MB RAM, 30 s timeout, no network access).

## Supported Languages

Python, C, C++, Fortran, Java, C#, F#, Visual Basic, Go, Rust, PHP, Ruby, Haskell, TypeScript (Deno), JavaScript (Node.js), Kotlin, R, Bash, SQL (SQLite), SQL (DuckDB), Swift, COBOL, Perl, Julia, Pascal, Octave, Assembly (NASM), Lua, OCaml, Common Lisp, Erlang, Elixir, Prolog, D, FreeBASIC, Dart, Clojure, Groovy, Scala, Zig, Nim, Crystal, Ada, PowerShell, Racket and Objective-C. `list_compilers` returns the current list with versions.

## Setup

Point your MCP client at the URL. No install needed.

```
https://api.onlinecompiler.io/mcp
```

There are two ways in:

- **Sign in (OAuth).** Clients that support MCP sign-in (claude.ai, Claude Desktop and mobile, ChatGPT, Claude Code, Codex) open an OnlineCompiler.io sign-in page (Google or an email link) and ask you to approve. The app then appears as a key named after it, for example "Claude (connected app)", on your [API Keys page](https://api.onlinecompiler.io/compilers/api-keys/). Disable that key to disconnect the app.
- **API key.** Send your key as `Authorization: Bearer <key>` (the bare key works too). Get a free key on the [API Keys page](https://api.onlinecompiler.io/compilers/api-keys/).

Runs count against your plan either way. A wrong or disabled key gets `401`.

To run the server yourself instead (version 0.6.0 and later): `onlinecompiler-mcp` serves Streamable HTTP on port 8080 (`MCP_HOST`, `MCP_PORT`) and takes each caller's key as a Bearer token, while `onlinecompiler-mcp --transport stdio` speaks stdio for local clients and reads your key from `ONLINECOMPILER_API_KEY`.

## Tools

### `list_compilers`
List all available compilers with their identifiers.

### `run_code`
Execute code with a specified compiler.

**Parameters:**
- `code` (required): Source code to execute
- `compiler` (required): Compiler identifier from `list_compilers` (e.g. `python-3.14`, `gcc-15`)
- `input` (optional): Standard input for the program
- `time_limit` (optional): Seconds the run may take, above 0 and at most 30 (default 30)
- `files` (optional): Files the program can use, up to 20 and 1,000,000 decoded bytes in total: helper source files (compiled with the program) and input data. Each `{"name": "util.py" or "pkg/util.py", "content": "...", "encoding": "utf8" or "base64"}`; the program finds them in its working directory

`python-3.14` includes numpy, pandas, scipy, scikit-learn, matplotlib, seaborn, statsmodels, sympy, openpyxl, pillow, duckdb, polars, wordcloud, pgmpy and nltk. Files a program writes to `$OUTPUT_DIR` come back (png, svg, csv, json, txt; up to 8 files and 2 MB), and `plt.show()` saves each open figure as a PNG.

**Returns:** `output`, `error`, `status`, `exit_code`, `time`, `memory`, `truncated`, `files`, `files_truncated`. PNG files arrive as MCP image content; SVG, CSV, JSON and text files are listed with their `text` (cut at 64 KB).

### `run_tests`
Check a program against test cases and judge it like an online judge. At most 10 tests per call, each counting as one run. Every test runs unless the code fails to compile or the request runs out of time.

**Parameters:**
- `code` (required): Source code to check
- `compiler` (required): Compiler identifier from `list_compilers`
- `tests` (required): Up to 10 objects, each `{"input": "...", "expected_output": "..."}`
- `time_limit` (optional): Seconds per test, above 0 and at most 30 (default 2); compiling does not count, and Java, Groovy and F# get a start-up allowance on top
- `checker` (optional): `trim` (default), `exact`, `tokens`, `float`, `rows` (unordered lines, numbers within tolerance), `table` (CSV tables with a header row compared by column name, rows in any order; print `df.to_csv(index=False)`) or `table_ordered` (the same, rows in order)
- `files` (optional): Files shared by every test (input data or helper source files), same shape as in `run_code`

**Returns:** an overall `verdict`, a `score` from 0 to 100 and a verdict per test.

### `judge_problem`
Judge code against one of your stored problems. Hidden tests return only their verdict, never their input or expected output. Nothing is invented: a missing problem or a failed run is an error (for example `HTTP 404: Problem not found`).

**Parameters:**
- `problem` (required): The id or slug of one of your stored problems
- `compiler` (required): Compiler identifier from `list_compilers`
- `code` (required): Source code to judge
- `mode` (optional): `all` (default) runs every test; `samples` runs only the sample tests

**Returns:** a `verdict`, a `score`, a per-test verdict, a `summary`, a `submission` id, a signed `receipt`, and the `problem` id and `version`.

## Client Configuration

### claude.ai, Claude Desktop and mobile

In claude.ai or Claude Desktop, open Customize, then Connectors, then Add custom connector. Paste `https://api.onlinecompiler.io/mcp`, sign in to OnlineCompiler.io when asked and approve. The connector belongs to your Claude account, so it works in the Claude mobile apps too.

### ChatGPT

Turn on developer mode in ChatGPT's settings, add a custom connector with `https://api.onlinecompiler.io/mcp` and sign in when asked.

### Claude Code

```bash
claude mcp add --transport http onlinecompiler https://api.onlinecompiler.io/mcp
```

Then run `/mcp` inside Claude Code, pick onlinecompiler and sign in. To use an API key instead:

```bash
claude mcp add onlinecompiler https://api.onlinecompiler.io/mcp --transport http --header "Authorization: Bearer YOUR_API_KEY"
```

### Gemini CLI

Install the extension from this repository:

```bash
gemini extensions install https://github.com/onlinecompiler-io/onlinecompiler-mcp
```

It adds the hosted server at `https://api.onlinecompiler.io/mcp` and a short context file telling Gemini when to use the tools. Gemini CLI signs you in with OAuth. To use an API key instead, add the server by hand in `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "onlinecompiler": {
      "httpUrl": "https://api.onlinecompiler.io/mcp",
      "headers": { "Authorization": "Bearer your-api-key" }
    }
  }
}
```

### Claude Code plugin

This repository is also a Claude Code plugin marketplace:

```
/plugin marketplace add onlinecompiler-io/onlinecompiler-mcp
/plugin install onlinecompiler@onlinecompiler
```

Then run `/mcp`, pick onlinecompiler and sign in. The plugin does the same as the `claude mcp add` command above.

### Cline

See [llms-install.md](https://github.com/onlinecompiler-io/onlinecompiler-mcp/blob/main/llms-install.md): add the URL as a remote server with your API key in an `Authorization` header.

### Codex

```bash
codex mcp add onlinecompiler --url https://api.onlinecompiler.io/mcp
codex mcp login onlinecompiler
```

To use an API key instead, skip the login and put the key in the environment variable that `bearer_token_env_var` names, in `~/.codex/config.toml`:

```toml
[mcp_servers.onlinecompiler]
url = "https://api.onlinecompiler.io/mcp"
bearer_token_env_var = "ONLINECOMPILER_API_KEY"
```

### VS Code (Copilot / Claude extension)

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "onlinecompiler": {
      "url": "https://api.onlinecompiler.io/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "onlinecompiler": {
      "url": "https://api.onlinecompiler.io/mcp",
      "headers": {
        "Authorization": "Bearer your-api-key"
      }
    }
  }
}
```
