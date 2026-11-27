# SAMPLE DATA only (invented pantry, fictional law firm).

Feature: Decline when the documents do not hold the answer
  When the answer is not in the files, the assistant says so and quotes
  nothing. A wrong answer with a real-looking citation is worse than
  no answer.

  @N5
  Scenario: N5 A quoted word that appears nowhere
    Given the documents in "sample_corpus_nonprofit"
    When I ask "Do the documents mention \"gluten-free\"?"
    Then it declines
    And it cites nothing
    And the answer comes from the "rag" route

  @N6
  Scenario: N6 A date the policies never give
    Given the documents in "sample_corpus_nonprofit"
    When I ask "What is the date of the next food distribution?"
    Then it declines
    And it cites nothing

  @N7
  Scenario: N7 Parking
    Given the documents in "sample_corpus_nonprofit"
    When I ask "Is there parking at the pantry?"
    Then it declines
    And it cites nothing

  @N8
  Scenario: N8 The annual budget (apostrophe must not fool it)
    Given the documents in "sample_corpus_nonprofit"
    When I ask "What is the pantry's annual budget?"
    Then it declines
    And it cites nothing

  @Q8
  Scenario: Q8 Off-topic question
    Given the documents in "sample_corpus"
    When I ask "When did someone last go to the moon?"
    Then it declines
    And it cites nothing

  @Q9
  Scenario: Q9 A fee for work the firm does not list
    Given the documents in "sample_corpus"
    When I ask "What is the fee for a patent application?"
    Then it declines
    And it cites nothing

  @Q10
  Scenario: Q10 A case-specific deadline the policies cannot know
    Given the documents in "sample_corpus"
    When I ask "What is the deadline for my specific case filed last Tuesday?"
    Then it declines
    And it cites nothing
