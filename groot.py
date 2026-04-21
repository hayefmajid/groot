#!/usr/bin/env python3
"""
groot.py — Hook UserPromptSubmit universel (Claude Code + Codex CLI)
=============================================================================

DÉTECTION AUTOMATIQUE DE L'ENVIRONNEMENT :
  - Codex CLI  : JSON d'entrée contient "turn_id" → mécanisme natif (reason = prompt compressé)
  - Claude Code : fallback → PowerShell SendKeys pour réinjection

MÉCANISME Claude Code :
  1. Intercepte le prompt
  2. Compresse via LLM configuré (local ou externe)
  3. Bloque le prompt original (decision="block")
  4. Injecte le texte compressé via PowerShell SendKeys
     - Mode normal   : injecte + Enter automatique
     - Mode validate : injecte SANS Enter (l'utilisateur valide manuellement)

MÉCANISME Codex CLI :
  1. Intercepte le prompt
  2. Compresse via LLM configuré
  3. Retourne decision="block" avec reason=texte_compressé
     → Codex utilise automatiquement le reason comme nouveau prompt
  (Pas de SendKeys, pas de SKIP_ONCE nécessaire)
  NOTE : Les hooks Codex CLI sont désactivés sur Windows (temporairement)

Config     : .groot-config.json
Activation : champ "active": true dans la config
Logs       : groot.log
Stats      : groot-stats.jsonl
"""

import json
import sys
import re
import base64
import subprocess
import urllib.request
import urllib.error
import datetime
from pathlib import Path

# Force UTF-8 Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

# ─── CONFIG ────────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
SKIP_ONCE  = BASE_DIR / ".compress-skip-once"
MARKER     = BASE_DIR / ".groot-active"
LOG        = BASE_DIR / "groot.log"
STATS      = BASE_DIR / "groot-stats.jsonl"
CONFIG_F   = BASE_DIR / ".groot-config.json"

TIMEOUT    = 90
MAX_TOKENS = 2048
SENDKEYS_DELAY_MS = 800

# ─── CAPTURE HWND TERMINAL (sécurité fenêtre) ─────────────────────────────────
# On capture la fenêtre active DÈS le démarrage du hook (avant la compression)
# pour garantir que SendKeys colle dans le bon terminal même si l'utilisateur
# a cliqué ailleurs pendant les quelques secondes de traitement LLM.

def _get_terminal_hwnd() -> int:
    """
    Retourne le HWND de la console du processus courant.
    GetConsoleWindow() est l'API correcte : elle retourne la fenêtre de la
    console à laquelle CE processus est attaché — c'est-à-dire le terminal
    Claude Code qui a lancé le hook, même si l'utilisateur a cliqué ailleurs.
    Fallback : GetForegroundWindow() si pas de console (terminal moderne).
    """
    try:
        import ctypes
        # 1er choix : console window du processus courant (fiable)
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            return hwnd
        # Fallback : fenêtre active (Windows Terminal / WT ne remonte pas GetConsoleWindow)
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return 0

_TERMINAL_HWND: int = 0   # capturé dans main() avant tout traitement

# ─── TYPES FICHIERS ────────────────────────────────────────────────────────────

IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"})
PDF_EXTS   = frozenset({".pdf"})
TEXT_EXTS  = frozenset({".txt", ".csv", ".md"})
MIME_MAP   = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif",  ".webp": "image/webp",  ".bmp": "image/bmp",
    ".tiff": "image/tiff"
}

# ─── GESTION FICHIERS (placeholders) ──────────────────────────────────────────

