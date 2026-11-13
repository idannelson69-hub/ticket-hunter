# העלאה ל-GitHub (מאגר ציבורי, באישור המשתמש) והגדרת הסודות. הרצה חוזרת מעדכנת קוד וסודות.
# שימוש: powershell -ExecutionPolicy Bypass -File deploy\github-setup.ps1
param([string]$RepoName = "ticket-hunter", [switch]$SecretsOnly)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $PSScriptRoot ".env.cloud"
$utf8 = New-Object System.Text.UTF8Encoding $false
Set-Location $root

$cfg = @{}
foreach ($line in [IO.File]::ReadAllLines($envFile, $utf8)) {
    if ($line -match '^\s*([A-Z_]+)=(.*)$') { $cfg[$Matches[1]] = $Matches[2].Trim() }
}
$owner = gh api user --jq .login
$full = "$owner/$RepoName"

if (-not $SecretsOnly) {
    if (-not (Test-Path .git)) { git init -q -b main }
    git add -A
    $staged = git diff --cached --name-only
    foreach ($bad in @(".env", "deploy/.env.cloud", "backend/.env")) {
        if ($staged -contains $bad) { throw "עצירה: הקובץ $bad עומד לעלות ל-GitHub" }
    }
    foreach ($s in @($cfg.TELEGRAM_BOT_TOKEN, $cfg.SMTP_PASSWORD, $cfg.TICKETMASTER_API_KEY, $cfg.ADMIN_PASSWORD, $cfg.SESSION_SECRET)) {
        if (-not $s) { continue }
        $hit = git grep --cached -l -F -e $s
        if ($hit) { throw "עצירה: נמצא סוד בתוך קובץ שעומד לעלות: $hit" }
    }
    Write-Host "✓ בדיקת בטיחות: אין סודות בקבצים"
    if (git status --porcelain) {
        $uid = gh api user --jq .id; git -c user.name="$owner" -c user.email="$uid+$owner@users.noreply.github.com" commit -q -m "עדכון מערכת צייד כרטיסים" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    }
    $exists = $true
    try { $ErrorActionPreference = "Continue"; gh repo view $full 2>$null | Out-Null; if ($LASTEXITCODE -ne 0) { $exists = $false } }
    catch { $exists = $false } finally { $ErrorActionPreference = "Stop" }
    if (-not $exists) {
        gh repo create $full --public --source . --remote origin --push --description "מעקב מכירת כרטיסים להופעות"
    } else {
        if (-not (git remote)) { git remote add origin "https://github.com/$full.git" }
        git push -q -u origin main
    }
    Write-Host "✓ הקוד ב-GitHub: https://github.com/$full"
}

# הסודות עוברים דרך קובץ זמני (UTF-8 בלי BOM) ולא דרך צינור של PowerShell — שמשבש קידוד
$tmpEnv = Join-Path $env:TEMP ("th-secrets-" + [guid]::NewGuid().ToString("N") + ".env")
try {
    $lines = @()
    foreach ($name in @("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO", "TICKETMASTER_API_KEY")) {
        $v = ($cfg[$name] -replace '[^\x21-\x7E]', '')   # רק תווים רגילים — בלי רווחים, BOM או סוף שורה
        if ($v) { $lines += "$name=$v"; Write-Host "✓ סוד יוגדר: $name" } else { Write-Host "· דילוג (ריק): $name" }
    }
    [IO.File]::WriteAllText($tmpEnv, ($lines -join "`n") + "`n", $utf8)
    gh secret set -f $tmpEnv --repo $full
    if ($LASTEXITCODE -ne 0) { throw "הגדרת הסודות נכשלה" }
} finally { Remove-Item $tmpEnv -Force -ErrorAction SilentlyContinue }
Write-Host "מעקב אחרי ההרצות: https://github.com/$full/actions"
