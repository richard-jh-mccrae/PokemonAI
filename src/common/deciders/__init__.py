"""The Pilot in parts: one module per decision family, each a `*Mixin` the `Pilot` composes.

`facts` holds the records they all read (`Board`, `Context`); `board_build` / `context_build` assemble those; every
other module scores one family of option against them. Nothing here imports `common.pilot` — the arrow runs one way,
which is what lets a family be read on its own."""
