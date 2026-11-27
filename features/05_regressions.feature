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
