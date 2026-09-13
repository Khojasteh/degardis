---
title: Repair wrong behavior
recognize:
- the requester reports behavior that is wrong
- the requester asks for a defect to be fixed
goal: The behavior is correct, and the repair is covered by a test that failed before it.
knowledge:
- evidence-required
- failure-modes
---

Reproduce before repairing. A repair applied to a defect nobody reproduced is a
change whose effect nobody can observe. Run [[script:greet.py]] when the defect
is only reproducible by the sample program.
