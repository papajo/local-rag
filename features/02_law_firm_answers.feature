# SAMPLE DATA: Harbor & Pine Law is a fictional firm.
# The files in sample_corpus/ are made up for testing only.

Feature: Answer front-desk questions from the firm's own policies
  The original 10-question set (Q1 to Q10) plus two routing checks.
  Q8 to Q10 are in 03_declines.feature.

  Background:
    Given the documents in "sample_corpus"

  @Q1 @L1
  Scenario: Q1 Divorce intake documents (section route)
    When I ask "What documents are needed for an uncontested divorce intake?"
    Then it answers
    And it cites "01-intake-checklist.md"
    And the cited section is "Documents needed for an uncontested divorce intake"
    And the answer comes from the "section_lookup" route

  @Q2
  Scenario: Q2 How a free consultation starts
    When I ask "How does a free consultation start?"
    Then it answers
    And it cites "02-consultation-process.md"

  @Q3
  Scenario: Q3 What to bring to the first consultation
    When I ask "What should a client bring to the first consultation?"
    Then it answers
    And it cites one of "02-consultation-process.md", "01-intake-checklist.md"

  @Q4
  Scenario: Q4 The flat fee
    When I ask "What is the flat fee for an uncontested divorce?"
    Then it answers
    And it cites "03-fee-policy.md"

  @Q5
  Scenario: Q5 Response time for a new inquiry
    When I ask "How quickly does the firm respond to a new inquiry?"
    Then it answers
    And it cites "04-deadline-policy.md"

  @Q6
  Scenario: Q6 Where client documents are stored
    When I ask "Are client documents stored locally or in the cloud?"
    Then it answers
    And it cites "05-confidentiality.md"

  @Q7
  Scenario: Q7 Cases the firm does not take
    When I ask "What cases does the firm not take on?"
    Then it answers
    And it cites "06-what-we-do-not-do.md"

  @L2
  Scenario: L2 List every document
    When I ask "List the documents"
    Then it answers
    And it cites all of "01-intake-checklist.md", "02-consultation-process.md", "03-fee-policy.md", "04-deadline-policy.md", "05-confidentiality.md", "06-what-we-do-not-do.md"
    And the answer comes from the "list_files" route
