"""MCP server for OnlineCompiler.io: execute code in 46 languages."""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Annotated, Literal
from urllib.parse import quote

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent

API_URL = os.environ.get(
    "ONLINECOMPILER_API_URL", "https://api.onlinecompiler.io"
)


class ApiKeyAuth(TokenVerifier):
    """Validate API keys by forwarding to the Django backend."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        return AccessToken(token=token, client_id=token[:8], scopes=[])


mcp = FastMCP(
    name="OnlineCompiler",
    instructions=(
        "This server lets you compile and run code in 46 programming languages "
        "via the OnlineCompiler.io API. Use list_compilers to see available "
        "languages, run_code to execute code, run_tests to judge a solution against test cases, "
        "and judge_problem to judge code against one of your stored problems."
    ),
    auth=ApiKeyAuth(),
)


def _get_api_key() -> str:
    """Get the API key from the Bearer token."""
    token = get_access_token()
    if token and token.token:
        return token.token
    raise ToolError(
        "Authentication required. Pass your API key as a Bearer token."
    )


@mcp.tool(tags={"compiler", "discovery"})
async def list_compilers() -> list[dict]:
    """List all available compilers/languages supported by OnlineCompiler.io.

    Returns a list of compiler objects with id and name.
    Use the id value as the compiler argument when calling run_code.
    """
    async with httpx.AsyncClient(base_url=API_URL, timeout=10) as client:
        resp = await client.get("/api/compilers/")
        if resp.status_code != 200:
            raise ToolError(f"Failed to list compilers: HTTP {resp.status_code}")
        return resp.json()["compilers"]


MAX_TEXT_FILE_CHARS = 64 * 1024
TEXT_FILE_MIMES = {"text/csv", "application/json", "text/plain", "image/svg+xml"}
FILES_PARAM = (
    "Files the program can use, up to 20 and 1,000,000 decoded bytes in total: helper source files "
    "(compiled with the program) and input data. Each {'name': 'util.py' or 'pkg/util.py', 'content': text, "
    "'encoding': 'utf8' (default) or 'base64'}. They sit in the program's working directory, so "
    "pd.read_csv('data.csv') works."
)


def _strip_file_bytes(value):
    """Copy of an API result without any file's content_base64."""
    if isinstance(value, dict):
        return {k: _strip_file_bytes(v) for k, v in value.items() if k != "content_base64"}
    if isinstance(value, list):
        return [_strip_file_bytes(v) for v in value]
    return value


def _decoded_text(entry: dict) -> str | None:
    """The file as text, cut at MAX_TEXT_FILE_CHARS; None unless it is base64 of valid UTF-8."""
    try:
        return base64.b64decode(entry.get("content_base64") or "").decode("utf-8")[:MAX_TEXT_FILE_CHARS]
    except (ValueError, TypeError):  # UnicodeDecodeError and binascii.Error are ValueErrors
        return None


def _code_result(result: dict) -> ToolResult:
    """PNG images become MCP image blocks; SVG and text files get a decoded `text` field."""
    structured = _strip_file_bytes({k: v for k, v in result.items() if k != "files"})
    images = []
    listed = []
    for entry in result.get("files") or []:
        shown = _strip_file_bytes(entry)
        if entry.get("mime") == "image/png" and entry.get("content_base64"):
            images.append(ImageContent(type="image", data=entry["content_base64"], mime_type="image/png"))
        elif entry.get("mime") in TEXT_FILE_MIMES:
            text = _decoded_text(entry)
            if text is not None:
                shown["text"] = text
        listed.append(shown)
    if "files" in result:
        structured["files"] = listed
    return ToolResult(
        content=[TextContent(type="text", text=json.dumps(structured)), *images],
        structured_content=structured,
    )


@mcp.tool(tags={"compiler", "execution"})
async def run_code(
    code: Annotated[str, "The source code to execute"],
    compiler: Annotated[
        str,
        "Compiler identifier (e.g. 'python-3.14', 'gcc-15'). Use list_compilers to see all options.",
    ],
    input: Annotated[str, "Standard input (stdin) to provide to the program"] = "",
    time_limit: Annotated[
        float | None,
        "Seconds the run may take, above 0 and at most 30. Defaults to 30.",
    ] = None,
    files: Annotated[list[dict] | None, FILES_PARAM] = None,
) -> ToolResult:
    """Run one program in a sandbox and return its output.

    Returns output, error, status, exit_code, time (wall-clock seconds), memory and truncated.
    Limited to 30 seconds (or time_limit) and 512 MB RAM. To check a solution against
    expected outputs, use run_tests instead.

    python-3.14 includes numpy, pandas, scipy, scikit-learn, matplotlib, seaborn, statsmodels,
    sympy, openpyxl, pillow, duckdb, polars, wordcloud, pgmpy and nltk (with WordNet, VADER and the
    English POS tagger data) (no network, so nothing else can be installed).
    Files a program writes to the directory in $OUTPUT_DIR come back in `files` (png, svg, csv,
    json and txt; up to 8 files and 2 MB): PNG charts are returned as images, and SVG, CSV, JSON
    and text files with their `text`. plt.show() saves each open figure as figure-N.png, so
    tutorial code returns its chart. Pass `files` to give the program input data or helper source files.
    """
    api_key = _get_api_key()
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    payload = {"code": code, "compiler": compiler, "input": input}
    if time_limit is not None:
        payload["time_limit"] = time_limit
    if files:
        payload["files"] = files
    async with httpx.AsyncClient(base_url=API_URL, timeout=35) as client:
        resp = await client.post(
            "/api/run-code-sync/",
            json=payload,
            headers=headers,
        )
        if resp.status_code != 200:
            raise ToolError(
                f"Code execution failed: HTTP {resp.status_code}: {resp.text}"
            )
        return _code_result(resp.json())


