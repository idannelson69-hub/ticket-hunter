# פריסה אוטומטית לשרת הענן.
# שימוש:  powershell -ExecutionPolicy Bypass -File deploy\deploy.ps1 -ServerIp 1.2.3.4
# בדיקת אריזה בלבד (בלי שרת):  ... -PackageOnly
param(
    [string]$ServerIp = "",
    [switch]$PackageOnly
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$key = Join-Path $env:USERPROFILE ".ssh\ticket-hunter"
$envFile = Join-Path $PSScriptRoot ".env.cloud"
$tmp = Join-Path $env:TEMP "ticket-hunter-deploy"
New-Item -ItemType Directory -Force $tmp | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding $false

function Read-Env($path) {
    $h = [ordered]@{}
    foreach ($line in [IO.File]::ReadAllLines($path, $utf8)) {
        if ($line -match '^\s*([A-Z_]+)=(.*)$') { $h[$Matches[1]] = $Matches[2].Trim() }
    }
    return $h
}
function Set-EnvValue($path, $name, $value) {
    $lines = [IO.File]::ReadAllLines($path, $utf8) | ForEach-Object { if ($_ -match "^$name=") { "$name=$value" } else { $_ } }
    [IO.File]::WriteAllLines($path, $lines, $utf8)
}

if (-not (Test-Path $envFile)) { throw "חסר הקובץ deploy\.env.cloud" }
$cfg = Read-Env $envFile

# --- בדיקת פרטים חסרים ---
$missing = @()
if (-not $cfg.TELEGRAM_BOT_TOKEN) { $missing += "TELEGRAM_BOT_TOKEN (התראות לטלפון)" }
if (-not $cfg.SMTP_PASSWORD) { $missing += "SMTP_PASSWORD (התראות למייל)" }
if (-not $cfg.TICKETMASTER_API_KEY) { $missing += "TICKETMASTER_API_KEY (מקור Ticketmaster)" }
if ($missing.Count) { Write-Host "⚠️ חסרים ב-.env.cloud — הערוצים האלה לא יפעלו עד שימולאו:" -ForegroundColor Yellow; $missing | ForEach-Object { Write-Host "   - $_" } }

# --- איתור אוטומטי של מזהה הצ'אט בטלגרם ---
if ($cfg.TELEGRAM_BOT_TOKEN -and -not $cfg.TELEGRAM_CHAT_ID) {
    try {
        $u = Invoke-RestMethod "https://api.telegram.org/bot$($cfg.TELEGRAM_BOT_TOKEN)/getUpdates" -TimeoutSec 15
        $chat = $u.result | ForEach-Object { $_.message.chat } | Where-Object { $_.type -eq "private" } | Select-Object -Last 1
        if ($chat) {
            Set-EnvValue $envFile "TELEGRAM_CHAT_ID" $chat.id
            $cfg.TELEGRAM_CHAT_ID = "$($chat.id)"
            Write-Host "✓ נמצא מזהה צ'אט בטלגרם ($($chat.first_name))" -ForegroundColor Green
        } else {
            Write-Host "⚠️ לא נמצאה הודעה לבוט. שלח לבוט הודעה בטלגרם והרץ שוב." -ForegroundColor Yellow
        }
    } catch { Write-Host "⚠️ הטוקן של טלגרם לא תקין או שאין חיבור: $($_.Exception.Message -replace 'bot\d+:[\w-]+','bot***')" -ForegroundColor Yellow }
}

# --- דומיין ---
if (-not $cfg.DOMAIN -and $ServerIp) {
    $cfg.DOMAIN = ($ServerIp -replace '\.', '-') + ".sslip.io"
    Set-EnvValue $envFile "DOMAIN" $cfg.DOMAIN
}

# --- אריזה ---
$pkg = Join-Path $tmp "th.tgz"
Push-Location $root
try {
    & tar -czf $pkg --exclude=.venv --exclude=node_modules --exclude=.next --exclude=frontend/out `
        --exclude=backend/data --exclude=data --exclude=.env --exclude=browser-profile --exclude=.claude `
        --exclude=deploy/.env.cloud --exclude=__pycache__ --exclude=.pytest_cache --exclude=docs --exclude=tools .
    if ($LASTEXITCODE -ne 0) { throw "האריזה נכשלה" }
} finally { Pop-Location }
Write-Host ("✓ חבילה נוצרה: {0:N1} MB" -f ((Get-Item $pkg).Length / 1MB))
if ($PackageOnly) { & tar -tzf $pkg | Select-Object -First 400; return }

if (-not $ServerIp) { throw "חסרה כתובת השרת: -ServerIp 1.2.3.4" }
if (-not (Test-Path $key)) { throw "חסר מפתח SSH: $key" }
$sshOpts = @("-i", $key, "-o", "StrictHostKeyChecking=accept-new", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20")
$target = "root@$ServerIp"

Write-Host "→ מעתיק לשרת..."
& scp @sshOpts $pkg "${target}:/tmp/th.tgz"; if ($LASTEXITCODE) { throw "ההעתקה לשרת נכשלה (בדוק את הכתובת ושמפתח ה-SSH הוגדר בשרת)" }
& scp @sshOpts $envFile "${target}:/tmp/th.env"; if ($LASTEXITCODE) { throw "העתקת ההגדרות נכשלה" }

Write-Host "→ מתקין ומפעיל בשרת (בפעם הראשונה 3–6 דקות)..."
$remote = "set -e; " +
    "command -v docker >/dev/null 2>&1 || (curl -fsSL https://get.docker.com | sh); " +
    "mkdir -p /opt/ticket-hunter && cd /opt/ticket-hunter; " +
    "tar -xzf /tmp/th.tgz && rm /tmp/th.tgz; " +
    "tr -d '\r' < /tmp/th.env > .env && rm /tmp/th.env && chmod 600 .env; " +
    "docker compose up -d --build; docker compose ps"
& ssh @sshOpts $target $remote; if ($LASTEXITCODE) { throw "ההפעלה בשרת נכשלה" }

Write-Host "→ ממתין שהאתר יעלה ב-https://$($cfg.DOMAIN) ..."
for ($i = 0; $i -lt 36; $i++) {
    try {
        $h = Invoke-RestMethod "https://$($cfg.DOMAIN)/api/health" -TimeoutSec 10
        if ($h.ok) { Write-Host "✓ המערכת פועלת: https://$($cfg.DOMAIN)" -ForegroundColor Green; return }
    } catch { Start-Sleep 5 }
}
Write-Host "⚠️ האתר עוד לא עונה ב-HTTPS. בדוק: ssh root@$ServerIp 'cd /opt/ticket-hunter && docker compose logs --tail=50'" -ForegroundColor Yellow
