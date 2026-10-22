# Install with Codex

This repository can be installed by asking Codex to read this file and follow it:

> Read `https://github.com/meta-xucong/voice-director-cli`, follow its `INSTALL.md`, and install the project and its Codex skills on this Windows computer. Use the default install locations unless they already contain unrelated files. Report each change and run the documented checks.

## What the setup does

1. Clones this public repository to `%USERPROFILE%\Documents\Codex\voice-director-cli` unless Codex has already cloned it elsewhere for this task.
2. Runs `scripts/install.ps1` from the clone.
3. Checks for Python 3.12. If missing and WinGet is available, the script installs Python 3.12 through WinGet; otherwise it stops with instructions to install Python 3.12.
4. Installs the four related Skills under `%CODEX_HOME%\skills` or `%USERPROFILE%\.codex\skills`, preserving their sibling folders and references.
5. Runs the offline test suite and CLI smoke checks.

No pip packages, speech models, TTS provider accounts, or API keys are required. The setup does not call a TTS service or upload course material. If Python is absent, the script attempts a user-scope install of `Python.Python.3.12` with WinGet and accepts the package/source agreements so the setup can proceed unattended. Microsoft documents the WinGet install options in its [install command reference](https://learn.microsoft.com/en-us/windows/package-manager/winget/install). If WinGet is missing or installation fails, the script stops and explains the manual step.

## Codex procedure

- Inspect this guide and `scripts/install.ps1` before execution.
- If the repository is not already present, clone it to the default path. If that path already exists, inspect it and avoid overwriting user files; reuse it only if it is this repository and its state is suitable.
- Run the installer from the repository root, passing `-SkillsRoot` only when a custom Codex skills directory is needed:

```powershell
pwsh -NoProfile -File .\scripts\install.ps1
```

- If `pwsh` is unavailable, use Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File .\scripts\install.ps1
```

- Report the repository path, selected Python version, installed or already-matching Skills, test result, and any step that stopped for user action.
- Do not place lesson videos, transcripts, narration, director maps, alignment input, or generated reports inside the public clone. Use a sibling private work directory.

## Safety and repeat runs

The installer never overwrites a different Skill already present at the destination. Identical installed Skills are left in place. If a destination Skill differs, the script stops and names the conflict so Codex can inspect it before making any change. Re-running after a successful install is safe.

The installer checks out no branches, commits nothing, and changes no GitHub state. It only copies this project's Skills into the local Codex skills directory, checks the local CLI, and runs offline tests. Restart or refresh Codex after installation if the new Skills do not appear immediately.
