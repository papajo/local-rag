# Backlog

Two lists, one file (the "two backlogs" idea from Matt Wynne's software
factory talk, Modern Software Engineering, 2026-11-25):

- **Product backlog**: what local-rag itself should do better.
- **Kaizen backlog**: what the way we build and check it should do
  better: tests, reviews, docs, process.

Work alternates between the two. Ship a product fix, then look at what
went wrong while doing it, and add or fix a Kaizen item.

## The loop (rules)

1. **Spec first.** A new bug or wish gets a scenario in `features/` that
   says, in plain English, what should happen. If it isn't being fixed
   now, tag it `@known-failure` and add a product item below.
2. **Fix, then untag.** When the fix lands, the run prints
   `KNOWN-NOW-OK`: remove the tag and close the item here.
3. **Every miss is a Kaizen item.** A bug that got past review, a wrong
   status in a doc, a check that didn't run: write down what would have
   caught it.
4. **The specs are the contract.** The human owner reads every word of
   `features/*.feature`. The code under them can change freely as long as
   `local-rag eval` exits 0.

Status: `open` · `doing` · `done (date)` · `dropped (why)`

## Product backlog

| ID | What's wrong | Guarded by | Likely fix | Status |
|---|---|---|---|---|
| P1 | A synonym the documents don't use ("homemade" vs "home-cooked") is declined though the answer is there (false decline) | `features/06` K1 | Embeddings (the SIE swap), not threshold tuning | open |
| P2 | A question that shares a name with an unrelated passage ("executive director's salary") gets that passage quoted (false answer) | `features/06` K2 | Embeddings | open |
| P3 | "What is the deadline for the flat fee?" still quotes "What the flat fee covers" first via RAG fallback | `features/06` K3, `features/05` R1 | Stronger relevance signal (embeddings). A literal "passage must mention the deadline" rule was tried and dropped: it wrongly declined "How much does document review cost?" | open |
| P4 | `ask` reads Markdown folders only; it does not read the LanceDB index built by `ingest` (Qodo PR #1, finding 2) | none yet: needs a spec once decided | Decide: point `ask` at LanceDB, or document Markdown-only as the design | open (decision) |
| P5 | Review queue has no cross-process lock (Qodo PR #2, finding 2) | none | File lock around queue writes | open (low risk) |
| P6 | RAG fallback runs the hybrid search twice (Qodo PR #2, finding 6) | none | Reuse the first result; performance only | open (low risk) |
| P7 | Default review-queue path for a wheel install points inside the package (Qodo PR #2, finding 10) | none | Default to a user data folder; `--queue` / `$LOCAL_RAG_REVIEW_QUEUE` work today | open |
| P8 | Follow-ups remember one turn only | `features/04` M1 to M4 | Only if a real user needs more | open (by design) |

## Kaizen backlog

| ID | What went wrong / what's missing | What would catch it | Status |
|---|---|---|---|
| Z1 | Eval cases were JSON only. A non-programmer couldn't read what the assistant is promised to do | Plain-English Gherkin specs in `features/`, run as Part 5 of `local-rag eval`, plus a check that every eval case id has a spec | done (2026-11-26) |
| Z2 | PR #2 was merged about a minute after it opened, before Qodo's review landed, so main carried two wrong answers | Branch protection on `main`: require a review and passing checks before merge (repo Settings → Branches) | open (owner's setting) |
| Z3 | Nothing runs the eval on a pull request; it only runs when someone remembers | A GitHub Action that runs `python -m local_rag.evaluate` on every PR and blocks on a non-zero exit | open |
| Z4 | `docs/p1-rag-upgrade.md` and `docs/p1-demo-script.md` predate the router, review queue and specs | Update them; add "docs touched?" to the PR checklist | open |
| Z5 | Test cases live in two places (`eval/*.json` and `features/`) | Parity check (done) keeps ids aligned. Next: generate one from the other, or make `features/` the single source | open |
| Z6 | K1 to K3 can't move until the TF-IDF stand-in is swapped for embeddings | One decision: when to do the SIE swap. Then re-run and untag whatever passes | open (decision) |

## Done log

- 2026-11-26 Z1: `features/` (6 files, 35 scenarios covering all 36 eval
  cases), `src/local_rag/specs.py` (stdlib runner, no new dependency),
  Part 5 in `local-rag eval`. Checked that the runner catches a wrong
  route, a missing spec, an unknown step, a router that always declines,
  and altered quotes.
