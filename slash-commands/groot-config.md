Configure a specific Groot setting. $ARGUMENTS: "key value". Write this PowerShell to a temp file and execute it:

$parts    = "$ARGUMENTS" -split ' ', 2
$key      = $parts[0]
$val      = if ($parts.Count -gt 1) { $parts[1] } else { "" }
$cfg_path = "$env:USERPROFILE\.claude\hooks\.groot-config.json"
$cfg      = Get-Content $cfg_path | ConvertFrom-Json

switch ($key) {
    "min_words"              { $cfg.min_words = [int]$val }
    "compression_type"       { $cfg.compression_type = $val }
    "validate_mode"          { $cfg.validate_mode = ($val -eq 'true') }
    "file_extraction_enabled" { $cfg.file_extraction_enabled = ($val -eq 'true') }
    default                  { Write-Host "Cles valides: min_words, compression_type, validate_mode, file_extraction_enabled"; exit }
}
$cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
Write-Host "Config mise a jour : $key = $val"
