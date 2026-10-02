---
title: Toolchain checks
applicability:
- When the change touches packaging
- When the change moves the supported version floor
---

- Does the package still import on the oldest supported interpreter?
- Is every new dependency declared where the resolver reads it?
- Does the lock state still match what the manifest asks for?
- Does raising the floor drop an interpreter a consumer relies on? Weigh it
  against [[guide:compatibility]].