# Patterns pour détecter les références de fichiers inline dans le prompt
_FILE_PATTERNS = [
    # Chemins Windows entre guillemets (avec espaces) : "C:\path with spaces\file.pdf"
    r'"[A-Za-z]:\\[^"]+\.(?:pdf|png|jpg|jpeg|gif|webp|svg|bmp|tiff|docx|xlsx|pptx|txt|csv|zip|rar)"',
    # Chemins Windows sans guillemets : C:\path\file.pdf
    r'[A-Za-z]:\\[^\s\n"]+\.(?:pdf|png|jpg|jpeg|gif|webp|svg|bmp|tiff|docx|xlsx|pptx|txt|csv|zip|rar)',
    # Chemins Unix/Mac entre guillemets (avec espaces) : "/path/to file.pdf"
    r'"/[^"]+\.(?:pdf|png|jpg|jpeg|gif|webp|svg|bmp|tiff|docx|xlsx|pptx|txt|csv|zip|rar)"',
    # Chemins Unix/Mac sans guillemets : /path/to/file.pdf
    r'/[^\s\n"]+\.(?:pdf|png|jpg|jpeg|gif|webp|svg|bmp|tiff|docx|xlsx|pptx|txt|csv|zip|rar)',
    # Mentions @fichier
    r'@[^\s\n]+\.(?:pdf|png|jpg|jpeg|gif|webp|docx|xlsx)',
    # Images markdown : ![alt](path)
    r'!\[[^\]]*\]\([^)]+\)',
    # Data URIs base64 (images encodées)
    r'data:(?:image|application)/[^;]+;base64,[A-Za-z0-9+/=]{20,}',
]
_FILE_RE = re.compile('|'.join(f'(?:{p})' for p in _FILE_PATTERNS), re.IGNORECASE)
_PH_PREFIX = "<<<TSLIM_"
_PH_SUFFIX = ">>>"

def extract_files(text: str) -> tuple:
    """Remplace les références fichiers par des placeholders. Retourne (texte_modifié, refs_originales)."""
    refs = []
    def _replace(m):
        refs.append(m.group(0))
        return f"{_PH_PREFIX}{len(refs)-1}{_PH_SUFFIX}"
    return _FILE_RE.sub(_replace, text), refs

def restore_files(text: str, refs: list) -> str:
    """Restaure les références originales depuis les placeholders."""
    for i, ref in enumerate(refs):
        text = text.replace(f"{_PH_PREFIX}{i}{_PH_SUFFIX}", ref)
    return text

# ─── EXTRACTION CONTENU FICHIERS ───────────────────────────────────────────────

def _vision_url(cfg: dict) -> str:
    """Retourne l'URL du modèle vision.
    Si llama.cpp local port 8080 → vision sur port 8081 (Qwen3-VL).
    Sinon utilise le même provider (OpenAI, Anthropic, etc. supportent nativement le vision)."""
    provider = cfg.get("llm_provider", "llama")
    url = cfg.get("providers", {}).get(provider, {}).get("url", "")
    if ":8080/" in url:
        return url.replace(":8080/", ":8081/")
    return url

def vision_extract(img_b64: str, mime: str, user_text: str, cfg: dict) -> str | None:
    """Envoie une image au LLM vision et retourne le texte extrait."""
    provider = cfg.get("llm_provider", "llama")
    p = cfg.get("providers", {}).get(provider, {})
    url = _vision_url(cfg)
    model = p.get("model", "")
    ctx = f"Contexte : {user_text.strip()}\n\n" if user_text.strip() else ""
    instruction = (
        f"{ctx}Extrais tout le texte visible dans cette image. "
        "Si c'est un document (facture, rapport, formulaire), retourne son contenu complet et structuré. "
        "Réponds UNIQUEMENT avec le texte extrait, sans commentaire ni préambule."
    )
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            {"type": "text", "text": instruction}
        ]}],
        "max_tokens": 2048, "temperature": 0.1, "stream": False
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if p.get("api_key"):
        headers["Authorization"] = f"Bearer {p['api_key']}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"].strip() or None

def pdf_extract(path: str) -> str | None:
    """Extrait le texte d'un PDF via pypdf (pip install pypdf)."""
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        pages = [(p.extract_text() or "").strip() for p in reader.pages]
        text = "\n\n".join(p for p in pages if p)
        return text[:4000] + "\n...[tronqué]" if len(text) > 4000 else text or None
    except ImportError:
        log("[PDF] pypdf absent — pip install pypdf --break-system-packages")
    except Exception as e:
        log(f"[PDF ERROR] {e}")
    return None

