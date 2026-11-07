"""Run with: python -m unittest discover -s tests (from mcp-server/, package installed or on PYTHONPATH=src)."""
import unittest

from onlinecompiler_mcp import server
import asyncio
import base64
import json
from unittest import mock

from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent

PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()
CSV_B64 = base64.b64encode(b"a,b\n1,2\n").decode()
API_RESULT = {
    "output": "ok", "exit_code": 0, "files_truncated": False,
    "files": [
        {"name": "figure-1.png", "mime": "image/png", "size": 12, "content_base64": PNG_B64, "url": "https://x/f/1"},
        {"name": "out.csv", "mime": "text/csv", "size": 8, "content_base64": CSV_B64, "url": None},
    ],
}


def _factory(payload):
    response = mock.Mock(status_code=200)
    response.json.return_value = payload
    client = mock.AsyncMock()
    client.post.return_value = response
    factory = mock.MagicMock()
    factory.return_value.__aenter__.return_value = client
    return factory, client


def run_tool(mod, name, payload, **kwargs):
    factory, client = _factory(payload)
    with (
        mock.patch.object(mod.httpx, "AsyncClient", factory),
        mock.patch.object(mod, "_get_api_key", return_value="key"),
    ):
        result = asyncio.run(getattr(mod, name)(**kwargs))
    return result, client


def check_files_forwarded(tc, mod):
    files = [{"name": "data.csv", "content": "a,b\n1,2\n", "encoding": "utf8"}]
    _, client = run_tool(mod, "run_code", API_RESULT, code="x", compiler="python-3.14", files=files)
    tc.assertEqual(client.post.call_args.kwargs["json"]["files"], files)
    _, client = run_tool(mod, "run_code", API_RESULT, code="x", compiler="python-3.14")
    tc.assertNotIn("files", client.post.call_args.kwargs["json"])


def check_run_code_result(tc, mod):
    result, _ = run_tool(mod, "run_code", API_RESULT, code="x", compiler="python-3.14")
    tc.assertIsInstance(result, ToolResult)
    images = [c for c in result.content if isinstance(c, ImageContent)]
    tc.assertEqual(len(images), 1)
    tc.assertEqual(images[0].data, PNG_B64)
    tc.assertEqual(images[0].mime_type, "image/png")
    texts = [c for c in result.content if isinstance(c, TextContent)]
    tc.assertEqual(len(texts), 1)
    tc.assertEqual(json.loads(texts[0].text), result.structured_content)
    by_name = {f["name"]: f for f in result.structured_content["files"]}
    tc.assertEqual(by_name["out.csv"]["text"], "a,b\n1,2\n")
    for entry in by_name.values():
        tc.assertNotIn("content_base64", entry)
    tc.assertNotIn("text", by_name["figure-1.png"])
    tc.assertEqual(result.structured_content["output"], "ok")


def check_text_cut_at_64kb(tc, mod):
    big = base64.b64encode(b"x" * 100_000).decode()
    payload = {"files": [{"name": "big.txt", "mime": "text/plain", "size": 100000, "content_base64": big, "url": None}]}
    result, _ = run_tool(mod, "run_code", payload, code="x", compiler="python-3.14")
    tc.assertEqual(len(result.structured_content["files"][0]["text"]), 64 * 1024)


def check_svg_gets_validated_text(tc, mod):
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><text>\u00e9t\u00e9</text></svg>'
    payload = {"files": [
        {"name": "c.svg", "mime": "image/svg+xml", "size": 9, "url": None,
         "content_base64": base64.b64encode(svg.encode()).decode()},
        {"name": "bad.svg", "mime": "image/svg+xml", "size": 7, "url": None,
         "content_base64": base64.b64encode(b"<svg>\xff</svg>").decode()},
    ]}
    result, _ = run_tool(mod, "run_code", payload, code="x", compiler="python-3.14")
    good, bad = result.structured_content["files"]
    tc.assertEqual(good["text"], svg)
    tc.assertNotIn("text", bad)
    tc.assertNotIn("content_base64", good)
    tc.assertFalse([c for c in result.content if isinstance(c, ImageContent)])


def check_docstrings_use_the_sites_units(tc, mod):
    docs = mod.run_code.__doc__ + mod.run_tests.__doc__
    tc.assertNotIn("MiB", docs)
    tc.assertIn("2 MB", mod.run_code.__doc__)


def check_run_tests_rows_and_files(tc, mod):
    payload = {"verdict": "accepted", "tests": [
        {"files": [{"name": "o.csv", "mime": "text/csv", "size": 3, "content_base64": CSV_B64, "url": None}],
         "files_truncated": False}]}
    files = [{"name": "d.csv", "content": "1"}]
    result, client = run_tool(
        mod, "run_tests", payload, code="x", compiler="duckdb-1.5",
        tests=[{"input": "", "expected_output": "1"}], checker="rows", files=files,
    )
    body = client.post.call_args.kwargs["json"]
    tc.assertEqual(body["checker"], "rows")
    tc.assertEqual(body["files"], files)
    tc.assertNotIn("content_base64", json.dumps(result))
    tc.assertEqual(result["tests"][0]["files"][0]["name"], "o.csv")


