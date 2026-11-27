# SAMPLE DATA only (invented pantry, fictional law firm).

Feature: Short follow-up questions use the question before them
  "And how often can they come back?" only makes sense after an earlier
  question. One turn of memory only.

  @M1
  Scenario: M1 A follow-up after a pantry question
    Given the documents in "sample_corpus_nonprofit"
    And the previous question was "Who can receive food from the pantry?"
    When I ask "And how often can they come back?"
    Then it answers
    And it cites "02-food-distribution.md"
    And the cited section is "How often a household can visit"

  @M2
  Scenario: M2 The same follow-up with nothing before it is declined
    Given the documents in "sample_corpus_nonprofit"
    When I ask "And how often can they come back?"
    Then it declines
    And it cites nothing

  @M3
  Scenario: M3 "What does it cover?" after asking about the flat fee
    Given the documents in "sample_corpus"
    And the previous question was "What is the flat fee for an uncontested divorce?"
    When I ask "What does it cover?"
    Then it answers
    And it cites "03-fee-policy.md"
    And the cited section is "What the flat fee covers"
    And the answer comes from the "section_lookup" route

  @M4
  Scenario: M4 A follow-up to an off-topic question is still declined
    Given the documents in "sample_corpus"
    And the previous question was "When did someone last go to the moon?"
    When I ask "Who was on it?"
    Then it declines
    And it cites nothing
