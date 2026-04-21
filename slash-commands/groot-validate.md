Toggle the validate_mode setting (inject with or without auto-Enter). Write this PowerShell to a temp file and execute it:

$cfg_path = "$env:USERPROFILE\.claude\hooks\.groot-config.json"
$cfg = Get-Content $cfg_path | ConvertFrom-Json
$cfg.validate_mode = -not $cfg.validate_mode
$cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
if ($cfg.validate_mode) {
    Write-Host "Mode validate : ON - texte colle SANS Enter, vous validez manuellement"
} else {
    Write-Host "Mode validate : OFF - Enter automatique apres collage"
}
