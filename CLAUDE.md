# CLAUDE.md — optimAI Project Context

> **Mode** : Phase 1 — Bootstrap + PoC, chaîne d'inférence validée
> **Dernière mise à jour** : 2026-05-19 (Session Desktop #6 — post CLI #2
> PATCH #3 validé, DEC-019 cleanup Osaurus exécuté)

## Présentation

`optimAI` est un outil personnel d'orchestration hybride "Cortex / Hands"
conçu pour réduire la consommation de tokens Claude (Desktop / CLI / API)
sur les tâches mécaniques (lectures de logs, packs de commandes shell,
diagnostics itératifs) et pour automatiser ce que Hassan exécute
aujourd'hui à la main en mode `/optimized`.

**Stack actuelle (DEC-017 + DEC-018)** :

- **Cortex** : Claude Desktop / CLI / API
- **Dispatcher** : Python 3.12 + FastMCP (à implémenter — sessions CLI #3+)
- **Hands** : `mlx_lm.server` (Apple ML Explore officiel) +
  `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` (~18 GB)
- **Communication** : MCP stdio (Cortex ↔ Dispatcher), HTTP OpenAI-compat
  (Dispatcher ↔ Hands)

Bascule depuis Osaurus le 2026-05-19 — voir DEC-016/017/018/019 et la
section "Évolution majeure 2026-05-19" de `DECISIONS.md`.

## Propriétaire

- **Nom** : Hassan Afif
- **Langue** : Français pour la conversation, Anglais pour le
  code/commentaires
- **Machine ID** : `~/.config/tbs-identity/machine-id` (partagé avec
  TBS et Bassmati)

## Règles absolues — Lire AVANT d'agir

### Fichiers à lire obligatoirement

| Priorité | Fichier | Contenu |
|----------|---------|---------|
| 🔴 | `DECISIONS.md` | Index des 19 décisions (DEC-001 → DEC-019, dont 6 superseded) |
| 🔴 | `ROADMAP.md` | Phases 1 → 4, statut courant |
| 🟡 | `decisions/DEC-*` | Détails individuels par décision |
| 🟡 | `docs/` | Architecture, patterns, troubleshooting (à venir Phase 1) |
| 🟡 | `.drafts/claude/CLI/README.md` | Convention briefs CLI + répartition Desktop/CLI/Hassan |

Si tu reprends en sortant d'un long gap : lis aussi le dernier
HANDOVER de `.drafts/claude/CLI/` (dossier gitignored, convention
Bassmati — voir section "Drafts" plus bas).

### Commandes : toujours vérifiées

**Ne JAMAIS deviner** les commandes, chemins fichiers, configurations.
Avant de proposer une commande :

1. Consulter `DECISIONS.md` et les `decisions/DEC-*` pertinentes
2. Si l'information n'est pas dans la doc, **demander à Hassan**
   plutôt que supposer

### Accès fichiers

Utiliser **MCP Filesystem** pour lire les fichiers du repo.
Base path : `/Users/hassanafif/Library/Mobile Documents/com~apple~CloudDocs/Developer/my-projects/production/optimAI/`

### Drafts (`.drafts/`)

Le dossier `.drafts/` est **gitignored** (convention Bassmati, étendue
à optimAI). Il contient les artefacts de travail transverses aux
sessions : briefs CLI, HANDOVERs entre sessions, rapports, logs de
debug, prompts utilisateur. Ces fichiers sont **partagés via iCloud
Drive** et donc disponibles sur les deux machines de Hassan (Mac
Studio + MacBook Pro), mais ne polluent pas l'historique Git.

Sous-arborescence :

- `.drafts/claude/CLI/` — briefs `CLI_PROMPT_NNN_*.md`, HANDOVERs
  Desktop→CLI / CLI→Desktop, REPORTs CLI. **Voir
  `.drafts/claude/CLI/README.md` pour la convention complète.**
- `.drafts/reports/` — logs d'incidents conservés pour traçabilité
  (ex. crash `.diag` Osaurus référencé dans DEC-016)
- `.drafts/SPECS/`, `.drafts/docs/`, `.drafts/my-prompts/` — utilisés
  ponctuellement par Hassan

### Projets liés

| Projet | Relation | Base path |
|--------|----------|-----------|
| **TBS** | Cas d'usage majeur (Swift, builds, Docker) | `.../production/TelegramBotsServer/` |
| **Bassmati** | Cas d'usage majeur (Go, Caddy, QNAP), source du pattern doc | `.../production/bassmati/` |
| **QNAP** | Cas d'usage majeur (Docker, network) | `.../production/QNAP/` |

### Repo GitHub

- **URL** : https://github.com/afifamily/optimAI (privé, créé 2026-05-17)
- **Branche** : `main`
- **Push** : opération privilégiée Hassan (DEC-009, DEC-010). CLI commit
  local uniquement.

## Méthodologie de travail avec Claude (DEC-009)

### Répartition Desktop / CLI / Hassan

| Acteur | Rôle | Périmètre |
|--------|------|-----------|
| **Claude Desktop** | Cortex / chef d'orchestre | Architecture, décisions (DEC-NNN), planification, documentation longue, briefs CLI. Écritures MCP courtes (< 200 lignes). **Pas d'exécution shell.** |
| **Claude CLI** | Hands intelligente | Bootstrap technique, implémentation Python, tests, debugging itératif, **commandes shell d'investigation et de cleanup non-destructives** (du, lsof, find, ls, brew uninstall, etc.). Garde sa faculté de penser et choisir. |
| **Hassan** | Validateur / opérateur sensible | Opérations privilégiées : `sudo`, `brew install`, `git push`, lancement `mlx_lm.server`, créations comptes/repos, validations explicites avant `rm -rf` / `rm` irréversibles, désinstallations système, opérations réseau (LAN/QNAP), gestion credentials. |

### Quand Desktop doit **déléguer** à CLI plutôt qu'exécuter via Hassan

**Leçon Desktop #6 (cleanup Osaurus, 2026-05-19)** : Desktop a fait
exécuter à Hassan ~30 commandes shell à la main pour le cleanup
Osaurus (vérif `lsof`, `du`, `find`, `brew uninstall`, etc.). Toutes
ces commandes étaient du **bootstrap technique pur** — CLI aurait pu
les batcher, exécuter, et présenter un rapport synthétique, en ne
laissant à Hassan que la validation des `rm -rf` (qui restent
opérations privilégiées DEC-009).

**Règle à appliquer dès Desktop #7** : pour toute tâche impliquant
**> 5 commandes shell d'investigation/cleanup non-destructives**,
Desktop produit un mini-brief CLI plutôt que de dérouler les commandes
en conversation. CLI exécute, demande validation Hassan aux étapes
destructives uniquement, livre un rapport.

Cas typiques candidats à déléguer à CLI :

- Cleanup d'un outil obsolète (cf. Osaurus → DEC-019)
- Diagnostic environnement (versions Python, état caches, etc.)
- Validation post-déploiement (curl + grep + count)
- Audit blacklist / config (relecture fichiers + cross-check)
- Migration entre machines (sync iCloud, vérif paths)

Cas qui restent en conversation Desktop direct :

- Question/réponse architecturale (pas de shell)
- Édition documentaire ciblée via MCP Filesystem
- Validation rapide d'un état (1-3 commandes max)
- Opérations privilégiées Hassan (qui de toute façon ne peuvent pas
  être déléguées)

### Convention briefs CLI

Documentée en détail dans `.drafts/claude/CLI/README.md`. En résumé :

- Tout passage Desktop → CLI s'accompagne d'un brief
  `.drafts/claude/CLI/CLI_PROMPT_NNN_*.md`
- Le brief contient : contexte, lectures obligatoires, prérequis,
  étapes ordonnées, sanity checks, format de rapport de fin
- CLI lit le brief, exécute en gardant son autonomie, produit un
  REPORT en fin de session
- Pour des **mini-briefs** (5-30 commandes shell, < 30 min), le brief
  peut être court (5-15 lignes) et directement collé dans la
  conversation CLI sans nécessairement créer un fichier

### Fallback Desktop → CLI

Si une écriture Desktop via MCP Filesystem échoue (timeout iCloud,
fichier verrouillé, contenu trop long), Desktop bascule immédiatement
en mode "préparation de brief CLI" sans insister.

### Diagnostic — règle issue de DEC-016

Quand on diagnostique un système fermé tiers (serveur, bibliothèque),
**prévoir un test discriminant dans la DEC elle-même**. Ne pas se
contenter d'une hypothèse plausible (cf. DEC-014 → DEC-016, ~24h
perdues sur Osaurus faute d'avoir varié plus tôt les paramètres
"modèle/template/serveur").

### Résolution de problèmes

Avant de proposer une solution :

1. Consulter les DEC-XXX (`DECISIONS.md`) et la `TROUBLESHOOTING.md`
   d'optimAI (à venir Phase 1)
2. Si lié à un cas d'usage TBS / Bassmati / QNAP, consulter le
   `DECISIONS.md` ou `TROUBLESHOOTING.md` du projet concerné
3. Si lié à l'infrastructure mlx_lm.server ou MLX, consulter `docs/`
   puis web search

## Architecture cible

```
┌─────────────────────────────────────────────────┐
│  CORTEX — Claude Desktop / CLI / API            │
│  Raisonnement de haut niveau                    │
└────────────────────┬────────────────────────────┘
                     │  MCP stdio (FastMCP)
                     ▼
┌─────────────────────────────────────────────────┐
│  DISPATCHER — Python 3.12, FastMCP server       │
│  Patterns prioritaires Phase 1 :                │
│    - optimai_diagnose (Pattern A)               │
│    - optimai_execute  (Pattern D)               │
│  Garde-fous : blacklist, sandbox, secrets       │
│  Limites : 10 iter / 5 min / 10 KB output       │
└────────────────────┬────────────────────────────┘
                     │  HTTP OpenAI-compatible
                     │  (KV cache automatique)
                     ▼
┌─────────────────────────────────────────────────┐
│  HANDS — mlx_lm.server + Qwen2.5-Coder-32B-     │
│          Instruct-4bit (~18 GB, MLX)            │
│  Loopback only 127.0.0.1:1337                   │
│  Mac Studio M2 Max 96 GB                        │
└─────────────────────────────────────────────────┘
```

Détails dans les DEC :

- DEC-001 : Architecture trois couches
- DEC-002 : Custom minimal Python (pas de framework)
- DEC-005 : MCP stdio via FastMCP
- DEC-006 : Patterns A et D prioritaires
- DEC-007 : Limites worker
- DEC-008 : Garde-fous sécurité
- DEC-012 : Port 1337, loopback only
- DEC-017 : `mlx_lm.server` comme couche d'inférence
- DEC-018 : Qwen2.5-Coder-32B-Instruct-4bit comme worker

## Stack technique

| Composant | Technologie | Justification |
|-----------|-------------|---------------|
| Langage | Python 3.12 (épinglé via `.python-version`, DEC-011) | Écosystème MCP + httpx + asyncio, maturité 31 mois |
| Project manager | `uv` | Recommandé par le SDK MCP officiel, rapide |
| Serveur MCP | `fastmcp` | Standard de facto, ~70% des serveurs MCP |
| Client inférence | `httpx` async | OpenAI-compatible, retry/timeout natifs |
| Validation | `pydantic` v2 | Schemas Task Spec / Report (livré avec FastMCP) |
| Tests | `pytest` + `pytest-asyncio` | Standard Python, fixtures JSON pour cas réels |
| Linter | `ruff` | Vitesse, configuration simple |
| Type checker | `mypy` (optionnel Phase 1) | Sûreté de type sur les schemas |
| Serveur inférence | `mlx_lm.server` (Apple ML Explore, DEC-017) | Officiel, templates HF appliqués, KV cache |
| Modèle worker | `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` (DEC-018) | Validé en live, coding ~GPT-4o, 18 GB en 4-bit |

## Build & Run Commands

### Environnement de dev

```bash
cd "/Users/hassanafif/Library/.../production/optimAI"

# Sync deps runtime + dev (DEC-011, dev extra dans pyproject.toml)
uv sync --extra dev

# Tests et lint
uv run pytest
uv run ruff check .

# Lancement serveur MCP (placeholder en Phase 1 étape 3,
# implémenté Phase 1 étape 9 — voir ROADMAP)
uv run python -m optimai.server
```

Deps résolues (lockées dans `uv.lock`, versionné) :

| Dep | Résolu |
|-----|--------|
| fastmcp | 3.3.1 |
| httpx | 0.28.1 |
| pydantic | 2.13.4 |
| pytest (dev) | 9.0.3 |
| pytest-asyncio (dev) | 1.3.0 |
| ruff (dev) | 0.15.13 |

### Python toolchain

- **Version** : 3.12 (épinglée dans `.python-version`, DEC-011)
- **Gestion** : `uv` télécharge et gère Python lui-même, sous
  `~/.local/share/uv/python/`
- **venv** : `.venv/` créée automatiquement par `uv` à la racine, pas
  besoin de l'activer manuellement (utiliser `uv run` pour tout)

### Serveur d'inférence — `mlx_lm.server` (DEC-017)

Installé hors du venv projet via `uv tool install mlx-lm` (Python isolé,
cohérent avec `huggingface-cli` installé pareil). Lancement **manuel par
Hassan dans un terminal dédié** (DEC-009, opération privilégiée) :

```bash
mlx_lm.server \
  --model mlx-community/Qwen2.5-Coder-32B-Instruct-4bit \
  --host 127.0.0.1 \
  --port 1337 \
  --log-level INFO
```

Arrêt : `Ctrl+C` dans le terminal. Pas d'autostart en Phase 1 — à
ré-évaluer en Phase 4 (launchd LaunchAgent envisageable, cf. note
DEC-017).

**Règles dures (DEC-012 + DEC-017)** :

- ❌ JAMAIS `--host 0.0.0.0` (exposition LAN interdite — la blacklist
  bloque, défense en profondeur)
- ❌ JAMAIS de variante avec authentification désactivée explicitement
  exposée
- ✅ Le UserWarning `mlx_lm.server is not recommended for production`
  est **attendu et accepté** (cf. DEC-017, section sécurité — loopback
  only mitige)

### Modèle worker — Qwen2.5-Coder-32B-Instruct-4bit (DEC-018)

Stocké dans `~/.cache/huggingface/hub/models--mlx-community--Qwen2.5-Coder-32B-Instruct-4bit/`
(~17 GB sur disque, cache officiel HuggingFace utilisé par `mlx-lm`).

Aucune action requise pour le télécharger : `mlx_lm.server` le pull
automatiquement au premier démarrage si absent (Hassan l'a déjà fait
en CLI #2).

Le legacy `~/MLXModels/` a été supprimé en DEC-019 (Desktop #6).
**Ne pas le recréer.**

## Sécurité — Checklist

Détail complet dans DEC-008.

- [x] Blacklist commandes shell (`rm -rf /`, `sudo`, `git push`, `curl|sh`, etc.)
- [x] Anti-`mlx_lm.server --host 0.0.0.0` dans la blacklist (DEC-012+017)
- [x] Anti-`osaurus serve` en défense en profondeur dans la blacklist
      (au cas où quelqu'un essayerait de réinstaller Osaurus — DEC-019)
- [x] Sandbox chemin (workdir uniquement en écriture)
- [x] Secrets `.env` jamais dans les prompts du worker
- [x] Échec explicite, pas de fallback risqué
- [x] Limites worker (10 iter / 5 min / 10 KB)
- [ ] Sandboxing Docker (Phase 4, optionnel)
- [ ] Détection regex tokens hardcodés étendue (à enrichir Phase 1 étape 4)

## Environment Variables

Source de vérité : `.env.example`. Copier en `.env` (gitignored).

Clés critiques (Phase 1, DEC-017 + DEC-018) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `MLX_SERVER_URL` | `http://127.0.0.1:1337/v1` | Endpoint OpenAI-compatible (loopback DEC-012) |
| `MLX_SERVER_PORT` | `1337` | Port (loopback only) |
| `OPTIMAI_MODEL` | `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` | Modèle worker (DEC-018) |
| `OPTIMAI_MAX_ITERATIONS` | `10` | Limite boucle worker (DEC-007) |
| `OPTIMAI_TIMEOUT_SECONDS` | `300` | Budget temps total 5 min (DEC-007) |
| `OPTIMAI_MAX_OUTPUT_BYTES` | `10240` | Troncature output shell 10 KB (DEC-007) |
| `OPTIMAI_BLACKLIST_FILE` | `config/blacklist.txt` | Liste commandes interdites (DEC-008) |
| `OPTIMAI_SANDBOX_STRICT` | `true` | Refus toute écriture hors workdir (DEC-008) |
| `OPTIMAI_LOG_LEVEL` | `INFO` | Verbosité logs |
| `OPTIMAI_LOG_FILE` | `logs/optimai.log` | Cible des logs Dispatcher |

## Commit Convention

Adaptée de Bassmati :

```
feat: Add new feature
fix: Bug fix
docs: Documentation
refactor: Code refactoring
test: Tests
security: Security improvement
chore: Maintenance, bootstrap, deps
```

## Code Comment Standards

Adaptés de TBS et Bassmati :

- Commentaires `#` concis, en anglais
- Docstrings (`"""..."""`) sur fonctions / classes publiques
- `# WARNING:` points de sécurité sensibles (sandbox, blacklist)
- `# SYNC POINT:` logique parallèle (worker prompt ↔ implémentation)
- Densité cible : 15-25%

## Historique des sessions

| Session | Date | Machine | Focus |
|---------|------|---------|-------|
| Desktop #1 | 2026-05-17 | Mac Studio | Initiation, DEC-001 → DEC-010, structure documentaire, brief CLI #1 |
| CLI #1 | 2026-05-17 | Mac Studio | Bootstrap technique : structure projet, `pyproject.toml`, `.gitignore`, Git init + commit `9deed6e`, remote `origin` |
| Desktop #2 | 2026-05-17 | Mac Studio | DEC-011 (Python 3.12), mises à jour DECISIONS/CLAUDE/ROADMAP post-CLI #1 |
| Desktop #3 | 2026-05-17 | Mac Studio | DEC-012 (port Osaurus 1337), brief CLI_PROMPT_002 initial |
| Desktop #4 | 2026-05-17/18 | Mac Studio | Plan B (DEC-013), diag Osaurus erroné (DEC-014), Plan C (DEC-015), patches du brief CLI |
| CLI #2 (1ère partie) | 2026-05-18/19 | Mac Studio | Install Osaurus, pull Qwen3-Coder puis Qwen2.5-Coder, 3 modèles testés tous échoués, **test discriminant** qui révèle la cause réelle (Osaurus fautif) |
| Desktop #5 | 2026-05-19 | Mac Studio | Diagnostic corrigé (DEC-016), bascule mlx_lm.server (DEC-017), Qwen2.5 confirmé sur preuves (DEC-018), cleanup Osaurus proposé (DEC-019), PATCH #3 du brief CLI, handover |
| CLI #2 (2ème partie) | 2026-05-19 | Mac Studio | PATCH #3 exécuté bout-en-bout : `mlx_lm.server` validé (`prompt_tokens=39`, KV cache OK, Fibonacci OK), `.env.example` + `.env` + `config/blacklist.txt` finalisés, commit local `05d8bae` |
| Desktop #6 | 2026-05-19 | Mac Studio | DEC-019 → ✅ Accepted, cleanup Osaurus exécuté (~19 GB libérés), CLAUDE.md / ROADMAP.md / DECISIONS.md mis à jour, CLI_PROMPT_003 rédigé, leçon "déléguer commandes shell à CLI" captée |
| CLI #3 | 2026-05-19 | Mac Studio | _En cours au moment de cette mise à jour_ — `config.py` + schemas Pattern A + `shell.py` + `worker.py` + PoC scripté Pattern A sur cas XCTest TBS (brief CLI_PROMPT_003) |
