# SAMPLE DATA only (invented pantry, fictional law firm).

Feature: Known failures, kept visible
  These say what SHOULD happen. Today they fail. They are reported on
  every run but do not fail it. Each one has an entry in BACKLOG.md.
  When one starts passing, the run prints KNOWN-NOW-OK: remove the
  @known-failure tag and close the backlog item.

  @known-failure @K1
  Scenario: K1 "Homemade" means the same as "home-cooked"
    Given the documents in "sample_corpus_nonprofit"
    When I ask "Can I donate a homemade lasagna?"
    Then it answers
    And it cites "03-donations-policy.md"

  @known-failure @K2
  Scenario: K2 A salary that is not in the documents is declined
    Given the documents in "sample_corpus_nonprofit"
    When I ask "What is the executive director's salary?"
    Then it declines
    And it cites nothing

  @known-failure @K3
  Scenario: K3 The flat-fee deadline is not answered from "What the flat fee covers"
    Given the documents in "sample_corpus"
    When I ask "What is the deadline for the flat fee?"
    Then it may answer or decline
    And it cites "03-fee-policy.md"
    And it does not quote the section "What the flat fee covers"
