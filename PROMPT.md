# Ralph Standing Prompt

You are running inside a **Ralph loop**: this exact prompt is fed to a fresh
agent (a brand-new context window) on every iteration. You have **no memory** of
previous iterations. Your only durable memory is the files on disk — above all
`PROGRESS.md` — and the state of the working tree. Treat `PROGRESS.md` as your
own notebook left for your next self.

## Every iteration, do exactly this

1. **Read `PROGRESS.md` first.** It is the source of truth for what is done,
   what is in flight, and what is next. If it does not exist, create it from the
   task below.
2. **Re-read the task/spec** in the "Task" section below. Reconcile it against
   `PROGRESS.md` — figure out the single next most valuable increment.
3. **Do that one increment.** Keep it small enough to finish and verify within
   this iteration. Do not attempt the whole task at once.
4. **Verify your work** — run the build/tests/linter or whatever check proves
   the increment is actually correct. Never mark something done you have not
   verified. If you cannot verify, say so in `PROGRESS.md` and leave it open.
5. **Update `PROGRESS.md`**: move the item to Done (with how you verified it),
   record anything you learned, and write the next step so your successor starts
   instantly. Keep it concise and current — prune stale notes.
6. **Stop condition:** when the entire Task is complete AND verified, print the
   done marker `EREV_LOOP_COMPLETE_7Q2X` on its own line as the last thing you
   output. Print it ONLY when truly finished — it terminates the loop. If
   anything remains, do NOT print it. Never write that token anywhere else (not
   in notes, commits or code); refer to it as "the done marker".

## Rules

- Make real, incremental, committed progress every iteration; never spin.
- Prefer the smallest change that advances the goal and can be verified now.
- If you hit an ambiguity you cannot resolve, pick the most reasonable
  interpretation, **record the assumption in `PROGRESS.md`**, and proceed —
  do not stall waiting for input (no human is watching mid-loop).
- If you are blocked by something outside your control (missing credential,
  external service, a decision only a human can make), write a clear
  `BLOCKED:` note at the top of `PROGRESS.md` describing exactly what you need,
  then print the done marker to stop the loop cleanly rather than burning iterations.
- Do not delete or overwrite work you did not create without recording why.
- Keep changes auditable: small, reviewable diffs over sweeping rewrites.

---

## Task

Build **eRev Cloud 1.0** in this repository (`~/dev/erev`) by working through `docs/BUILD_SPEC.md` item by item, in
document order. eRev Cloud is an open-source, multi-tenant ASC 606 / IFRS 15 revenue subledger (FastAPI + PostgreSQL 17
+ React 19). It rebuilds the legacy desktop app eRev (`~/dev/erev-legacy`, read-only), and its UX is modelled on
RightRev-class products.

### Read at the start of every iteration

Several documents are 100–400 KB. **Never Read a document over 100 KB in full.** Use Grep to find the ids the current
item cites, then Read with `offset`/`limit`.

**Always read:**
1. `PROGRESS.md`
2. `docs/00-GOAL.md`: scope, gates G1–G12, standing constraints.
3. `docs/01-DECISIONS.md`: binding decisions, including the §7 amendments, which govern where they differ from the
   original text. Document precedence is in §0 and D-73/D-74.
4. `docs/BUILD_SPEC.md`: the header sections (source precedence, gate table, cross-cutting rules), the item you are
   building and the item after it.
5. `docs/dev-guide.md`: §0.5, §1 (layout), §2.4 (environments and roles), §3 (running), §4 (make targets) and §10
   (gates, git hygiene, forbidden commands, done checklist, evidence format).

**Read only the sections the current item cites:**
- `docs/dev-guide.md` §5–§9 (kernel signatures, conventions, testing contracts);
- `docs/04-DATA_MODEL.md` (tables, enums, identifiers, API);
- `docs/accounting/ENGINE_SPEC.md` and `ENGINE_SPEC_B.md`, `docs/accounting/POLICIES.md`, and the answer keys under
  `docs/accounting/answer-keys/`;
