# Exploratory testing charters

Scripted cases check what the requirements say. These sessions look for what
they do not say. Each charter is a time-boxed session (session-based test
management): one mission, notes taken while testing, and a short debrief.

**Tools:** Postman (import `postman/commission-engine.postman_collection.json` to
get working examples) and Swagger UI at `http://localhost:8000/docs`.

**Setup for every session:** start the API on a fresh database
(`python scripts/reset_db.py sqlite:///./explore.db`, then
`DATABASE_URL=sqlite:///./explore.db uvicorn app.main:app`) and record the
build from `GET /health`.

Write each session report in `docs/exploratory/` using the template at the end.
File any defect in Jira and in `bugs/`, and add a scripted test case for
anything worth keeping in the regression suite.

## CH-01 Money and date inputs (45 min)

**Mission:** explore how the API interprets amounts and dates that a real client
or a spreadsheet export could send, to discover inputs that are accepted with a
different meaning than intended.

**Ideas:** thousands separators (`"1,500.00"`), spaces (`" 1500 "`), scientific
notation (`1.5e3`), trailing zeros (`"100.000"`), `null`, `true`, very large or
tiny values, numbers as strings in quotas, dates with time or time zone
(`2026-10-15T23:30:00-06:00`), `2026-02-30`, leap years.

**Look at:** the stored value (`GET /transactions/{id}`), the credit lines, the
statement. Is anything silently rounded or reinterpreted?

## CH-02 A quarter in the life of one seller (45 min)

**Mission:** explore sequences across periods for one seller, to discover
statements that do not add up after returns, deactivation and closes.

**Ideas:** a split sale in October, a partial return in November inside the
window, a second partial return outside the window, deactivate the second
seller, close October, try to return again, close November, compare every
statement with a hand calculation. Try the same sequence in a different order.

**Look at:** net credited per period, attainment, which statement shows the
clawback, what an INACTIVE seller sees.

## CH-03 Fixing a rejected import (30 min)

**Mission:** act as an operator whose 2,000-row import was rejected, and explore
whether the error response alone lets them find and fix every bad row.

**Ideas:** mix schema errors and business errors in one batch, several errors in
the same row, a return whose sale failed earlier in the batch, an empty batch,
the 5,000-row limit.

**Look at:** are row numbers 0-based or 1-based and is that obvious? Does the
message say what to change? How many round trips does it take to get a clean
import?

## Session report template

```markdown
# Session report: CH-0X <title>

| | |
|---|---|
| Tester | |
| Date and start time | |
| Duration | (planned / actual) |
| Build | (from GET /health) |
| Charter vs opportunity | (% of the time on the mission / % on side paths) |

## What I tested
Short notes, in the order things happened.

## Bugs
| ID | Summary | Severity |
|---|---|---|

## Issues and questions
Things that are not bugs yet: unclear requirements, surprising behaviour.

## New scripted test cases proposed
| Proposed ID | Title | Requirement |
|---|---|---|
```
