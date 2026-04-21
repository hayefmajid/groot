Configure the LLM provider. $ARGUMENTS: "provider" or "provider api_key". Write this PowerShell to a temp file and execute it:

$args_val = "$ARGUMENTS" -split ' '
$provider = $args_val[0].ToLower()
$api_key  = if ($args_val.Count -gt 1) { $args_val[1] } else { $null }
$valid    = @('llama','ollama','lmstudio','openai','anthropic','nvidia','groq','mistral')

if ($provider -notin $valid) {
    Write-Host "Providers disponibles :"
    Write-Host "  Local  : llama, ollama, lmstudio"
    Write-Host "  Cloud  : openai, anthropic, nvidia, groq, mistral"
    Write-Host "Usage : /groot-llm ollama"
    Write-Host "        /groot-llm openai sk-votre-cle"
    exit
}
$cfg_path = "$env:USERPROFILE\.claude\hooks\.groot-config.json"
$cfg = Get-Content $cfg_path | ConvertFrom-Json
if ($api_key) {
    $cfg.providers.$provider.api_key = $api_key
    $cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
    Write-Host "$provider : API key configuree OK"
} else {
    $cfg.llm_provider = $provider
    $cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
    $local = $provider -in 'llama','ollama','lmstudio'
    Write-Host "LLM actif : $provider  $(if ($local) { '(local)' } else { '(cloud)' })"
    Write-Host "Modele    : $($cfg.providers.$provider.model)"
    if (-not $local -and -not $cfg.providers.$provider.api_key) {
        Write-Host "ATTENTION : API key manquante -> /groot-llm $provider votre-cle"
    }
}
