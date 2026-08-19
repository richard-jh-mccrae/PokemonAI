"""One module per card function, named for the function it owns.

Deliberately empty of re-exports: importing a function must not drag in its siblings, and an
empty package init is what guarantees no cycle back into the card records."""
