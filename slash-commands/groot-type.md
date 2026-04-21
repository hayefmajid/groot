Set the compression type to $ARGUMENTS (must be "full" or "extra"). Write this PowerShell to a temp file and execute it:

$type     = "$ARGUMENTS".Trim().ToLower()
$cfg_path = "$env:USERPROFILE\.claude\hooks\.groot-config.json"

if ($type -notin 'full','extra') { Write-Host "Usage: /groot-type full  ou  /groot-type extra"; exit }
$cfg = Get-Content $cfg_path | ConvertFrom-Json
$cfg.compression_type = $type
$cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
$desc = if ($type -eq 'full') { '~20% cible (standard)' } else { '~10% cible (EXTREME)' }
Write-Host "Type compression : $($type.ToUpper())  ($desc)"