MAX_TESTS = 10


def _tests_payload(tests: list[dict]) -> list[dict]:
    if len(tests) > MAX_TESTS:
        raise ToolError(f"At most {MAX_TESTS} tests per call, got {len(tests)}.")
    # A missing expected_output goes through as null, so the API answers 400 naming the test.
    return [
        {"input": t.get("input", ""), "expected_output": t.get("expected_output")}
        for t in tests
    ]


@mcp.tool(tags={"compiler", "execution", "judging"})
async def run_tests(
    code: Annotated[str, "The source code to check"],
    compiler: Annotated[
        str,
        "Compiler identifier (e.g. 'python-3.14', 'gcc-15'). Use list_compilers to see all options.",
    ],
    tests: Annotated[
        list[dict],
        "Up to 10 test cases, each {'input': stdin text, 'expected_output': text the program should print}.",
    ],
    time_limit: Annotated[
        float | None,
        "Seconds each test may take, above 0 and at most 30. Defaults to 2.",
    ] = None,
    checker: Annotated[
        Literal["trim", "exact", "tokens", "float", "rows", "table", "table_ordered"],
        "How output is compared: trim ignores trailing whitespace (default), exact is byte for byte, "
        "tokens ignores all whitespace differences, float compares numbers within a small tolerance, "
        "rows compares lines as an unordered set (for SQL and pandas output), numbers within tolerance, "
        "table compares CSV tables with a header row by column name, rows in any order (print "
        "df.to_csv()), and table_ordered does the same with rows in order.",
    ] = "trim",
    files: Annotated[list[dict] | None, FILES_PARAM + " Shared by every test."] = None,
) -> dict:
    """Check a program against test cases and judge it like an online judge.

    Takes at most 10 tests, each counting as one run. Every test runs unless the code fails
    to compile or the request runs out of time. Returns an overall verdict, a score from 0
    to 100 and a verdict per test. time_limit is seconds per test; compiling before the run
    does not count against it, and Java, Groovy and F#, which compile as they start, get a
    start-up allowance on top of it. python-3.14 includes numpy, pandas, scipy, scikit-learn,
    matplotlib, seaborn, statsmodels, sympy, openpyxl, pillow, duckdb, polars, wordcloud, pgmpy
    and nltk, and duckdb-1.5 works
    like sqlite-3, so data questions can be judged with checker "rows" and shared `files`.
    Files a program writes to $OUTPUT_DIR come back on visible tests only, as metadata.
    """
    api_key = _get_api_key()
    payload = {
        "code": code,
        "compiler": compiler,
        "tests": _tests_payload(tests),
        "checker": checker,
        "scoring": "percent",
    }
    if time_limit is not None:
        payload["time_limit"] = time_limit
    if files:
        payload["files"] = files
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=API_URL, timeout=90) as client:
        resp = await client.post("/api/run-tests/", json=payload, headers=headers)
        if resp.status_code != 200:
            raise ToolError(
                f"Tests failed to run: HTTP {resp.status_code}: {resp.text}"
            )
        return _strip_file_bytes(resp.json())


# A stored problem's id (prob_ and 24 letters and digits) or slug (1 to 64 lowercase letters, digits and hyphens,
# not starting with a hyphen), as the API takes them in its paths. Anything else is refused before a request is made.
PROBLEM_REF = re.compile(r"prob_[A-Za-z0-9]{24}|[a-z0-9][a-z0-9-]{0,63}")


def _judge_error_message(resp) -> str:
    """The API's {"error"} message, or the body text when it is not JSON."""
    try:
        message = resp.json().get("error")
    except (ValueError, AttributeError):
        message = None
    return f"HTTP {resp.status_code}: {message or resp.text}"


def _judge_result(body: dict) -> dict:
    """The REST body without any per-test files, which a stored problem never shows."""
    result = _strip_file_bytes(body)
    if isinstance(result.get("tests"), list):
        result["tests"] = [
            {k: v for k, v in t.items() if k not in ("files", "files_truncated")} if isinstance(t, dict) else t
            for t in result["tests"]
        ]
    return result


@mcp.tool(tags={"compiler", "execution", "judging"})
async def judge_problem(
    problem: Annotated[str, "The id or slug of one of your stored problems"],
    compiler: Annotated[
        str,
        "Compiler identifier (e.g. 'python-3.14', 'gcc-15'). Use list_compilers to see all options.",
    ],
    code: Annotated[str, "The source code to judge"],
    mode: Annotated[
        Literal["all", "samples"],
        "'all' runs every test (default); 'samples' runs only the sample tests.",
    ] = "all",
) -> dict:
    """Judge code against one of your stored problems.

    Runs the problem's tests and returns a verdict, a score, a summary, a submission id, a
    signed receipt, and the problem id and version. Hidden tests return only their verdict,
    never their input or expected output. It never invents results: if the problem is missing
    or the run fails, you get an error.
    """
    if not isinstance(problem, str) or not PROBLEM_REF.fullmatch(problem):
        raise ToolError("problem must be a problem id or slug")
    api_key = _get_api_key()
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=API_URL, timeout=150) as client:
        resp = await client.post(
            f"/api/problems/{quote(problem, safe='')}/submissions/",
            json={"compiler": compiler, "code": code, "mode": mode},
            headers=headers,
        )
        if resp.status_code != 200:
            raise ToolError(_judge_error_message(resp))
        return _judge_result(resp.json())


def main():
    """Entry point: runs as Streamable HTTP server."""
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8080"))
    mcp.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