- `docs/legacy/DEVIATIONS.md` and `docs/legacy/golden/`;
- `docs/05-ARCHITECTURE.md`;
- `docs/02-PRD.md`, `docs/03-REQUIREMENTS.md`, `docs/GLOSSARY.md`;
- `docs/design/DESIGN_SYSTEM.md`, `docs/design/SCREENS.md`, `docs/design/SCREENS_B.md` and `docs/design/tokens.css`.

**Background only; never overrides the above:** `docs/research/*`, `docs/legacy/01…07`, `research-harness/`,
`legacy-harness/`.

### Per iteration

1. **Choose the item.**
   - If `PROGRESS.md` has an item under **In flight**, finish it first.
   - Otherwise take the first BUILD_SPEC item, in document order, that is not ticked in `PROGRESS.md`. Supervisor items
     (for example `ENG-5a … Supervisor item`) are ordinary items at their position.
   - You may complete more than one small item in an iteration, but never end an iteration with `make ci` red.
   - Before you start coding, record the item under **In flight**.
2. **Implement it** to its acceptance criteria and to the dev-guide conventions, with tests. The engine
   (`backend/erev_engine`) stays pure: no database, IO, clock or floats.
3. **Verify.**
   - `make ci` must be green.
   - Run the specialist gates the BUILD_SPEC gate table requires for this kind of item (`make answer-keys`,
     `make parity`, `make properties`, `make test-pg`, `make e2e SPEC=…`, `make perf`, as dev-guide §4.4 and §10.1
     define them).
   - For UI items, **Read** the light and dark screenshots your e2e spec wrote. Compare them with SCREENS/SCREENS_B and
     DESIGN_SYSTEM, and fix deviations before ticking.
   - Record a finding in `PROGRESS.md` before you fix it, so the insight survives if the iteration dies.
   - **Keep every gate alive until it finishes.** This loop runs headless (`claude -p`). When your turn ends the
     process exits, and every background job it started is killed (SIGTERM). Iterations 37–39 lost their `make ci`
     and `make test-pg` runs this way and produced nothing.
     - Run a gate expected to finish within 9 minutes as a **foreground** Bash call with `timeout` 600000, then read
       its report.
     - Run a longer gate (for example a full `make e2e` or `make perf`) detached:
       `nohup make <target> > .run/<target>.out 2>&1 & echo $! > .run/<target>.gate.pid`.
       Then wait for it with repeated foreground calls of at most 9 minutes each. Each call is
       `backend/.venv/bin/python -c 'import os,time; p=int(open(".run/<target>.gate.pid").read()); e=time.time()+540`
       followed by a loop that breaks when `os.kill(p, 0)` raises `OSError`, sleeping 5 seconds between checks.
       Repeat until the PID has exited, then read `.run/<target>.out` and `.run/reports/<target>/report.json`.
     - Never use `run_in_background` for a gate or test run. Never end your turn while a job you started is still
       running. If the iteration is nearly out of budget, stop the job by its PID, leave the item **In flight** with
       a handoff note, and end cleanly.
4. **Update `PROGRESS.md`** using the dev-guide §10.5 evidence format.
   - Tick the item as `- [x] <ID> <title> — <evidence: commands and counts>`.
   - Put assumptions under **Spec questions**.
   - Put things only the supervisor can verify (Docker, network, visual judgement you could not complete) under
     **Supervisor verification needed**.
   - Write the next step under **Next**.
   - Keep the file under 20 KB by collapsing older evidence to one line per phase.
   - **Spec questions archive.** When you tick a phase's `GATE-<code>` item, move that phase's **Spec questions** from
     `PROGRESS.md` into `docs/reviews/loop/spec-questions-<code>.md`, verbatim. Create the file with a heading naming
     the phase, and commit it with the GATE item. Keep the ids stable (`SPEC-Q-n` numbering continues across phases).
     Leave **Supervisor verification needed** entries in `PROGRESS.md`.
