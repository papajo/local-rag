# Demo script — Firm Knowledge Assistant (2–3 minutes)

Record the screen + voiceover. No face on camera needed. Say "sample
data" out loud once. Do not name a real firm or client.

## Setup (before recording)

```bash
cd local-rag   # repo root
uv run local-rag eval   # must exit 0; shows the 10/10 table
```

## Take 1 — the good answer (about 60 seconds)

Say: "This is a small law firm's own documents — sample data only.
I ask it what documents are needed for an uncontested divorce intake."

Run:

```bash
uv run local-rag ask "What documents are needed for an uncontested divorce intake?"
```

Point at the screen: the answer is the 5-item list — marriage
certificate, financial affidavit, property list, parenting plan,
intake form — and every line carries its citation:
`01-intake-checklist.md (chunk 0)`. Say: "The answer is not generated
from thin air. It is a passage from the firm's own document, with the
source on it."

## Take 2 — the decline (about 45 seconds)

Say: "Now the test that matters more. I ask it something the documents
do not contain."

Run:

```bash
uv run local-rag ask "When did someone last go to the moon?"
```

Point at `[DECLINED]`. Say: "It declines instead of guessing. A system
that invents an answer is worse than no system for a law firm."

## Take 3 — the decline with evidence (about 60 seconds, the selling point)

Say: "And the hard one — a deadline for a specific case."

Run:

```bash
uv run local-rag ask "What is the deadline for my specific case filed last Tuesday?"
```

Point at the decline *and* the quoted sentence: "It does not state the
deadline for any specific client's case." Say: "It refuses to invent a
deadline, and it shows you the sentence that says why. That is the
guardrail. That is what the $750 pilot installs on a firm's own
documents, local-only, with this same evaluation table."

## Close (15 seconds)

Say: "Three questions, three correct behaviours: a cited answer, a
clean decline, and a decline with its reason. The evaluation table is
in the repo — 10 out of 10, 7 answered, 3 declined, no invented answers."

## Watch-once checklist before publishing

- [ ] "Sample data" said out loud and visible on screen.
- [ ] No real firm name, client name, or phone number anywhere.
- [ ] Q1 shows the 5-item list with its citation.
- [ ] Q8 shows `[DECLINED]`, Q10 shows the decline with the policy sentence.
- [ ] No hiring claim, no "$1.2M", no invented result quoted.
