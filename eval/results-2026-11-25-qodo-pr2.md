# Eval results — 2026-11-25 (after the Qodo PR #2 fixes)

Run: `python -m local_rag.evaluate` from the repo root (sandbox, Python 3.12, `PYTHONPATH=src`). Generated from that run's functions; exit code 0.
Corpora: `sample_corpus/` (Harbor & Pine Law — fictional firm) and `sample_corpus_nonprofit/` (Bayside Community Pantry — **invented** nonprofit). Sample data only; nothing here is a real organisation.

## Part 1 — original 10 questions

| Metric | RAG only | Router |
|---|---|---|
| n_questions | 10 | 10 |
| answered_correctly | 7 | 7 |
| false_declines | 0 | 0 |
| declined_correctly | 3 | 3 |
| false_answers | 0 | 0 |
| mean_context_precision_at_1 | 1.0 | 1.0 |
| mean_context_precision_at_3 | 0.57 | 0.57 |
| mean_context_recall | 0.93 | 0.93 |
| citation_accuracy | 1.0 | 1.0 |
| decline_accuracy | 1.0 | 1.0 |
| verbatim_quote_check_answered | 1.0 | 1.0 |

| ID | Status | Path | Correct |
|---|---|---|---|
| Q1 | answered | section_lookup | True |
| Q2 | answered | section_lookup | True |
| Q3 | answered | section_lookup | True |
| Q4 | answered | rag | True |
| Q5 | answered | rag | True |
| Q6 | answered | section_lookup | True |
| Q7 | answered | rag | True |
| Q8 | declined | rag | True |
| Q9 | declined | rag | True |
| Q10 | declined | rag | True |

## Part 2 — extended eval (26 cases, 3 known limitations not gated)

- **n_cases**: 26
- **n_gated**: 23
- **n_known_limitations**: 3
- **correct**: 23
- **classification**: {'answered_answerable': 15, 'false_declines': 0, 'declined_unanswerable': 6, 'false_answers': 0}
- **path_choice_correct**: 13/13
- **citation_correct_answerable**: 15/15
- **multi_turn_correct**: 4/4
- **paths_used**: {'list_files': 2, 'phrase_lookup': 2, 'rag': 17, 'section_lookup': 5}
- **known_limitations_still_failing**: 3

| ID | Category | Status | Path | Correct | Question |
|---|---|---|---|---|---|
| N1 | path_choice | answered | list_files | True | What documents do you have? |
| N2 | path_choice | answered | section_lookup | True | What is the minimum age for volunteers? |
| N3 | citation | answered | rag | True | How old do you have to be to help out? |
| N4 | path_choice | answered | phrase_lookup | True | Which policy mentions "locked filing cabinet"? |
| N5 | answer_vs_decline | declined | rag | True | Do the documents mention "gluten-free"? |
| N6 | answer_vs_decline | declined | rag | True | What is the date of the next food distribution? |
| N7 | answer_vs_decline | declined | rag | True | Is there parking at the pantry? |
| N8 | answer_vs_decline | declined | rag | True | What is the pantry's annual budget? |
| N9 | path_choice | answered | section_lookup | True | Who approves new AI tools? |
| N10 | citation | answered | rag | True | Can staff paste client names into ChatGPT? |
| N11 | path_choice | answered | section_lookup | True | How do I get a receipt for my donation? |
| N12 | path_choice | answered | rag | True | How long are household records kept? |
| N13 | citation | answered | rag | True | When is fresh produce accepted? |
| N14 | citation | answered | rag | True | Does the pantry share names with partner food banks? |
| M1 | multi_turn | answered | rag | True | And how often can they come back? |
| M2 | multi_turn | declined | rag | True | And how often can they come back? |
| M3 | multi_turn | answered | section_lookup | True | What does it cover? |
| M4 | multi_turn | declined | rag | True | Who was on it? |
| L1 | path_choice | answered | section_lookup | True | What documents are needed for an uncontested divorce intake? |
| L2 | path_choice | answered | list_files | True | List the documents |
| R1 | regression | answered | rag | True | What is the deadline for the flat fee? |
| R2 | regression | answered | rag | True | What's the client's fee? |
| R3 | regression | answered | phrase_lookup | True | Which policy mentions 'locked filing cabinet'? |
| K1 | known_limitation | declined | rag | known-fail | Can I donate a homemade lasagna? |
| K2 | known_limitation | answered | rag | known-fail | What is the executive director's salary? |
| K3 | known_limitation | answered | rag | known-fail | What is the deadline for the flat fee? |

## Part 3 — review queue tasks: 9/9

- OK — suspend holds the answer (pending, nothing released)
- OK — suspend keeps citations and route
- OK — declined draft is queued as declined
- OK — queue survives a restart (read by a new process)
- OK — approve releases the draft unchanged
- OK — edit-then-approve releases the reviewer's text, marked edited
- OK — reject never releases
- OK — nothing left pending
- OK — a decided item cannot be decided again

## Part 4 — direct checks for the Qodo PR #2 fixes: 8/8

- OK — apostrophes are not read as a quoted phrase (finding 8)
- OK — real double and single quotes still give a phrase (finding 8)
- OK — mismatched source/section citations fail the paired check (finding 7)
- OK — refusal sentence in the second cited chunk declines (finding 9)
- OK — document listing titles are inside their cited evidence (finding 3)
- OK — empty and headings-only corpora raise a corpus error (finding 4)
- OK — rag-only ignores --previous for a self-contained question (finding 5)
- OK — rag-only still expands a real follow-up (finding 5)
