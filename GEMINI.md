# OnlineCompiler

Use the onlinecompiler tools to run code instead of guessing its output.

- Call `list_compilers` first and use an exact compiler id from it (for example `python-3.14`, `gcc-15`).
- Use `run_code` to run a program, with optional stdin in `input`. Each run is a fresh sandbox with no network.
- Use `run_tests` to check a solution against up to 10 test cases and report the verdict.
- Use `judge_problem` only when the user has stored problems in their OnlineCompiler.io account.
- Report `output`, `error` and `exit_code` as they are. A non-zero `exit_code` or a non-empty `error` means the run failed.
