# Checks the GitHub token used by cron-job.org. The token is typed here and never saved or shown.
$sec = Read-Host "Paste the github_pat_ token here and press Enter (it will not be shown)" -AsSecureString
$tok = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)).Trim()
if ($tok -like "Bearer *") { $tok = $tok.Substring(7).Trim() }
Write-Host ""
Write-Host ("Token length: {0} characters, starts with github_pat_: {1}" -f $tok.Length, $tok.StartsWith("github_pat_"))
$h = @{ Authorization = "Bearer $tok"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28"; "User-Agent" = "ticket-hunter-cron" }
$base = "https://api.github.com/repos/idannelson69-hub/ticket-hunter"

function Try-Call($label, $method, $uri, $body) {
    try {
        if ($body) { $r = Invoke-WebRequest -UseBasicParsing -Method $method -Headers $h -ContentType "application/json" -Body $body -Uri $uri }
        else { $r = Invoke-WebRequest -UseBasicParsing -Method $method -Headers $h -Uri $uri }
        Write-Host ("[{0}] OK {1}" -f $label, $r.StatusCode) -ForegroundColor Green
    } catch {
        $resp = $_.Exception.Response
        $code = if ($resp) { $resp.StatusCode.value__ } else { "?" }
        Write-Host ("[{0}] FAILED {1}" -f $label, $code) -ForegroundColor Red
        if ($_.ErrorDetails.Message) { Write-Host ("   GitHub said: " + $_.ErrorDetails.Message) }
        if ($resp) {
            foreach ($k in @("X-Accepted-GitHub-Permissions", "X-GitHub-SSO", "X-OAuth-Scopes")) {
                $v = $resp.Headers[$k]; if ($v) { Write-Host ("   {0}: {1}" -f $k, $v) }
            }
        }
    }
}

Try-Call "1. who am I" "Get" "https://api.github.com/user" $null
Try-Call "2. read repo" "Get" $base $null
Try-Call "3. read actions" "Get" "$base/actions/workflows" $null
Try-Call "4. start check" "Post" "$base/actions/workflows/monitor.yml/dispatches" '{"ref":"main"}'
$tok = $null
Write-Host ""
Read-Host "Press Enter to close"
