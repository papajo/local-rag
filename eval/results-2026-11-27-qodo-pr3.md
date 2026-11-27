# Eval results — 2026-11-27, after Qodo PR #3 fixes

Command: `python -m local_rag.evaluate` (exit 0). Latencies are machine-dependent.

```

Part 1 — original 10 questions (router: tools first, RAG fallback)
  n_questions: 10
  answered_correctly: 7
  false_declines: 0
  declined_correctly: 3
  false_answers: 0
  mean_context_precision_at_1: 1.0
  mean_context_precision_at_3: 0.57
  mean_context_recall: 0.93
  citation_accuracy: 1.0
  decline_accuracy: 1.0
  verbatim_quote_check_answered: 1.0
  mean_latency_ms: 0.2
  (RAG-only baseline: 7 answered correctly, 3 declined correctly, 0 false declines, 0 false answers)

  Per question
  OK  Q1 [answered] path=section_lookup P@1=1.0 P@3=0.33 recall=1.0 cite=Y top=1.0 0.5ms
  OK  Q2 [answered] path=section_lookup P@1=1.0 P@3=0.67 recall=1.0 cite=Y top=0.867 0.3ms
  OK  Q3 [answered] path=section_lookup P@1=1.0 P@3=0.67 recall=0.5 cite=Y top=0.9 0.3ms
  OK  Q4 [answered] path=rag P@1=1.0 P@3=0.67 recall=1.0 cite=Y top=1.0 0.2ms
  OK  Q5 [answered] path=rag P@1=1.0 P@3=0.33 recall=1.0 cite=Y top=0.84 0.1ms
  OK  Q6 [answered] path=section_lookup P@1=1.0 P@3=0.67 recall=1.0 cite=Y top=1.0 0.3ms
  OK  Q7 [answered] path=rag P@1=1.0 P@3=0.67 recall=1.0 cite=Y top=1.0 0.1ms
  OK  Q8 [declined] path=rag P@1=0.0 P@3=0.0 recall=0.0 cite=n/a top=0.7 0.2ms
  OK  Q9 [declined] path=rag P@1=0.0 P@3=0.0 recall=0.0 cite=n/a top=0.733 0.1ms
  OK  Q10 [declined] path=rag P@1=0.0 P@3=0.0 recall=0.0 cite=n/a top=0.8 0.1ms

Part 2 — extended eval
  n_cases: 26
  n_gated: 23
  n_known_limitations: 3
  correct: 23
  classification: {'answered_answerable': 15, 'false_declines': 0, 'declined_unanswerable': 6, 'false_answers': 0}
  path_choice_correct: 13/13
  citation_correct_answerable: 15/15
  multi_turn_correct: 4/4
  paths_used: {'list_files': 2, 'phrase_lookup': 2, 'rag': 17, 'section_lookup': 5}
  known_limitations_still_failing: 3
  OK  N1 path_choice [answered] path=list_files — What documents do you have?
  OK  N2 path_choice [answered] path=section_lookup — What is the minimum age for volunteers?
  OK  N3 citation [answered] path=rag — How old do you have to be to help out?
  OK  N4 path_choice [answered] path=phrase_lookup — Which policy mentions "locked filing cabinet"?
  OK  N5 answer_vs_decline [declined] path=rag — Do the documents mention "gluten-free"?
  OK  N6 answer_vs_decline [declined] path=rag — What is the date of the next food distribution?
  OK  N7 answer_vs_decline [declined] path=rag — Is there parking at the pantry?
  OK  N8 answer_vs_decline [declined] path=rag — What is the pantry's annual budget?
  OK  N9 path_choice [answered] path=section_lookup — Who approves new AI tools?
  OK  N10 citation [answered] path=rag — Can staff paste client names into ChatGPT?
  OK  N11 path_choice [answered] path=section_lookup — How do I get a receipt for my donation?
  OK  N12 path_choice [answered] path=rag — How long are household records kept?
  OK  N13 citation [answered] path=rag — When is fresh produce accepted?
  OK  N14 citation [answered] path=rag — Does the pantry share names with partner food banks?
  OK  M1 multi_turn [answered] path=rag — And how often can they come back?
  OK  M2 multi_turn [declined] path=rag — And how often can they come back?
  OK  M3 multi_turn [answered] path=section_lookup — What does it cover?
  OK  M4 multi_turn [declined] path=rag — Who was on it?
  OK  L1 path_choice [answered] path=section_lookup — What documents are needed for an uncontested divorce intake?
  OK  L2 path_choice [answered] path=list_files — List the documents
  OK  R1 regression [answered] path=rag — What is the deadline for the flat fee?
  OK  R2 regression [answered] path=rag — What's the client's fee?
  OK  R3 regression [answered] path=phrase_lookup — Which policy mentions 'locked filing cabinet'?
  KNOWN-FAIL K1 known_limitation [declined] path=rag status_ok=N citation_ok=N — Can I donate a homemade lasagna?
  KNOWN-FAIL K2 known_limitation [answered] path=rag status_ok=N citation_ok=N — What is the executive director's salary?
  KNOWN-FAIL K3 known_limitation [answered] path=rag forbidden_ok=N — What is the deadline for the flat fee?

Part 3 — review queue tasks
  OK  suspend holds the answer (pending, nothing released)
  OK  suspend keeps citations and route
  OK  declined draft is queued as declined
  OK  queue survives a restart (read by a new process) (pending seen by new process: 3)
  OK  approve releases the draft unchanged
  OK  edit-then-approve releases the reviewer's text, marked edited
  OK  reject never releases
  OK  nothing left pending
  OK  a decided item cannot be decided again
  completed: 9/9

Part 4 — direct checks for the Qodo PR #2 and PR #3 fixes
  OK  apostrophes are not read as a quoted phrase (finding 8)
  OK  real double and single quotes still give a phrase (finding 8)
  OK  mismatched source/section citations fail the paired check (finding 7)
  OK  refusal sentence in the second cited chunk declines (finding 9)
  OK  document listing titles are inside their cited evidence (finding 3)
  OK  empty and headings-only corpora raise a corpus error (finding 4)
  OK  rag-only ignores --previous for a self-contained question (finding 5)
  OK  rag-only still expands a real follow-up (finding 5)
  OK  refusal with repeated whitespace cites its own chunk (Qodo PR #3, finding 1)
  OK  a refusal phrase split by extra spaces still declines (Qodo PR #3, finding 1)
  OK  JSON listing citations are document-level, no chunk pointer (Qodo PR #3, finding 2)
  OK  review-queue listing citations are document-level (Qodo PR #3, finding 2)
  OK  chunk citations still serialise with chunk and section (Qodo PR #3, finding 2)
  OK  listing evidence is the H1 line exactly as in the file (Qodo PR #3, finding 3)
  OK  every listing evidence line is a real line of its file (Qodo PR #3, finding 3)
  passed: 15/15

Part 5 — plain-English behaviour specs (features/*.feature)
  01_pantry_answers.feature
    OK   N1 List every policy file
    OK   N2 A question that matches a heading goes straight to that section
    OK   N3 The same question in everyday words still finds the right section
    OK   N4 A phrase in double quotes is looked up word for word
    OK   N9 Who approves new AI tools
    OK   N10 Client names and ChatGPT
    OK   N11 Donation receipts
    OK   N12 Two similar headings are treated as unclear and go to search
    OK   N13 Fresh produce
    OK   N14 Sharing names with partner food banks
  02_law_firm_answers.feature
    OK   Q1 Divorce intake documents (section route)
    OK   Q2 How a free consultation starts
    OK   Q3 What to bring to the first consultation
    OK   Q4 The flat fee
    OK   Q5 Response time for a new inquiry
    OK   Q6 Where client documents are stored
    OK   Q7 Cases the firm does not take
    OK   L2 List every document
  03_declines.feature
    OK   N5 A quoted word that appears nowhere
    OK   N6 A date the policies never give
    OK   N7 Parking
    OK   N8 The annual budget (apostrophe must not fool it)
    OK   Q8 Off-topic question
    OK   Q9 A fee for work the firm does not list
    OK   Q10 A case-specific deadline the policies cannot know
  04_follow_ups.feature
    OK   M1 A follow-up after a pantry question
    OK   M2 The same follow-up with nothing before it is declined
    OK   M3 "What does it cover?" after asking about the flat fee
    OK   M4 A follow-up to an off-topic question is still declined
  05_regressions.feature
    OK   R1 A heading that shares words but gives no deadline is not used as the answer
    OK   R2 Apostrophes are not quote marks
    OK   R3 Real single quotes around a phrase still work
  06_known_failures.feature
    KNOWN-FAIL   K1 "Homemade" means the same as "home-cooked"
           - expected an answer, got declined
           - expected a citation from ['03-donations-policy.md'], got none
    KNOWN-FAIL   K2 A salary that is not in the documents is declined
           - expected a decline, got an answer citing ['01-volunteer-onboarding.md', '04-ai-use-policy.md']
           - expected no citations, got ['01-volunteer-onboarding.md', '04-ai-use-policy.md']
    KNOWN-FAIL   K3 The flat-fee deadline is not answered from "What the flat fee covers"
           - quoted the forbidden section 'What the flat fee covers'
  scenarios: 35
  gated_passed: 32/32
  known_failures_still_failing: 3
  known_failures_now_passing: 0
  eval_cases_without_a_spec: []
  all_gated_pass: True

RESULT: PASS
```
