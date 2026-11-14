# Result: old tests fail on merged agent code in a third of test-editing pull requests, and almost every time that is the point of the change

Run 2026-11-13. Plan: [`PREREG.md`](PREREG.md), written before any data was read. Changes to
the plan: [`DEVIATIONS.md`](DEVIATIONS.md).

## Finding

1. **The event is common.** Among merged agent-authored pull requests in Python repositories
   that edit a test file which already existed, the base-branch version of at least one such
   test fails on the merged code (and passes on the base code) in **62 of 170** conclusive
   replays: 36.5%, 95% CI 29.6 to 43.9%.
2. **It is rarely a problem.** Reading all 62: **59 intended** behaviour changes
   (renames, API changes, removed features, version bumps, new required arguments) and **3
   real undisclosed regressions**. The first pass left 3 unclear and found 1 real case; a
   second rater then disagreed on 8 more, and all 11 were traced through repository history
   (below and "Second rater"). (Revised 2026-11-14; the 2026-11-13 version said 61 and 1.)
3. **No real case is an agent weakening a test to hide its own failure.** Two are merge
   accidents: a stale agent branch merged over work landed hours earlier, silently removing it
   with the tests edited to match (sshpilot#418, robotocore#97). The third (agentflow#1)
   replaced a bridge module and dropped its read-only tool enforcement without saying so; the
   maintainers found it seven months later (issue #47) and fixed it (#49).
4. **So the gate is killed.** `testward` as a merge gate would ask for a human sign-off on
   about one in three honest test-editing pull requests to surface 3 real problems in 62
   flags (4.8%, CI 1.7 to 13.3%), which is 3 in 170 conclusive replays (1.8%, CI 0.6 to 5.1%).
   H1 held; H2 failed (95.2% intended, CI 86.7 to 98.3%, against a bar of under 50%).

## Numbers

| | Sample A (seed 20261113) | Sample B (seed 20261114) | Pooled |
|---|---|---|---|
| Pull requests sampled | 300 | 147 | 447 |
| No existing test changed at replay | 39 | 23 | 62 |
| Excluded: merge commit is not the pull request diff | 14 | 9 | 23 |
| Replays attempted | 247 | 115 | 362 |
| Conclusive (held or needs sign-off) | 120 (48.6%) | 50 (43.5%) | 170 (47.0%) |
| **Needs sign-off** | **45 (37.5%, CI 29.4 to 46.4)** | **17 (34.0%, CI 22.4 to 47.8)** | **62 (36.5%, CI 29.6 to 43.9)** |
| Floor control: comment-only change flagged | 0 of 245 | 0 of 118 | 0 of 363 |
| Label: intended (first pass) | 44 | 15 | 59 |
| Label: unclear (first pass) | 1 | 2 | 3 |
| Label: intended (after tracing the 3 unclear) | 45 | 16 | 61 |
| Label: meets the "laundered" rubric (after tracing) | 0 | 1 | 1 |

Sample A without the 30 pilot rows that were seen before the setup changes: 39 of 106, 36.8%
(CI 28.2 to 46.3). The replication sample was drawn with a different seed and run once.

Population the samples come from: 43,174 merged agent pull requests in Python repositories in
`pull_request.parquet`; 13,387 of them (31%) edit a test file that already existed, across
1,504 repositories.

Needs sign-off over conclusive, by agent, pooled: Claude Code 40 of 89, Copilot 13 of 32,
OpenAI Codex 8 of 42, Cursor 1 of 4, Jules 0 of 2, Devin 0 of 1. The study was not designed to
compare agents and these are not adjusted for repository or task.

## The three cases the first pass could not settle

Each was traced afterwards through commits and file history on GitHub (reading only).

| Pull request | First-pass doubt | What the history shows | Label |
|---|---|---|---|
| [PrimeIntellect-ai/verifiers#974](https://github.com/PrimeIntellect-ai/verifiers/pull/974) | Deletes `test_env_crash_recovery.py`; the old `test_retry_after_recovery` fails with `assert 3 == 2` | The old test counts every socket send. The change adds a cancel-signal send, as its description says, so the count is 3. The same test was carried into `test_env_server.py` and still asserts 2 attempts | intended |
| [boringdata/boring-semantic-layer#146](https://github.com/boringdata/boring-semantic-layer/pull/146) | A lazy-import fix also changes assertions from `fastmcp` to `mcp`, unmentioned | The old error message told users to install a `[fastmcp]` extra that `pyproject.toml` never declared. The change corrects it to `[mcp]`, which exists. The old test pinned the wrong text | intended |
| [mfat/sshpilot#418](https://github.com/mfat/sshpilot/pull/418) | A drag-and-drop change deletes `test_open_remote_path_none_defaults` | The `~` default and this test were added on `dev` in `769d7cdc`. The agent branch predated them. Merge commit `e56cba26`, 46 minutes later, kept the stale side, so merging the pull request removed the fix and its test. Commit `28db6b6a`, four hours later, redoes the fix by hand; the test did not come back | real regression |

The sshpilot case meets the pre-registered "laundered" rubric (behaviour changed, test
removed, description silent), but nobody edited a test to hide a failure: it is a lost change
from merging a stale branch. It is the kind of thing the replay exists to catch, and it is the
only one in 62.

## Controls

- **Built in:** every failing replay was re-run on the base code; a test failing there too is
  inconclusive, not flagged.
- **Floor:** in each repository, a change that only appended a comment to the same test files
  was replayed. 0 of 363 were flagged, so the harness does not blame a no-op edit.
- **Stability:** each flagged pull request was replayed twice more. Two in sample A did not
  repeat and are counted as "unstable", not as needing sign-off.

## Objections tested

- *The rate is an artefact of the pilot-informed setup.* Without pilot rows the rate is 36.8%.
- *One seed.* The second seed gives 34.0%, inside the first interval.
- *Easy repositories only.* Conclusive yield was 68 of 141 for repositories with 100 to 1,000
  stars and 52 of 106 above 1,000; flagged rates 35% and 40% (sample A).

## Second rater (added 2026-11-14)

Zaid labelled all 62 flagged pull requests independently on the labelling page
(`label_server.py`, which never reads the first rater's labels). Output of `study/agreement.py`
is in `results/agreement-zaid.txt`; his labels are in `results/labels-zaid.jsonl`.

| | intended | laundered | unclear |
|---|---|---|---|
| First rater, final | 61 | 1 | 0 |
| Second rater | 53 | 5 | 4 |

- Raw agreement with the final labels is 54 of 62 (87.1%), Cohen's kappa 0.18. Kappa is low
  because almost every pull request is "intended", so chance agreement is already high; the
  disagreements are what matter.
- Both raters call sshpilot#418 laundered. The second rater also calls four more laundered
  (pal-mcp-server#95, tsam#176, agentflow#1, xorq#1752) and four unclear (robotocore#97,
  pytensor#1574, pal-mcp-server#51, shotgun#161). The first rater read all eight as intended
  refactors or renames. These eight have not been traced through repository history the way
  the first pass's three unclear cases were.
- **Traced (2026-11-14), read-only through each repository's pull request, diff, later commits
  and issues; no code run.** Two of the eight are real regressions:
  - agentflow#1 (second rater: laundered): the Kimi bridge it replaced enforced read-only
    tools; the new adapter runs the CLI with `--yolo` and ignores the setting, and the body
    does not mention it. Issue shouc/agentflow#47 (2026-10-31) reported it; #49 fixed it.
  - robotocore#97 (second rater: unclear): the merge commit removes 260 lines of
    `gateway/app.py`, including the health endpoint's services filter and versioned
    snapshots merged about two hours earlier; the description covers only the boot
    orchestrator, and the features were not restored.
  - The other six are intended: tsam#176 (`feat!` rename with deprecation shims and a
    compatibility test), xorq#1752 (rename stated in the summary), pytensor#1574 (title and
    linked issue describe the change), pal-mcp-server#51 (class rename only), shotgun#161
    (change stated in the squash commit). pal-mcp-server#95 is borderline: the schema change is
    the point of the rewrite, but its body also says "No breaking changes" and two tests were
    replaced by skips. Counting it would make 4 of 62.
- Real problems after tracing: 3 of 62 (sshpilot#418, robotocore#97, agentflow#1).
- **The kill decision does not change.** H2 fails if half or more of the flagged pull requests
  are intended. On the second rater's labels 53 of 62 are intended (85.5%), still far above
  the bar, so the gate is still killed under either rater.

## Limitations

- **Half the replays were inconclusive** (192 of 362), 77 of the 121 in sample A because a
  dependency did not import. Repositories that install with a generic recipe may differ from
  those that do not.
- **Merged pull requests only.** Laundering that a reviewer caught before merge is absent.
  This measures what survives review.
- **Second rater disagrees on 8 of 62** (section above). 59 first-rater labels come from a single pass over the title, about 1,200 characters
  of description and the test diff. Only the 3 first-pass unclear cases were traced through
  history; the 59 "intended" ones were not, and a lost change like the sshpilot one could be
  hiding among them wherever a description happens to sound complete. The labels, first-pass
  labels and reasons are in `results/labels-*.jsonl` for anyone to contest.
- **Per file.** A file is flagged if any old case fails; the count of failing cases was not
  measured.
- **Python and pytest only, one dataset.** The per-commit file status in the dataset was used
  to find candidates; 62 of 447 turned out to have no existing test changed.
- Three pull requests were drawn in both samples and counted once.

## What this does not show

- That agents never weaken tests. It shows no deliberate weakening among 62 flagged merged
  pull requests and three undisclosed losses: two from stale-branch merges, one a dropped
  safety check.
- Anything about pull requests that were not merged, about languages other than Python, or
  about whether agents differ from human authors: there is no human comparison group.
- That the replay is useless. It reliably answers "did this change alter behaviour that an
  existing test pinned down", and the three unclear cases are exactly the ones a reviewer
  would want pointed out. It did point at all three real regressions. It is information for a
  reviewer, not a gate.

## Reproduce

```bash
# metadata only; needs gh and uv
cd study
uv run --with duckdb python funnel.py                       # writes candidates.parquet
uv run --with duckdb python sample.py 20261113 300 sample-a.jsonl
uv run --with duckdb python sample.py 20261114 150 sample-b.jsonl
bash selftest.sh /tmp/testward-selftest                     # harness check, no outside code

# execution: on GitHub Actions only, it runs the sampled repositories' code
gh workflow run study.yml -f sample=sample-a.jsonl          # run 43416236854
gh workflow run study.yml -f sample=sample-b.jsonl          # run 43423488010
# download the artifacts, concatenate out-*.jsonl, then:
python analyze.py results/sample-a.jsonl
```

Raw rows, flagged lists, rater dossiers and labels are in [`results/`](results/). Total hosted
runner time for both samples: about 773 minutes.

Data: AIDev (hao-li/AIDev on Hugging Face, CC BY 4.0).
