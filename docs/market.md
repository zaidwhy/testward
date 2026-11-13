# Is this worth building? Evidence, rivals, price, kill test

Written 2026-11-13 from one afternoon of desk research. No customer was interviewed. Nothing
below is a user quote unless it links to where the person wrote it.

## The problem as stated

A coding agent is asked to make CI green. It can fix the code or loosen the test. Both produce
a green build, and the reviewer sees a diff that touches code and tests together.

## Evidence that it happens and that people care

| Evidence | Source | Weight |
|---|---|---|
| "the agent makes a failing test pass by loosening it instead of fixing the code"; a reply reports "The build stayed green for days until users hit silent null-pointer crashes" | [Product Hunt thread][ph], 6 replies, 62 views | Real people, tiny sample |
| In agent pull requests that did not improve coverage (Java), agents deleted 82 tests and added 31 | [arXiv 2607.18057][arxiv], 4,882 agent PRs from the AIDev dataset | Measured, but deletion is not proof of laundering |
| 96% of developers do not fully trust AI-written code; over a third say reviewing it takes more effort than a colleague's code | [Sonar 2026 survey][sonar], 1,100+ developers | Large, but Sonar sells verification tools ([The Register][reg] makes the same caveat) |
| Top concern: reviewing and validating AI-written code at scale (47.7%) | [Qodo 2026 report][qodo] | Vendor survey |
| Repliers in the thread name only manual habits and CODEOWNERS as their fix | [Product Hunt thread][ph] | Suggests no tool has become the default |

## Evidence against

- **Zaid's own measurement.** In [flake-laundering][study] (229 Claude Code runs), a plain "get
  CI green" brief weakened a correct test in 0 of 60 runs, and 0 of 30 when the bug was harder
  to see. With a current frontier model the event is rare. Older or cheaper models, other
  agents and longer tasks were not measured.
- **Rivals have no traction.** Three tools already aim at this and none has an audience (table
  below). That pattern has meant "builders without users" in every earlier search in
  `projects/startup-discovery`.
- **No visible spend.** No paid product was found whose main job is this check. Money in the
  neighbourhood goes to broad AI code review and to flaky-test tooling.
- A search of the Claude Code and Codex issue trackers for complaints about weakened or
  falsely passing tests, sorted by reactions, returned no issue on this topic near the top.

Net: the failure is real and costly when it happens, its frequency is unknown and possibly
low, and willingness to pay is unproven.

## Rivals

Star counts read from the GitHub API on 2026-11-13.

| Tool | What it does | Stars | Where it is weak |
|---|---|---|---|
| [TestSeal][testseal] | Static rules on Python/pytest diffs (removed assertions, weaker comparisons, new skips). States that it never executes the repository | 8 | Python only. Cannot tell a harmless rewrite from a weakening, because it never runs anything |
| [Swarm Orchestrator][swarm] | CLI with eight default diff checks, TypeScript and JavaScript | 114 | Its author reports about 3.4 findings on a clean pull request and says the structural checks "throw too many false positives to trust as automatic blockers" |
| ai-pr-confidence | 0 to 100 score for an AI-written pull request | 0 | A score, not a decision |
| CodeRabbit and other AI reviewers | A model comments on the whole diff | paid, widely used | Probabilistic; may or may not mention the test edit; no gate |
| CODEOWNERS on test paths | Forces a human review of test changes | built in | Tells the reviewer to look, not what to look at |

The gap testward takes: decide by execution. Nobody found in this search replays base tests
against head code. That absence is weak evidence of an opening and equally consistent with the
idea not being wanted.

## Who would use it

Hypothesis, not finding: teams of 3 to 30 engineers that merge agent-written pull requests
daily and already require green CI before merge. The buyer is whoever owns the CI
configuration. Solo developers get the CLI and Action free and are not the paying customer.

## Product strategy

- Free and open: the CLI and the Action. They are the whole check and work with no account.
- Paid: the hosted sign-off ledger, because sign-offs have to live outside the repository and
  a team does not want to run a server for that.
- Not building: an AI reviewer, coverage, flaky-test tracking. Each is a funded category.
- Next, only if the kill test passes: a GitHub App so sign-off is a button on the pull
  request and the check re-runs itself; team accounts; per-case replay for pytest and Jest.

## Price and unit economics

Reference prices, from secondary pricing pages read on 2026-11-13 and not from the vendors'
own pages:

| Product | Price | Source |
|---|---|---|
| CodeRabbit | $24, $48, $72 per developer per month, billed annually | [activepieces summary][cr] |
| Codecov | about $5 per user per month (Team), $12 (Pro); sources disagree | Capterra and similar listings |
| Trunk Flaky Tests | per committer, usage based, no public seat price; free up to 5 committers | [trunk.io/pricing][trunk] |

testward does one narrow check, so it cannot charge like a reviewer. Planned price: **a flat
$19 per organisation per month**, free for public repositories and during early access. Flat,
because a per-seat price on a single CI check invites the question of which seats count.
Billing is not built; nothing is charged today.

Unit economics, with every assumption marked:

- The check runs on the customer's CI minutes. Server cost per report is one small JSON row.
- Fixed cost: one small always-on container with a volume. Assumed $10 a month; read the
  host's current price before launch.
- Card fees: assumed 2.9% + $0.30 per charge, about $0.85 on $19.
- Contribution per paying organisation: about $18 a month. Fixed hosting is covered by the
  first one.
- Unknown and decisive: cost to acquire a customer, and churn. There is no data for either.
  At $19 a month this only works if customers arrive through the free Action without sales
  effort.
- Storage bound per project today: 500 reports of at most 512 KB, so 256 MB worst case;
  typical reports are a few KB.

## The kill test

Two checks, in this order, before any more building.

1. **Prevalence, two evenings, no outreach.** Run `testward replay` over merged agent-authored
   pull requests that edit existing tests, sampled from the public AIDev dataset used in
   [the coverage paper][arxiv]. Count how many get "needs sign-off" and read each one. Kill
   the product if fewer than 1 in 100 test-editing pull requests need sign-off, or if most
   that do are intended behaviour changes. Either way the count is a publishable follow-up to
   flake-laundering.
2. **Pull, two weeks.** Publish the Action, reply in the Product Hunt thread and to the
   authors of the incident write-ups with the prevalence numbers. Kill the hosted product if
   fewer than 3 repositories that Zaid does not own add the workflow within 14 days.

[ph]: https://www.producthunt.com/p/vibecoding/how-do-you-stop-ai-coding-agents-from-weakening-tests-to-make-them-pass
[arxiv]: https://arxiv.org/abs/2607.18057
[sonar]: https://www.sonarsource.com/blog/state-of-code-developer-survey-report-the-current-reality-of-ai-coding/
[reg]: https://www.theregister.com/2026/01/09/devs_ai_code/
[qodo]: https://www.qodo.ai/?p=22120
[study]: https://github.com/zaidwhy/flake-laundering
[testseal]: https://github.com/satwiksps/testseal
[swarm]: https://dev.to/moonrunnerkc/catching-the-shortcuts-ai-coding-agents-take-to-look-done-45mm
[cr]: https://www.activepieces.com/blog/coderabbit-pricing-2026-plans-costs-and-limits
[trunk]: https://trunk.io/pricing
