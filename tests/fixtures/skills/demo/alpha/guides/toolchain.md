---
title: Toolchain checks
activation: When the change touches packaging or the supported version floor
---

- Does the package still import on the oldest supported interpreter?
- Is every new dependency declared where the resolver reads it?
- Does the lock state still match what the manifest asks for?
