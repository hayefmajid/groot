Toggle file_extraction_enabled (PDF, TXT, MD). Write this PowerShell to a temp file and execute it:

$cfg_path = "$env:USERPROFILE\.claude\hooks\.groot-config.json"
$cfg = Get-Content $cfg_path | ConvertFrom-Json
if ($null -eq $cfg.file_extraction_enabled) {
    $cfg | Add-Member -NotePropertyName file_extraction_enabled -NotePropertyValue $true -Force
}
$cfg.file_extraction_enabled = -not $cfg.file_extraction_enabled
$cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
if ($cfg.file_extraction_enabled) {
    Write-Host "Extraction fichiers : ON  - PDF/TXT/MD lus et injectes dans le prompt"
} else {
    Write-Host "Extraction fichiers : OFF - chemins conserves, Claude lit les fichiers lui-meme"
}
