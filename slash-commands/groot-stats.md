Display compression statistics. Write this PowerShell to a temp file and execute it:

$f = "$env:USERPROFILE\.claude\hooks\groot-stats.jsonl"
if (-not (Test-Path $f)) { Write-Host "Aucune stat disponible."; exit }
$entries    = Get-Content $f | ForEach-Object { $_ | ConvertFrom-Json }
$total      = $entries.Count
$savedChars = ($entries | Measure-Object -Property saved_chars -Sum).Sum
$origChars  = ($entries | Measure-Object -Property orig_chars  -Sum).Sum
$compChars  = ($entries | Measure-Object -Property comp_chars  -Sum).Sum
$savedWords = ($entries | Measure-Object -Property orig_words  -Sum).Sum - ($entries | Measure-Object -Property comp_words -Sum).Sum
$avgRatio   = [math]::Round(($entries | Measure-Object -Property ratio_pct -Average).Average, 1)
$best  = ($entries | Sort-Object ratio_pct | Select-Object -First 1)
$worst = ($entries | Sort-Object ratio_pct | Select-Object -Last  1)
Write-Host "---------------------------------------------------"
Write-Host "  GROOT - STATISTIQUES"
Write-Host "---------------------------------------------------"
Write-Host "  Compressions totales : $total"
Write-Host "  Chars economises     : $savedChars  ($origChars -> $compChars)"
Write-Host "  Mots economises      : $savedWords"
Write-Host "  Ratio moyen          : $avgRatio%"
Write-Host "  Meilleure            : $($best.ratio_pct)%  $($best.preview.Substring(0,[Math]::Min(40,$best.preview.Length)))"
Write-Host "  Moins bonne          : $($worst.ratio_pct)% $($worst.preview.Substring(0,[Math]::Min(40,$worst.preview.Length)))"
Write-Host "---------------------------------------------------"
$last10 = $entries | Select-Object -Last 10
Write-Host "  Dernieres compressions :"
foreach ($e in $last10) {
    $ts = $e.ts.Substring(5,11)
    $w  = "$($e.orig_words)->$($e.comp_words)"
    $r  = "$($e.ratio_pct)%"
    $p2 = $e.preview.Substring(0,[Math]::Min(30,$e.preview.Length))
    Write-Host "  $ts  $w  $r  $p2"
}
