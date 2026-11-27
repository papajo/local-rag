# SAMPLE DATA only (invented pantry, fictional law firm).

Feature: Bugs that were fixed stay fixed
  Each scenario guards one bug Qodo found on pull request #2.

  @R1
  Scenario: R1 A heading that shares words but gives no deadline is not used as the answer
    # Qodo finding 1. "What the flat fee covers" shares two words with
    # the question but states no deadline.
    Given the documents in "sample_corpus"
    When I ask "What is the deadline for the flat fee?"
    Then it may answer or decline
    And it cites "03-fee-policy.md"
    And it does not use the "section_lookup" route
    And it does not use the "phrase_lookup" route

  @R2
  Scenario: R2 Apostrophes are not quote marks
    # Qodo finding 8. "What's the client's fee?" was read as the phrase
    # "s the client" and answered from the confidentiality policy.
    Given the documents in "sample_corpus"
    When I ask "What's the client's fee?"
    Then it may answer or decline
    And it cites one of "03-fee-policy.md", "02-consultation-process.md"
    And it does not use the "phrase_lookup" route
    And it does not cite "05-confidentiality.md"

  @R3
  Scenario: R3 Real single quotes around a phrase still work
    Given the documents in "sample_corpus_nonprofit"
    When I ask "Which policy mentions 'locked filing cabinet'?"
    Then it answers
    And it cites "05-client-privacy.md"
    And the cited section is "Where household records are kept"
    And the answer comes from the "phrase_lookup" route

  @R4
  Scenario: R4 A decline quotes the passage it came from, not the first chunk
    # Qodo PR #3, finding 1. The refusal sentence lives in the deadline
    # policy's chunk 10. The old code re-found it by text and fell back
    # to the first chunk when the sentence had extra spaces. No bundled
    # document has those extra spaces, so this scenario pins the
    # behaviour on the real files; the double-space case itself is
    # covered by the synthetic checks in eval Part 4.
    Given the documents in "sample_corpus"
    When I ask "Which policy mentions \"does not state the deadline\"?"
    Then it declines
    And the decline names "04-deadline-policy.md"
    And the answer comes from the "phrase_lookup" route

  @R5
  Scenario: R5 A document listing cites titles, not chunks
    # Qodo PR #3, finding 2. The JSON and review-queue form of a listing
    # citation used to point at a section chunk. The title line is not
    # inside any chunk, so the structured form must say document-level
    # with no chunk and no section.
    Given the documents in "sample_corpus"
    When I ask "List the documents"
    Then it answers
    And it cites all of "01-intake-checklist.md", "02-consultation-process.md", "03-fee-policy.md", "04-deadline-policy.md", "05-confidentiality.md", "06-what-we-do-not-do.md"
    And the listing citations are document-level
    And the answer comes from the "list_files" route

  @R6
  Scenario: R6 A listing's evidence is a line from its own file
    # Qodo PR #3, finding 3. The old code rebuilt the evidence line as
    # "# <title>", which is not a line of the file when the heading has
    # odd spacing. No bundled heading has odd spacing, so this pins the
    # behaviour on the real files; the odd-spacing case is covered by
    # the synthetic check in eval Part 4.
    Given the documents in "sample_corpus"
    When I ask "List the documents"
    Then it answers
    And each listing citation's evidence is a line from its own file
    And the answer comes from the "list_files" route
