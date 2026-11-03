GATE BUDGET MEASUREMENT — tests/test_template_gate_pairing.py
Declared at: ac08dfed (#602 patrol monolith split into twelve leg gates)
Written: 2026-11-03

WHY THIS GATE LEFT THE FLEET DEFAULT
  It has no budget_sec of its own, so it fell through to default.budget_sec = 69.27 s.
  Its population is "shipped gates this commit touches" (the STAGED INDEX, read by the
  gate itself: tests/test_template_gate_pairing.py:115), and its cost is per-judged-gate
  temp-repo work. Before #602 that population was 1 (the patrol monolith counted once);
  the split took it to 20, roughly doubling the wall. It therefore cannot finish inside
  the default and `gate_select --staged --run` records NO VERDICT for it — not a failure
  and not a pass. This receipt is the basis for the budget that removes that hole.

SAMPLES (this manifest's slow-tail rule, #579 / ruling n=4460: the WORST OBSERVED is the
basis, never the quietest single sample)

  BASIS  192.11 s  rc=0  load 8.31 (1-min)  population 19 shipped gates touched
         Regime: 55 staged paths, 13 split patrol legs on disk, 4-core box.
         Taken on the staged tree that BECAME ac08dfed, before the commit's final two
         paths were staged. The raw output of this run was not retained; the figures are
         as recorded in the measuring session. Population 19 of the 20 the cited tree
         carries, so the figure is CONSERVATIVE for the declared tree: the missing gate
         adds cost, it does not remove any.

  AT-TREE 108.17 s  rc=0  load 3.44 (1-min)  population 20 shipped gates touched
         Reproducible at the cited revision. Command:

           git worktree add --detach /tmp/af-pair-measure ac08dfed
           cd /tmp/af-pair-measure && git reset --soft 944a6164   # puts the commit's own
                                                                  # diff in the index,
                                                                  # which is the
                                                                  # population the gate
                                                                  # reads
           /usr/bin/time -f "WALL_SEC %e" /usr/bin/python3 tests/test_template_gate_pairing.py

         Output (verbatim, tail):
           PASS  ARM 1..8 (all eight probes bit)
           PASS  CONTROL: the instrument reads the staged population it is judging
           PASS  CONTROL: an empty index is empty, not unread
           population: 20 shipped gate(s) touched by this commit; 0 unpaired
           template gate pairing passed — every probe bit, and no touched shipped gate is unpaired
           WALL_SEC 108.17

  PRIOR  110.80 s  rc=0  load 3.16 (1-min)  population 19
         Measured by the #602 lane on a deliberately quiet box. Methodologically WORSE
         than the basis, not merely smaller: a quiet box is exactly the bias the
         slow-tail rule exists to correct. Recorded, never the basis.

DERIVATION (tools/gate_budget.py:534 — margin_for(x) = 4.0 + 0.75/x)
  margin_for(192.11) = 4.0 + 0.75/192.11 = 4.003904 -> stored 4.004
  budget_sec = 192.11 * 4.003904 = 769.19 s

TWO THINGS CHECKED SO THE DECLARATION CREATES NO SECOND PROBLEM
  1. The gate is NOT in default.population (26 entries, largest 17.13 s), so declaring it
     cannot disturb the default's own derivation.
  2. It is absent from docs/shipped-audit-skips.json and from the shipped audit's
     registrations, so the shipped depth does not run it and no skip is owed.

CONTENTION NOTE
  The at-tree sample was taken at load 3.44, after the #602 lane's 65-gate round had
  exited, so the two runs do not overlap.
