---
name: skillopt-dir-write-permission
description: Writing to E:\skillopt needs a one-time elevated icacls grant; the Claude Code process runs non-elevated.
metadata: 
  node_type: memory
  type: project
  originSessionId: ff54177a-3262-4e53-b9cb-bc92bf633e25
---

`E:\skillopt` is owned by `BUILTIN\Administrators` and originally granted only **Read** to `Users`, so every write failed with `Permission denied` / `UnauthorizedAccessException`. This is **NOT a sandbox issue** — `dangerouslyDisableSandbox` did not help. The Claude Code process runs **non-elevated** as `Dionysus\王奕豪` (a Users member), so it only got read rights.

**Fix (user ran it in an *elevated* PowerShell — a normal window fails with "Access is denied"):**
`icacls "E:\skillopt" /grant "*S-1-5-32-545:(OI)(CI)M" /T`  (`*S-1-5-32-545` = the built-in Users group). After this, writes work.

Git also needed: `git config --global --add safe.directory E:/skillopt` (dubious-ownership warning, since the folder owner is Administrators).

**Why:** non-obvious; cost several turns to diagnose. **How to apply:** if writes to `E:\skillopt` (or other Admin-owned dirs) start failing again, re-run the elevated icacls grant; don't blame the sandbox. Part of [[skillopt-repro-project]].
