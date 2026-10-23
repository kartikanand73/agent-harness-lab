# Seven-stage harness exercise

The harness runs outside this application. Integrate these stages with your
existing Claude harness rather than adding a second framework to this repo.

1. **Acquire:** clone the repository into an isolated workspace; inspect its
   current branch and working tree. Create a task branch. Never overwrite local
   changes. Use credentials from your local GitHub integration, not committed files.
2. **Understand:** read AGENTS.md, CLAUDE.md, Task.md, architecture, source, and
   tests. Run the baseline suite and record the result.
3. **Plan:** map acceptance criteria to likely files and tests; keep one task in
   scope. Record assumptions and the intended change before implementation.
4. **Implement:** make a focused change; preserve public behavior outside scope.
   Keep progress notes outside source or in a task-specific work log if needed.
5. **Verify and repair:** run regression and task checks. Use a configurable
   execution/time budget (suggested starting point: three repair attempts, 20
   minutes). The harness must enforce the limits; this document cannot. Stop
   and report evidence if the budget is exhausted. Do not alter tests to hide failure.
6. **Review and submit:** inspect git diff, check for secrets and unintended files,
   commit, push the feature branch, and open a PR. Include actual commands,
   results, costs if measured, and limitations. Human approval precedes merge.
7. **Handover:** a second developer clones the repo, runs the documented checks,
   reads the PR, and reproduces the behavior without your assistance. Log failures
   and compare total effort against ordinary Claude-assisted development.

## Suggested run evidence (record actual values)

- Task ID, base commit, feature branch, final commit, PR URL.
- Baseline, regression, and acceptance commands, exit codes, and summaries.
- Elapsed time, retries, input/output tokens and model cost if available.
- Human time spent specifying, intervening, reviewing, and correcting.
- Changes accepted/rejected and residual issues.

Do not claim that a task is done merely because the agent says it is done. A
passing check is scoped evidence, not proof that every business requirement is met.

## What this exercise demonstrates

The agent must inspect unfamiliar code, preserve a working baseline, change
multiple layers consistently, verify failures, and leave a reviewable handover.
GitHub access, branch protection, budgets, protected acceptance files, credential
handling, and independent review must be configured in the actual harness/host.
