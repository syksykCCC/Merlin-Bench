# Protocol summary

1. Find one Hamilton cycle in the public graph.
2. Build 24 complete canonically serialized relabelings and send all of them in one
   `hamiltonicity.commit` event.
3. Arthur returns all 24 random bits in one `hamiltonicity.challenge` reply.
4. Send one `hamiltonicity.open` event. For bit 0, open the source-to-commit
   permutation; for bit 1, open a Hamilton cycle in the committed graph.

The full commitment is parsed before any challenge bit is sampled. Events are
artifact-free and terminal on malformed or invalid input.
