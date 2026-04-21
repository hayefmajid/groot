Display the current Groot configuration. Write this PowerShell to a temp file and execute it:

$base    = "$env:USERPROFILE\.claude\hooks"
$cfg     = Get-Content "$base\.groot-config.json" | ConvertFrom-Json
$active  = Test-Path "$base\.groot-active"
$p       = $cfg.llm_provider
$pc      = $cfg.providers.$p
$filesOn = if ($null -eq $cfg.file_extraction_enabled) { $true } else { $cfg.file_extraction_enabled }
Write-Host "--------------------------------------------"
Write-Host "  GROOT - CONFIGURATION"
Write-Host "--------------------------------------------"
Write-Host "  Compression        : $(if ($active) { 'ACTIVE' } else { 'INACTIVE' })"
Write-Host "  Min. mots          : $($cfg.min_words)"
Write-Host "  Mode validate      : $(if ($cfg.validate_mode) { 'ON (sans Enter auto)' } else { 'OFF (Enter auto)' })"
Write-Host "  Type               : $($cfg.compression_type.ToUpper()) $(if ($cfg.compression_type -eq 'full') { '(~20% cible)' } else { '(~10% cible)' })"
Write-Host "  Fichiers PDF/TXT/MD: $(if ($filesOn) { 'ON  (lus + injectes)' } else { 'OFF (conserves tels quels)' })"
Write-Host "  LLM provider       : $p $(if ($p -in 'llama','ollama','lmstudio') { '(local)' } else { '(cloud)' })"
Write-Host "  Modele             : $($pc.model)"
Write-Host "  URL                : $($pc.url)"
if ($p -notin 'llama','ollama','lmstudio') {
    Write-Host "  API Key            : $(if ($pc.api_key) { 'OK configuree' } else { 'MANQUANTE' })"
}
Write-Host "--------------------------------------------"
Write-Host "  /groot            toggle ON/OFF"
Write-Host "  /groot-type       full | extra"
Write-Host "  /groot-files      toggle extraction PDF/TXT/MD"
Write-Host "  /groot-validate   toggle Enter automatique"
Write-Host "  /groot-llm        changer de provider"
Write-Host "  /groot-tokens     seuil minimum mots"
Write-Host "  /groot-stats      statistiques"
Write-Host "--------------------------------------------"