def check_judge_problem(tc, mod):
    from fastmcp.exceptions import ToolError

    body = {"verdict": "accepted", "summary": "ok", "submission": "sub_x", "receipt": {"signature": "s"},
            "problem": "prob_x", "version": 2,
            "tests": [{"verdict": "accepted", "files": [{"name": "o.csv", "content_base64": CSV_B64}]}]}
    factory, client = _factory(body)
    with (
        mock.patch.object(mod.httpx, "AsyncClient", factory),
        mock.patch.object(mod, "_get_api_key", return_value="key"),
    ):
        result = asyncio.run(mod.judge_problem(problem="two-sum", compiler="python-3.14", code="x"))
    tc.assertEqual(factory.call_args.kwargs["timeout"], 150)
    tc.assertEqual(client.post.call_args.args[0], "/api/problems/two-sum/submissions/")
    tc.assertEqual(client.post.call_args.kwargs["json"], {"compiler": "python-3.14", "code": "x", "mode": "all"})
    tc.assertNotIn("files", result["tests"][0])
    for key in ("summary", "submission", "receipt", "problem", "version"):
        tc.assertEqual(result[key], body[key])
    factory, client = _factory({"error": "Problem not found"})
    client.post.return_value.status_code = 404
    client.post.return_value.text = '{"error": "Problem not found"}'
    with (
        mock.patch.object(mod.httpx, "AsyncClient", factory),
        mock.patch.object(mod, "_get_api_key", return_value="key"),
        tc.assertRaises(ToolError) as caught,
    ):
        asyncio.run(mod.judge_problem(problem="nope", compiler="python-3.14", code="x", mode="samples"))
    tc.assertEqual(str(caught.exception), "HTTP 404: Problem not found")
    tc.assertEqual(client.post.call_args.kwargs["json"]["mode"], "samples")


def check_judge_problem_takes_an_id_or_a_slug(tc, mod):
    """As the API's problem ids (prob_ and 24 letters and digits) and slugs; anything else is refused unsent."""
    from fastmcp.exceptions import ToolError

    tc.assertEqual(mod.PROBLEM_REF.pattern, r"prob_[A-Za-z0-9]{24}|[a-z0-9][a-z0-9-]{0,63}")
    for bad in ("a/b c", "", "Two-Sum", "-sum", "x" * 65, "prob_short", "prob_" + "x" * 25, "../submissions",
                "sum\n", "sum?mode=all", "sum%2F", None, 7):
        factory, client = _factory({"verdict": "accepted"})
        with (
            mock.patch.object(mod.httpx, "AsyncClient", factory),
            mock.patch.object(mod, "_get_api_key", return_value="key"),
            tc.assertRaises(ToolError) as caught,
        ):
            asyncio.run(mod.judge_problem(problem=bad, compiler="python-3.14", code="x"))
        tc.assertEqual(str(caught.exception), "problem must be a problem id or slug", bad)
        factory.assert_not_called()
        client.post.assert_not_called()
    for good in ("prob_" + "A1b2" * 6, "a", "two-sum", "x" * 64, "9-lives"):
        factory, client = _factory({"verdict": "accepted"})
        with (
            mock.patch.object(mod.httpx, "AsyncClient", factory),
            mock.patch.object(mod, "_get_api_key", return_value="key"),
        ):
            asyncio.run(mod.judge_problem(problem=good, compiler="python-3.14", code="x"))
        tc.assertEqual(client.post.call_args.args[0], f"/api/problems/{good}/submissions/")


class FilesTests(unittest.TestCase):
    def test_files_forwarded(self):
        check_files_forwarded(self, server)

    def test_run_code_result(self):
        check_run_code_result(self, server)

    def test_text_cut_at_64kb(self):
        check_text_cut_at_64kb(self, server)

    def test_run_tests_rows_and_files(self):
        check_run_tests_rows_and_files(self, server)

    def test_svg_gets_validated_text(self):
        check_svg_gets_validated_text(self, server)

    def test_docstrings_use_the_sites_units(self):
        check_docstrings_use_the_sites_units(self, server)

    def test_judge_problem(self):
        check_judge_problem(self, server)

    def test_judge_problem_takes_an_id_or_a_slug(self):
        check_judge_problem_takes_an_id_or_a_slug(self, server)

    def test_language_count_leaves_out_data_runtimes(self):
        self.assertIn("46 programming languages", server.mcp.instructions)

    def test_instructions_name_each_tool_once(self):
        self.assertIn("languages, run_code to execute code, run_tests to judge a solution against test cases, and "
                      "judge_problem to judge code against one of your stored problems.", server.mcp.instructions)


if __name__ == "__main__":
    unittest.main()
