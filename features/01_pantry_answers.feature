# SAMPLE DATA: Bayside Community Pantry is an invented nonprofit.
# The files in sample_corpus_nonprofit/ are made up for testing only.

Feature: Answer pantry staff questions from the pantry's own policies
  A staff member asks a question in plain words. If a policy covers it,
  the assistant answers with a word-for-word quote and says which file
  and which section it came from.

  Background:
    Given the documents in "sample_corpus_nonprofit"

  @N1
  Scenario: N1 List every policy file
    When I ask "What documents do you have?"
    Then it answers
    And it cites all of "01-volunteer-onboarding.md", "02-food-distribution.md", "03-donations-policy.md", "04-ai-use-policy.md", "05-client-privacy.md"
    And the answer comes from the "list_files" route

  @N2
  Scenario: N2 A question that matches a heading goes straight to that section
    When I ask "What is the minimum age for volunteers?"
    Then it answers
    And it cites "01-volunteer-onboarding.md"
    And the cited section is "Minimum age for volunteers"
    And the answer comes from the "section_lookup" route

  @N3
  Scenario: N3 The same question in everyday words still finds the right section
    When I ask "How old do you have to be to help out?"
    Then it answers
    And it cites "01-volunteer-onboarding.md"
    And the cited section is "Minimum age for volunteers"
    And the answer comes from the "rag" route

  @N4
  Scenario: N4 A phrase in double quotes is looked up word for word
    When I ask "Which policy mentions \"locked filing cabinet\"?"
    Then it answers
    And it cites "05-client-privacy.md"
    And the cited section is "Where household records are kept"
    And the answer comes from the "phrase_lookup" route

  @N9
  Scenario: N9 Who approves new AI tools
    When I ask "Who approves new AI tools?"
    Then it answers
    And it cites "04-ai-use-policy.md"
    And the cited section is "Who approves new AI tools"
    And the answer comes from the "section_lookup" route

  @N10
  Scenario: N10 Client names and ChatGPT
    When I ask "Can staff paste client names into ChatGPT?"
    Then it answers
    And it cites "04-ai-use-policy.md"
    And the cited section is "What staff must never put into an AI tool"
    And the answer comes from the "rag" route

  @N11
  Scenario: N11 Donation receipts
    When I ask "How do I get a receipt for my donation?"
    Then it answers
    And it cites "03-donations-policy.md"
    And the cited section is "Donation receipts"
    And the answer comes from the "section_lookup" route

  @N12
  Scenario: N12 Two similar headings are treated as unclear and go to search
    When I ask "How long are household records kept?"
    Then it answers
    And it cites "05-client-privacy.md"
    And the cited section is "How long records are kept"
    And the answer comes from the "rag" route

  @N13
  Scenario: N13 Fresh produce
    When I ask "When is fresh produce accepted?"
    Then it answers
    And it cites "03-donations-policy.md"
    And the cited section is "Food donations we accept"

  @N14
  Scenario: N14 Sharing names with partner food banks
    When I ask "Does the pantry share names with partner food banks?"
    Then it answers
    And it cites "05-client-privacy.md"
    And the cited section is "Sharing records with partners"
