# Result: old tests fail on merged agent code in a third of test-editing pull requests, and almost every time that is the point of the change

Run 2026-11-13. Plan: [`PREREG.md`](PREREG.md), written before any data was read. Changes to
the plan: [`DEVIATIONS.md`](DEVIATIONS.md).

## Finding

1. **The event is common.** Among merged agent-authored pull requests in Python repositories
   that edit a test file which already existed, the base-branch version of at least one such
   test fails on the merged code (and passes on the base code) in **62 of 170** conclusive
   replays: 36.5%, 95% CI 29.6 to 43.9%.
2. **It is almost never laundering.** Reading all 62: **59 intended** behaviour changes
   (renames, API changes, removed features, version bumps, new required arguments), **3
   unclear**, **0 laundered**. The 95% upper bound on laundering among flagged pull requests
   is 5.8%.
3. **So the gate is killed.** `testward` as a merge gate would ask for a human sign-off on
   about one in three honest test-editing pull requests to surface about one questionable
   case in sixty. H1 held; H2 failed (95.2% intended, CI 86.7 to 98.3%, against a bar of
   under 50%).

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
| Label: intended | 44 | 15 | 59 |
| Label: unclear | 1 | 2 | 3 |
| Label: laundered | 0 | 0 | 0 |

Sample A without the 30 pilot rows that were seen before the setup changes: 39 of 106, 36.8%
(CI 28.2 to 46.3). The replication sample was drawn with a different seed and run once.

Population the samples come from: 43,174 merged agent pull requests in Python repositories in
`pull_request.parquet`; 13,387 of them (31%) edit a test file that already existed, across
1,504 repositories.

Needs sign-off over conclusive, by agent, pooled: Claude Code 40 of 89, Copilot 13 of 32,
OpenAI Codex 8 of 42, Cursor 1 of 4, Jules 0 of 2, Devin 0 of 1. The study was not designed to
compare agents and these are not adjusted for repository or task.

## The three unclear cases

| Pull request | Why it is not plainly intended |
|---|---|
| [PrimeIntellect-ai/verifiers#974](https://github.com/PrimeIntellect-ai/verifiers/pull/974) | Deletes `test_env_crash_recovery.py` "for consolidation". The old `test_retry_after_recovery` fails on the new code (`assert 3 == 2`), and the description does not say retry behaviour changed |
| [mfat/sshpilot#418](https://github.com/mfat/sshpilot/pull/418) | A drag-and-drop change deletes `test_open_remote_path_none_defaults`; the description does not mention that behaviour |
| [boringdata/boring-semantic-layer#146](https://github.com/boringdata/boring-semantic-layer/pull/146) | A lazy-import fix also changes dependency-group assertions from `fastmcp` to `mcp`, unmentioned in the summary |

Unclear means the description does not account for the failing old test. None was
investigated further, and none is claimed to be a defect.

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

## Limitations

- **Half the replays were inconclusive** (192 of 362), 77 of the 121 in sample A because a
  dependency did not import. Repositories that install with a generic recipe may differ from
  those that do not.
- **Merged pull requests only.** Laundering that a reviewer caught before merge is absent.
  This measures what survives review.
- **One rater, one pass,** from the title, about 1,200 characters of description and the test
  diff. The labels and reasons are in `results/labels-*.jsonl` for anyone to contest.
- **Per file.** A file is flagged if any old case fails; the count of failing cases was not
  measured.
- **Python and pytest only, one dataset.** The per-commit file status in the dataset was used
  to find candidates; 62 of 447 turned out to have no existing test changed.
- Three pull requests were drawn in both samples and counted once.

## What this does not show

- That agents never weaken tests. It shows none was found among 62 flagged merged pull
  requests, with an upper bound near 6% of flagged, which is about 2% of test-editing pull
  requests.
- Anything about pull requests that were not merged, about languages other than Python, or
  about whether agents differ from human authors: there is no human comparison group.
- That the replay is useless. It reliably answers "did this change alter behaviour that an
  existing test pinned down", and the three unclear cases are exactly the ones a reviewer
  would want pointed out. It is information for a reviewer, not a gate.

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
