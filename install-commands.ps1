$base = "......"
$src  = "$base\slash-commands"
$dst  = "$env:USERPROFILE\.claude\commands"

New-Item -ItemType Directory -Path $dst -Force | Out-Null

# ── Supprimer anciens slash commands compress-* (migration → groot) ────────────
Get-ChildItem "$dst\compress*.md" -ErrorAction SilentlyContinue | Remove-Item -Force
Write-Host "OK - anciens compress-*.md supprimes de $dst"

# ── Slash commands /groot ──────────────────────────────────────────────────────
Copy-Item "$src\groot.md"          "$dst\groot.md"          -Force
Copy-Item "$src\groot-stats.md"    "$dst\groot-stats.md"    -Force
Copy-Item "$src\groot-show.md"     "$dst\groot-show.md"     -Force
Copy-Item "$src\groot-config.md"   "$dst\groot-config.md"   -Force
Copy-Item "$src\groot-type.md"     "$dst\groot-type.md"     -Force
Copy-Item "$src\groot-validate.md" "$dst\groot-validate.md" -Force
Copy-Item "$src\groot-llm.md"      "$dst\groot-llm.md"      -Force
Copy-Item "$src\groot-tokens.md"   "$dst\groot-tokens.md"   -Force
Copy-Item "$src\groot-files.md"    "$dst\groot-files.md"    -Force

# ── Script principal + config → dossier hooks Claude ──────────────────────────
$dstHook = "$env:USERPROFILE\.claude\hooks"
New-Item -ItemType Directory -Path $dstHook -Force | Out-Null

Copy-Item "$base\groot.py" 