5. **Commit.**
   - Stage explicit paths only (`git add <paths>`), then `git commit -m "<ID>: <summary>"`.
   - The message body ends with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.
   - Commit `PROGRESS.md` with the item. Never leave files staged.

### Hard rules

- **Git.**
  - Never run `git checkout` (including `git checkout -- <file>` to revert), `git switch`, `git restore`,
    `git reset --hard`, `git stash`, `git clean`, `git rebase`, `git push`, `git commit --amend`, `git add -A` or
    `git add .`.
  - To undo your own change, edit the file back.
- **Supervisor documents.**
  - Do not edit `docs/**` (everything under docs/, including BUILD_SPEC, the answer keys, `deviations.json` and
    `docs/reviews/`), `PROMPT.md`, `research-harness/**` or `legacy-harness/**`. The one exception is the
    spec-questions archive `docs/reviews/loop/spec-questions-<code>.md` described in step 4.
  - Conflicts and gaps go under **Spec questions** in `PROGRESS.md`. Take the most reasonable interpretation and
    proceed.
  - Generated artifacts the dev guide assigns to the build (for example an exported `openapi.json`) are allowed only at
    the paths the dev guide names.
- **Processes and paths.**
  - Never `pkill`, `killall`, or kill by name or pattern. Stop servers only with `make dev-down` or the PIDs in
    `.run/`.
  - Probe with `lsof -nP -iTCP:<port> -sTCP:LISTEN` before binding. Use only ports 8190 (API), 5270 (Vite), 8199 and
    5279 (e2e).
  - Never write to `/tmp`. Scratch files go in `.run/`.
  - Leave every server you started stopped at the end of the iteration.
  - Do not use browser MCP tools. Playwright runs only through `make e2e`.
- **PostgreSQL** (shared Homebrew PostgreSQL 17 on 127.0.0.1:5432).
  - Connect only through the `EREV_*` URLs in `.env`, to the databases `erev`, `erev_test` and `erev_e2e`, as
    `erev_owner` (migrations and test schema reset) or `erev_app` (everything else).
  - Never create, drop or alter databases or roles, and never change server settings.
  - Never connect as a superuser. Never touch `erev_rv_*` or any other project's database.
  - Never print credentials from `.env`.
- **Supervisor targets (D-48a) are never run by the loop:** `make audit-deps`, `make zap-baseline`,
  `make docker-build`, `make compose-verify`, `make tf-validate`, `make backup`. If an item needs one, implement the
  artifacts, validate them offline, and add the check under **Supervisor verification needed**.
- **Network and secrets.**
  - Tests never touch the network. AI runs only through the fake provider or a mocked SDK client.
  - Before writing Anthropic SDK code, read the `claude-api` skill documentation. If it is unavailable, code against
    the provider interface, test only with the fake, and record it under **Supervisor verification needed**.
  - No secrets in code. Do not read credential files outside this repository.
- **Honesty and completeness.**
  - Never tick an item you have not verified. Quote counts from a run made after your last change.
  - Never weaken, skip, xfail or delete a test to make a gate pass. Never edit expected values in
    `docs/accounting/answer-keys/`, `docs/legacy/golden/` or `deviations.json`. Fix the code, or record a **Spec
    question** if you believe an expected value is wrong, and do not tick the item.
  - No placeholder pages, "coming soon" copy or TODO stubs presented as features. Navigation lists only built routes.
- **Blocked.** Use `BLOCKED:` only for something that prevents *all* remaining items. Otherwise record the obstacle and
  continue with the next item that does not depend on it.

### Done

Print the done marker only when **all** of the following are true:
- every BUILD_SPEC item is ticked in `PROGRESS.md` with evidence;
- the final release item's evidence table covers `docs/00-GOAL.md` gates G1–G11, each with a command run on a clean
  tree after the last commit (`git status --porcelain` empty), or recorded under **Supervisor verification needed**
  where the gate allows it (Docker, Terraform);
- no **In flight** item remains.