def text_extract(path: str) -> str | None:
    """Lit un fichier texte brut."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read().strip()
        return content[:4000] + "\n...[tronqué]" if len(content) > 4000 else content or None
    except Exception as e:
        log(f"[TXT ERROR] {e}")
        return None

def enrich_prompt(prompt: str, cfg: dict) -> str:
    """
    Détecte les fichiers dans le prompt et enrichit le texte :
    - Image  → garde le chemin (Claude voit l'image) + ajoute description vision
    - PDF    → remplace le chemin par le texte extrait
    - Texte  → remplace le chemin par le contenu
    """
    file_matches = list(_FILE_RE.finditer(prompt))
    if not file_matches:
        return prompt

    user_text = _FILE_RE.sub("", prompt).strip()
    image_additions = []

    for m in file_matches:
        raw_path = m.group(0)
        clean_path = raw_path.strip('"\'')
        suffix = Path(clean_path).suffix.lower()

        if suffix in IMAGE_EXTS:
            try:
                log(f"[VISION] Analyse : {Path(clean_path).name}")
                with open(clean_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                mime = MIME_MAP.get(suffix, "image/png")
                desc = vision_extract(b64, mime, user_text, cfg)
                if desc:
                    image_additions.append(f"\n[Texte extrait de {Path(clean_path).name}:]\n{desc}")
                    log(f"[VISION OK] {len(desc)} chars extraits")
                else:
                    log(f"[VISION] Aucun texte extrait de {Path(clean_path).name}")
            except FileNotFoundError:
                log(f"[VISION] Introuvable : {clean_path}")
            except Exception as e:
                log(f"[VISION ERROR] {e}")

        elif suffix in PDF_EXTS:
            try:
                log(f"[PDF] Extraction : {Path(clean_path).name}")
                text = pdf_extract(clean_path)
                if text:
                    replacement = f"[Contenu PDF — {Path(clean_path).name}:]\n{text}"
                    prompt = prompt.replace(raw_path, replacement)
                    log(f"[PDF OK] {len(text)} chars extraits")
            except Exception as e:
                log(f"[PDF ERROR] {e}")

        elif suffix in TEXT_EXTS:
            try:
                content = text_extract(clean_path)
                if content:
                    replacement = f"[Contenu de {Path(clean_path).name}:]\n{content}"
                    prompt = prompt.replace(raw_path, replacement)
            except Exception as e:
                log(f"[TXT ERROR] {e}")

    # Ajouter les descriptions d'images à la fin (le chemin original est conservé)
    return prompt + "".join(image_additions)

# ─── SYSTEM PROMPTS ────────────────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "full": (
        "Tu es un COMPRESSEUR DE PROMPT.\n"
        "RÈGLE ABSOLUE : détecte la langue du texte et compresse-le dans CETTE MÊME LANGUE. Ne traduis JAMAIS.\n"
        "Cible : 20% de la longueur originale maximum.\n"
        "SUPPRIME : politesse, transitions, redondances, meta-commentaires, explications évidentes, emphases molles.\n"
        "COMPRESSE : phrases complètes → style télégraphique. Utilise -> & / + = ~ pour réduire.\n"
        "PRÉSERVE ABSOLUMENT : chiffres, dates, montants, URLs, codes techniques, noms propres, "
        "négations logiques, termes métier.\n"
        "PRÉSERVE ABSOLUMENT les tokens <<<TSLIM_N>>> — ne les modifie, déplace ou supprime JAMAIS.\n"
        "Réponds UNIQUEMENT avec le texte compressé. ZÉRO préambule. ZÉRO commentaire."
    ),
    "extra": (
        "Tu es un COMPRESSEUR EXTRÊME.\n"
        "RÈGLE ABSOLUE : détecte la langue du texte et compresse-le dans CETTE MÊME LANGUE. Ne traduis JAMAIS.\n"
        "Cible : 10% de la longueur originale. Sois brutal — supprime tout sauf l'essentiel absolu.\n"
        "SUPPRIME : tout ce qui n'est pas critique pour l'action demandée.\n"
        "PRÉSERVE UNIQUEMENT : chiffres, noms propres, termes techniques, négations critiques.\n"
        "PRÉSERVE ABSOLUMENT les tokens <<<TSLIM_N>>> — ne les modifie, déplace ou supprime JAMAIS.\n"
        "Style : mots-clés uniquement, pas de phrases. Maximum de densité sémantique.\n"
        "Réponds UNIQUEMENT avec le texte compressé. ZÉRO préambule. ZÉRO commentaire."
    )
}

# ─── LOGGING ───────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    try:
        with open(LOG, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def log_stats(original: str, compressed: str, provider: str, comp_type: str) -> None:
    entry = {
        "ts":         datetime.datetime.now().isoformat(timespec="seconds"),
        "orig_chars": len(original),
        "comp_chars": len(compressed),
        "orig_words": len(original.split()),
        "comp_words": len(compressed.split()),
        "ratio_pct":  round(len(compressed) / len(original) * 100, 1),
        "saved_chars":len(original) - len(compressed),
        "provider":   provider,
        "type":       comp_type,
        "preview":    original[:60].replace("\n", " ")
    }
    try:
        with open(STATS, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ─── CONFIG ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    defaults = {
        "active": False, "min_words": 10, "validate_mode": False,
        "compression_type": "full", "llm_provider": "llama",
        # ── Extraction fichiers (PDF, TXT, MD) ──────────────────────────────
        # true  → les fichiers référencés dans le prompt sont lus et injectés
        # false → les chemins sont préservés tels quels, Claude les lit lui-même
        "file_extraction_enabled": True,
        "providers": {
            "llama": {"url": "http://localhost:8080/v1/chat/completions",
                      "model": "gemma-4-26b-a4b", "api_key": None, "type": "openai"}
        }
    }
    try:
        with open(CONFIG_F, encoding="utf-8") as f:
            return {**defaults, **json.load(f)}
    except Exception:
        return defaults

# ─── COMPRESSION ───────────────────────────────────────────────────────────────

def compress_openai(text: str, provider_cfg: dict, system_prompt: str) -> str | None:
    payload = json.dumps({
        "model":    provider_cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Compresse ce texte :\n\n<<<\n{text}\n>>>"}
        ],
        "max_tokens":  MAX_TOKENS,
        "temperature": 0.1,
        "stream":      False,
        "thinking":    False
    }, ensure_ascii=False).encode("utf-8")

    headers = {"Content-Type": "application/json; charset=utf-8"}
    if provider_cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {provider_cfg['api_key']}"

    req = urllib.request.Request(
        provider_cfg["url"], data=payload, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip() or None

def compress_anthropic(text: str, provider_cfg: dict, system_prompt: str) -> str | None:
    payload = json.dumps({
        "model":      provider_cfg["model"],
        "max_tokens": MAX_TOKENS,
        "system":     system_prompt,
        "messages":   [{"role": "user", "content": f"Compresse ce texte :\n\n<<<\n{text}\n>>>"}]
    }, ensure_ascii=False).encode("utf-8")

    headers = {
        "Content-Type":      "application/json",
        "x-api-key":         provider_cfg.get("api_key", ""),
        "anthropic-version": "2023-06-01"
    }
    req = urllib.request.Request(
        provider_cfg["url"], data=payload, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body["content"][0]["text"].strip() or None

def compress(text: str, cfg: dict) -> str | None:
    provider_name = cfg.get("llm_provider", "llama")
    providers     = cfg.get("providers", {})
    provider_cfg  = providers.get(provider_name, {})
    comp_type     = cfg.get("compression_type", "full")
    system_prompt = SYSTEM_PROMPTS.get(comp_type, SYSTEM_PROMPTS["full"])

    if not provider_cfg:
        log(f"[ERROR] Provider '{provider_name}' non configuré")
        return None

    import time
    retries = 3
    for attempt in range(1, retries + 1):
        try:
            if provider_cfg.get("type") == "anthropic":
                return compress_anthropic(text, provider_cfg, system_prompt)
            else:
                return compress_openai(text, provider_cfg, system_prompt)
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < retries:
                log(f"[RETRY {attempt}/{retries}] {provider_name} 503 — attente 2s...")
                time.sleep(2)
                continue
            log(f"[COMPRESS ERROR] {provider_name} HTTP {e.code}: {e.reason}")
            return None
        except urllib.error.URLError as e:
            log(f"[COMPRESS ERROR] {provider_name} injoignable : {e}")
            return None
        except Exception as e:
            log(f"[COMPRESS ERROR] {type(e).__name__}: {e}")
            return None
    return None

# ─── SENDKEYS ──────────────────────────────────────────────────────────────────

def sendkeys_to_terminal(text: str, delay_ms: int, send_enter: bool) -> None:
    """
    Colle le texte compressé dans le terminal Claude Code via presse-papiers.
    Utilise AttachThreadInput pour contourner la restriction Windows qui bloque
    SetForegroundWindow depuis un processus background — c'est la seule méthode
    fiable pour reprendre le focus même si l'utilisateur a cliqué ailleurs.
    """
    hwnd = _TERMINAL_HWND
    enter_line = '[System.Windows.Forms.SendKeys]::SendWait("{ENTER}")' if send_enter else ""

    # Échapper les guillemets pour PowerShell here-string
    text_escaped_ps = text.replace("'", "''")

    if hwnd:
        focus_block = f"""
# ── AttachThreadInput : seule méthode fiable pour voler le focus sous Windows ──
$sig = @'
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
[DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
[DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
[DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
[DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
'@
Add-Type -MemberDefinition $sig -Name WinAPI -Namespace Focus -ErrorAction SilentlyContinue
$hwnd = [IntPtr]{hwnd}
if ([Focus.WinAPI]::IsIconic($hwnd)) {{ [Focus.WinAPI]::ShowWindow($hwnd, 9) | Out-Null; Start-Sleep -Milliseconds 150 }}
$pid2 = 0
$targetThread  = [Focus.WinAPI]::GetWindowThreadProcessId($hwnd, [ref]$pid2)
$currentThread = [Focus.WinAPI]::GetCurrentThreadId()
[Focus.WinAPI]::AttachThreadInput($currentThread, $targetThread, $true)  | Out-Null
[Focus.WinAPI]::SetForegroundWindow($hwnd) | Out-Null
Start-Sleep -Milliseconds 120
[Focus.WinAPI]::AttachThreadInput($currentThread, $targetThread, $false) | Out-Null
"""
        log(f"[PASTE] AttachThreadInput + SetForegroundWindow HWND={hwnd}")
    else:
        focus_block = ""
        log("[PASTE] HWND=0 — collage sans focus forcé")

    ps_script = f"""
Start-Sleep -Milliseconds {delay_ms}
Add-Type -AssemblyName System.Windows.Forms
# ── Mettre le texte dans le presse-papiers ──
$text = @'
{text_escaped_ps}
'@
[System.Windows.Forms.Clipboard]::SetText($text.TrimEnd("`r`n"))
{focus_block}
# ── Coller via Ctrl+V ──
[System.Windows.Forms.SendKeys]::SendWait("^v")
Start-Sleep -Milliseconds 80
{enter_line}
"""
    subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    )
    mode = "avec Enter" if send_enter else "SANS Enter (validate)"
    log(f"[PASTE] Collage presse-papiers planifié dans {delay_ms}ms — {mode}")

# ─── DÉTECTION ENVIRONNEMENT ───────────────────────────────────────────────────

def detect_environment(hook_input: dict) -> str:
    """
    Retourne 'codex' si on tourne dans Codex CLI, 'claude' sinon.
    Seul Codex CLI envoie 'turn_id' dans le JSON d'entrée.
    Claude Code et Codex CLI envoient tous deux 'hook_event_name',
    donc ce champ ne peut PAS servir à discriminer.
    """
    if "turn_id" in hook_input:
        return "codex"
    return "claude"

# ─── HANDLERS PAR ENVIRONNEMENT ────────────────────────────────────────────────

def handle_claude_code(prompt: str, compressed: str, cfg: dict, words: int, ratio: float) -> None:
    """
    Claude Code : block + SendKeys pour réinjecter le texte compressé.
    SKIP_ONCE protège contre la boucle infinie.
    """
    SKIP_ONCE.touch()
    validate_mode = cfg.get("validate_mode", False)
    sendkeys_to_terminal(compressed, SENDKEYS_DELAY_MS, send_enter=not validate_mode)

    output = {
        "decision": "block",
        "reason": f"✂️ {words}→{len(compressed.split())} mots ({ratio:.0f}%) [{cfg['llm_provider']}/{cfg['compression_type']}]"
                  + (" — EN ATTENTE VALIDATION" if validate_mode else "")
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))
    log("[BLOCK/CLAUDE] prompt original bloqué, SendKeys planifié")

def handle_codex_cli(prompt: str, compressed: str, cfg: dict, words: int, ratio: float) -> None:
    """
    Codex CLI : block avec reason = texte compressé.
    Codex utilise automatiquement le reason comme nouveau prompt.
    Pas de SendKeys, pas de SKIP_ONCE nécessaire.
    """
    comp_words = len(compressed.split())
    stats_line = f"✂️ {words}→{comp_words} mots ({ratio:.0f}%) [{cfg['llm_provider']}/{cfg['compression_type']}]"
    log(f"[BLOCK/CODEX] {stats_line}")

    # En Codex CLI, validate_mode n'est pas applicable (pas de terminal à contrôler)
    # Le reason devient directement le nouveau prompt envoyé au modèle
    output = {
        "decision": "block",
        "reason": compressed  # ← Codex utilise ceci comme nouveau prompt
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))

# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # ── Capturer IMMÉDIATEMENT le HWND du terminal actif ──────────────────────
    # Le hook s'exécute depuis le terminal Claude Code — la fenêtre active EN CE
    # MOMENT est donc forcément le bon terminal. On le mémorise avant toute
    # opération longue (appel LLM) pour pouvoir y revenir après.
    global _TERMINAL_HWND
    _TERMINAL_HWND = _get_terminal_hwnd()
    log(f"[HWND] Terminal capturé : {_TERMINAL_HWND} ({'console' if _TERMINAL_HWND else 'non trouvé'})")

    raw = sys.stdin.read()
    log(f"[START] stdin {len(raw)} bytes")

    try:
        hook_input = json.loads(raw)
    except Exception as e:
        log(f"[JSON ERROR] {e}")
        print("{}")
        return

    prompt = hook_input.get("prompt", "").strip()
    if not prompt:
        log("[SKIP] prompt vide")
        print("{}")
        return

    # Ignorer les messages système internes de Claude Code / Cowork
    SYSTEM_TAGS = ("<task-notification>", "<task-id>", "<system-reminder>", "<command-message>")
    if any(tag in prompt for tag in SYSTEM_TAGS) or prompt.startswith("<"):
        log("[SKIP] message système interne détecté — ignoré")
        print("{}")
        return

    # Ignorer les commandes techniques : chemins ~/.claude, SKILL.md, slash commands, /compress
    TECHNICAL_MARKERS = ("~/.claude", "SKILL.md", "CLAUDE.md", ".claude/", "/compress", "/clear", "/help")
    if any(m in prompt for m in TECHNICAL_MARKERS) or prompt.startswith("/"):
        log("[SKIP] commande technique détectée — ignorée")
        print("{}")
        return

    # Ignorer les prompts base64 bruts (image déjà encodée dans le texte par Claude Code)
    # Ces payloads sont énormes et non traitables directement
    if "base64," in prompt and len(prompt) > 5000:
        log(f"[SKIP] base64 brut détecté ({len(prompt)} chars) — ignoré")
        print("{}")
        return

    env = detect_environment(hook_input)
    log(f"[ENV] détecté : {env}")

    # Anti-boucle infinie (Claude Code uniquement — Codex n'a pas ce problème)
    if env == "claude" and SKIP_ONCE.exists():
        age = datetime.datetime.now().timestamp() - SKIP_ONCE.stat().st_mtime
        if age < 15:
            SKIP_ONCE.unlink()
            log(f"[SKIP] prompt injecté (anti-boucle Claude Code, age={age:.1f}s)")
            print("{}")
            return
        else:
            # Fichier périmé (SendKeys a probablement raté) → on l'ignore et on continue
            SKIP_ONCE.unlink()
            log(f"[WARN] skip-once périmé ({age:.0f}s) — ignoré, compression normale")

    cfg = load_config()

    # Vérification active : JSON ET marker file
    # Si désynchronisés, le marker file fait foi (créé par /compress)
    json_active    = cfg.get("active", False)
    marker_active  = MARKER.exists()

    if json_active != marker_active:
        # Auto-réparation : on aligne le JSON sur le marker
        cfg["active"] = marker_active
        try:
            with open(CONFIG_F, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            log(f"[REPAIR] JSON désynchronisé → active={marker_active} (source: marker)")
        except Exception as e:
            log(f"[REPAIR ERROR] {e}")

    if not cfg.get("active", False):
        log("[SKIP] compression inactive")
        print("{}")
        return

    min_words = cfg.get("min_words", 10)
    words = len(prompt.split())
    if words < min_words:
        log(f"[SKIP] trop court ({words} mots < {min_words})")
        print("{}")
        return

    # ── Enrichissement fichiers (images via vision, PDF/texte via extraction) ──
    file_extraction = cfg.get("file_extraction_enabled", True)
    if file_extraction and _FILE_RE.search(prompt):
        log("[FILES] Fichiers détectés — enrichissement en cours...")
        prompt = enrich_prompt(prompt, cfg)
    elif not file_extraction and _FILE_RE.search(prompt):
        log("[FILES] Extraction désactivée — chemins conservés tels quels")

    # ── Gestion fichiers : extraire références, compresser texte seul ──────────
    text_to_compress, file_refs = extract_files(prompt)

    # Si le prompt ne contient QUE des fichiers ou trop peu de texte → pas de valeur
    text_only = text_to_compress.strip()
    if not text_only or len(text_only.split()) < min_words:
        if file_refs:
            log(f"[SKIP] fichier(s) seul(s) ou texte court ({len(text_only.split())} mots) — laissé à Claude Code")
        else:
            log(f"[SKIP] trop court après extraction fichiers ({len(text_only.split())} mots)")
        print("{}")
        return

    # Si fichier(s) présent(s) ET texte court (< 25 mots) → Claude Code gère nativement, pas de valeur
    if file_refs and len(text_only.split()) < 25:
        log(f"[SKIP] fichier + texte court ({len(text_only.split())} mots) — Claude Code lit le fichier nativement")
        print("{}")
        return

    if file_refs:
        log(f"[FILES] {len(file_refs)} référence(s) fichier extraite(s) → placeholders")

    log(f"[COMPRESS] {len(text_to_compress)} chars, {len(text_to_compress.split())} mots — provider={cfg['llm_provider']} type={cfg['compression_type']} env={env}")

    compressed_text = compress(text_to_compress, cfg)
    if not compressed_text:
        log("[FALLBACK] compression échouée, prompt original envoyé")
        print("{}")
        return

    # Si le texte compressé est trop court ou identique → pas de valeur ajoutée
    if len(compressed_text.split()) < 4:
        log(f"[SKIP] texte compressé trop court ({len(compressed_text.split())} mots) — prompt original envoyé")
        print("{}")
        return

    # Restaurer les références fichiers à leurs positions originales
    compressed = restore_files(compressed_text, file_refs)

    ratio = len(compressed_text) / len(text_to_compress) * 100
    log(f"[OK] {len(prompt)} → {len(compressed)} chars ({ratio:.0f}%) | {words} → {len(compressed.split())} mots" +
        (f" | {len(file_refs)} fichier(s) preservé(s)" if file_refs else ""))

    log_stats(prompt, compressed, cfg["llm_provider"], cfg["compression_type"])

    if env == "codex":
        handle_codex_cli(prompt, compressed, cfg, words, ratio)
    else:
        handle_claude_code(prompt, compressed, cfg, words, ratio)


if __name__ == "__main__":
    main()
