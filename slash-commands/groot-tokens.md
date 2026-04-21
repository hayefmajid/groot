Set the minimum word count threshold to $ARGUMENTS (a positive integer). Write this PowerShell to a temp file and execute it:

$n        = [int]"$ARGUMENTS"
$cfg_path = "$env:USERPROFILE\.claude\hooks\.groot-config.json"

if ($n -lt 1) { Write-Host "Usage: /groot-tokens 20  (entier positif)"; exit }
$cfg = Get-Content $cfg_path | ConvertFrom-Json
$cfg.min_words = $n
$cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
Write-Host "Minimum mots : $n  (prompts de moins de $n mots ignores)"
