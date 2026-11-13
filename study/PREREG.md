# Kill test D-249: how often does a merged agent pull request need its old tests changed to pass?

Written 2026-11-13 before any dataset row was read. Changes after this point go in a
"Deviations" section of `RESULT.md`, never by editing this file.

## Question

Among merged, agent-authored pull requests that modify, delete or rename a test file that
already existed, in what fraction does the old version of at least one such test fail on the
merged code while passing on the base code (testward verdict "needs sign-off")?

## Hypothesis and what would falsify it

H1: the fraction is at least 1 in 100.
H2: of the pull requests that need sign-off, fewer than half are plain intended behaviour
changes (the pull request says it changes that behaviour and the test edit follows from it).

The product is killed if either fails:

- H1 fails if the point estimate is under 1% **and** the sample is large enough that the upper
  end of the 95% Wilson interval is under 3%. If the estimate is under 1% but the interval is
  wider than that, the result is "not shown", reported as such, and the product stays unbuilt
  until a larger run.
- H2 fails if half or more of the flagged pull requests are labelled "intended".

A third outcome is fixed in advance: if fewer than 40% of sampled pull requests give a
conclusive replay (held or needs sign-off), the headline is "the harness cannot measure this"
and no rate is claimed.

## Prior work and the gap

- AIDev dataset (hao-li/AIDev on Hugging Face, CC BY 4.0): agent-authored pull requests.
- arXiv 2607.18057, test coverage of agentic pull requests on AIDev: reports deleted versus
  added tests, does not execute old tests against new code.
- flake-laundering (zaidwhy, DOI 10.5281/zenodo.23721575): 0 of 60 weakened tests under a plain
  brief, one agent, synthetic race bugs, lab setting.
- ImpossibleBench and EvilGenie (cited in flake-laundering's RESULT.md): agents cheating on
  tasks built to be impossible.

Gap: nobody has replayed base tests against merged agent code in real repositories.

## Design

- Population: AIDev pull requests with a merge timestamp, in repositories whose main language
  is Python, where at least one file matching testward's default test globs has status
  modified, removed or renamed.
- Sample: simple random, seed 20261113, 300 pull requests, at most 3 per repository so one
  project cannot dominate. 300 because zero hits in 300 puts the 95% upper bound near 1.2%.
- Measured per pull request: testward verdict per changed test file, with base = the pull
  request's base commit and head = its merge result. A pull request "needs sign-off" if any
  file does.
- Test command: `python -m pytest {file} -x -q -p no:cacheprovider`, timeout 300 s per file.
  Environment: fresh virtualenv, `pip install -e .` with the repository's test extras when
  declared, else `requirements*.txt`; 15 minute budget per pull request. No per-repository
  hand tuning; a repository that does not install is counted as not conclusive.
- Built-in control: every failing replay is re-run against the base code. A test that fails
  there too is "inconclusive", never "needs sign-off".
- Floor control: in each repository where the environment installs, one synthetic change that
  only appends a comment to the same test files is replayed. It must give zero "needs
  sign-off". Any hit means the harness is wrong and the run is void.
- Comparison group, if the dataset carries one: the same procedure on human-authored pull
  requests from the same repositories. If it does not, this is stated as a limitation.
- Labelling of each flagged pull request, from its title, description and diff, by one rater:
  **intended** (description states the behaviour change the old test contradicts),
  **laundered** (description claims a fix or no behaviour change, and the old test encodes
  behaviour the description does not mention changing), **unclear**.
- Replication before any headline: a second sample of 150 with a different seed
  (20261114). JavaScript/TypeScript is a separate study, not part of this one.

## Confounds

| Confound | Handling |
|---|---|
| Merged pull requests were reviewed by people, so laundering that reviewers caught is missing | Accepted and stated. This measures what survives review, which is what a gate would add to |
| Repositories that install without tuning are simpler than the rest | Measured: yield reported by repository size; accepted |
| Flaky tests | Controlled by the base-code run; each flagged file is replayed twice more |
| Squash merges change the head commit | Head is the merge commit recorded by GitHub, checked to exist |
| Old test imports a helper the change renamed | Counted as needs sign-off by design; labelled in the reading pass |
| One rater | Accepted and stated; labels and evidence are published per pull request |
| Dataset era and agent mix | Reported per agent; one dataset only |

## Safety

Running a repository's tests executes its code. Nothing from the sample runs on a machine
that holds credentials. Execution happens in disposable hosted CI runners with no secrets.
