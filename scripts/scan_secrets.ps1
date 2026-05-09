Param(
  [string]$Mode = "manual"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Use script location as source of truth to avoid encoding issues in unicode paths.
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$patterns = @(
  # Generic JWT-like token (catches leaked legacy anon/service_role JWT)
  'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}',
  # Supabase secret API key (new format)
  'sb_secret_[A-Za-z0-9_-]{10,}',
  # Common cloud API key prefixes
  'sk_live_[A-Za-z0-9]{12,}',
  'AIza[0-9A-Za-z\-_]{20,}'
)

$excludeFiles = @(
  'env.example',
  '*.md',
  '*.txt'
)

function Test-PatternInText {
  Param(
    [string]$Text,
    [string]$FileHint
  )

  foreach ($pattern in $patterns) {
    if ($Text -match $pattern) {
      return [PSCustomObject]@{
        Matched = $true
        Pattern = $pattern
        FileHint = $FileHint
      }
    }
  }

  return [PSCustomObject]@{
    Matched = $false
    Pattern = ''
    FileHint = $FileHint
  }
}

function Is-ExcludedFile {
  Param([string]$Path)

  foreach ($rule in $excludeFiles) {
    if ($Path -like $rule) { return $true }
    if ($Path -like "*\$rule") { return $true }
    if ($Path -like "*/$rule") { return $true }
  }
  return $false
}

$findings = New-Object System.Collections.Generic.List[object]

# 1) Scan tracked files in HEAD.
$trackedFiles = git -c core.quotepath=false ls-files
foreach ($file in $trackedFiles) {
  if (Is-ExcludedFile $file) { continue }
  if (-not (Test-Path $file)) { continue }

  try {
    $content = Get-Content -Path $file -Raw -ErrorAction Stop
  }
  catch {
    continue
  }

  $result = Test-PatternInText -Text $content -FileHint $file
  if ($result.Matched) {
    $findings.Add([PSCustomObject]@{
      Scope = 'HEAD'
      File = $file
      Pattern = $result.Pattern
    })
  }
}

# 2) Scan staged diff to catch newly added leaks before push.
$stagedPatch = git diff --cached --unified=0
$resultPatch = Test-PatternInText -Text $stagedPatch -FileHint 'staged-diff'
if ($resultPatch.Matched) {
  $findings.Add([PSCustomObject]@{
    Scope = 'STAGED'
    File = 'staged-diff'
    Pattern = $resultPatch.Pattern
  })
}

if ($findings.Count -gt 0) {
  Write-Host ''
  Write-Host '[SECURITY BLOCK] Potential secrets detected. Push blocked.' -ForegroundColor Red
  Write-Host 'Findings:' -ForegroundColor Yellow
  $findings | ForEach-Object {
    Write-Host (" - [{0}] {1} | pattern: {2}" -f $_.Scope, $_.File, $_.Pattern)
  }
  Write-Host ''
  Write-Host 'Action: remove leaked values, rotate keys if needed, then retry push.' -ForegroundColor Yellow
  exit 1
}

if ($Mode -eq 'manual') {
  Write-Host '[OK] No obvious secret patterns found in tracked files or staged diff.' -ForegroundColor Green
}

exit 0
