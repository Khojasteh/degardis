---
kind: concept
title: How this system fails
---

Failures fall into three shapes, and each is reproduced differently.

Three shapes account for nearly every defect here.

## Wrong value

The code runs and produces something incorrect. Reproduce by calling it with the
reported input.

## Wrong path

The code takes a branch it should not. Reproduce by recreating the state the
branch reads, which is rarely the same as the input.

## No result

The code raises or hangs. Reproduce by the operation the reporter named, at the
same concurrency.

## Worked example

The report: totals come out one short for orders placed on the last day of a
month.

1. **Reproduce.** A wrong value, so call the total with a month-end date. It is
   one short.
2. **Test first.** Write the failing test at that date. It fails.
3. **Repair.** The range excluded its upper bound.
4. **Confirm.** The test passes, and the suite still does.

The test was written before the repair, so it is known to fail without it. A test
written afterwards proves only that it passes now.
