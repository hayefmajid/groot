$base     = "$env:USERPROFILE\.claude\hooks"
$cfg_path = "$base\.groot-config.json"
$marker   = "$base\.groot-active"

New-Item -ItemType Directory -Path $base -Force | Out-Null

# Creer config par defaut si absente
if (-not (Test-Path $cfg_path)) {
    @{
        active                  = $false
        min_words               = 10
        validate_mode           = $false
        compression_type        = "full"
        file_extraction_enabled = $true
        llm_provider            = "llama"
        providers = @{
            llama    = @{ url = "http://localhost:8080/v1/chat/completions"; model = "gemma-4-26b-a4b";        api_key = $null; type = "openai" }
            ollama   = @{ url = "http://localhost:11434/v1/chat/completions"; model = "llama3.2";              api_key = $null; type = "openai" }
            lmstudio = @{ url = "http://localhost:1234/v1/chat/completions"; model = "local-model";           api_key = $null; type = "openai" }
            openai   = @{ url = "https://api.openai.com/v1/chat/completions"; model = "gpt-4o-mini";          api_key = "";    type = "openai" }
            anthropic= @{ url = "https://api.anthropic.com/v1/messages";     model = "claude-haiku-4-5-20251001"; api_key = ""; type = "anthropic" }
            groq     = @{ url = "https://api.groq.com/openai/v1/chat/completions"; model = "llama-3.1-8b-instant"; api_key = ""; type = "openai" }
            mistral  = @{ url = "https://api.mistral.ai/v1/chat/completions"; model = "mistral-small-latest"; api_key = "";   type = "openai" }
        }
    } | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8
    Write-Host "Config initialisee : $cfg_path"
}

$cfg = Get-Content $cfg_path -Raw | ConvertFrom-Json
$now = -not [bool]$cfg.active
$cfg.active = $now
$cfg | ConvertTo-Json -Depth 5 | Set-Content $cfg_path -Encoding UTF8

if ($now) {
    New-Item -ItemType File -Path $marker -Force | Out-Null
    Write-Host "I AM GROOT : ACTIVE  (compression ON)"
} else {
    if (Test-Path $marker) { Remove-Item $marker -Force }
    Write-Host "I AM GROOT : INACTIVE (compression OFF)"
}
