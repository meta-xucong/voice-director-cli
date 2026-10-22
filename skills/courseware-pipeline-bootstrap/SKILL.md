---
name: courseware-pipeline-bootstrap
description: Install the public Voice Director CLI repository and its related Codex Skills on Windows by following the repository's setup guide. Use when a user asks Codex to download or set up this project from GitHub.
metadata:
  short-description: Download and configure the courseware pipeline
---

# Courseware Pipeline Bootstrap

When asked to install this project, read and follow the repository's [INSTALL.md](https://github.com/meta-xucong/voice-director-cli/blob/main/INSTALL.md) as the operational source of truth. If a clone already exists, use its local `INSTALL.md` and installer script.

1. Read the repository's `INSTALL.md`, inspect `scripts/install.ps1`, and confirm the expected repository is `meta-xucong/voice-director-cli`.
2. If the repository is not available locally, clone it to `%USERPROFILE%\Documents\Codex\voice-director-cli`. Never overwrite an existing directory. If one exists, inspect its Git remote and worktree state first.
3. Run the repository installer from its root. It installs only the four related project Skills, preserves `references/`, checks for Python 3.12, and runs offline tests. It may use WinGet to install Python 3.12 if absent.
4. Report the repository and Skills locations, Python version, test result, and any conflict or manual step.

Do not put user lesson material into the public repository. Do not run TTS, upload content, modify GitHub, or install unrelated software as part of setup. The installer does not overwrite a different Skill already at its destination.
