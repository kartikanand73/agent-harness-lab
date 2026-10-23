# Claude entry point

Read AGENTS.md, then Task.md, then the linked task brief. Inspect source and tests
before writing code. Follow the workflow in docs/HARNESS-RUNBOOK.md.

Baseline: `python -m unittest discover -s tests -v`.

This application uses only the Python standard library. Run commands from the
repository root. Python 3.11 or newer is required.

Your task is to enhance this application using the user's harness. The repository
does not include the harness itself. Finish at a reviewable PR; a human merges.
