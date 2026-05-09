# Security Checklist (API Keys)

## Why this exists
- Prevent secret leakage before push to GitHub.
- Keep a repeatable process after key rotation incidents.

## Current status (2026-05-09)
- Runtime code no longer hardcodes Supabase keys.
- Legacy leaked JWT still exists in old history commit(s): `56aaffa`.
- Keys were rotated and local/deploy env values updated.

## Mandatory checks before each push
1. Run secret scan:
   - `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/scan_secrets.ps1`
2. Verify sensitive files are not tracked:
   - `git ls-files .env .streamlit/secrets.toml`
3. Inspect staged changes for accidental secrets:
   - `git diff --cached`

## Automatic guardrail
- Hook file: `.githooks/pre-push`
- Script file: `scripts/scan_secrets.ps1`
- Local activation command:
  - `git config core.hooksPath .githooks`

## Incident response if flagged
1. Stop push immediately.
2. Remove secret from tracked changes and commit history if needed.
3. Rotate affected key in provider console.
4. Update runtime secrets in deployment platform.
5. Re-run `scripts/scan_secrets.ps1` and push again.
