# ADR-TEMP-676 — One action-choice identity spans search and selection

One neutral Action Choice Identity combines semantic Action Identity with the exact submitted selection
and identifies Candidate Roster members across search, coverage, policy, and final-result validation.
The existing policy-specific type becomes a compatibility alias with an unchanged wire shape until #611
retires it; the broader rename is accepted to prevent policy ownership and selection-blind matching.

Search Result accepts only a Candidate Roster already proven equal, in order, to the legal actions in its
Evaluation Request. The coordinator validates this proof and never repairs, reorders, or completes a roster
after search, preserving ADR-0178's materialize-before-work boundary.
