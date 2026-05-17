# CLAUDE.md — optimAI Project Context

> **Mode** : Phase 1 — Bootstrap + PoC
> **Dernière mise à jour** : 2026-05-17 (Session Desktop #1 — Initiation,
> capture des 10 premières décisions, structure documentaire)

## Présentation

`optimAI` est un outil personnel d'orchestration hybride "Cortex / Hands"
conçu pour réduire la consommation de tokens Claude (Desktop / CLI / API)
sur les tâches mécaniques (lectures de logs, packs de commandes shell,
diagnostics itératifs) et pour automatiser ce que Hassan exécute
aujourd'hui à la main en mode `/optimized`.

**Stack** : Python 3.12 + FastMCP + Osaurus (MLX) + Qwen3-Coder-Next 8-bit.

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
| 🔴 | `DECISIONS.md` | Index des décisions (10 décisions DEC-001 → DEC-010 actuellement) |
| 🔴 | `ROADMAP.md` | Phases 1 → 4, statut courant |
| 🟡 | `decisions/DEC-*` | Détails individuels par décision |
| 🟡 | `docs/` | Architecture, patterns, troubleshooting (à venir Phase 1) |

### Commandes : toujours vérifiées

**Ne JAMAIS deviner** les commandes, chemins fichiers, configurations.
Avant de proposer une commande :

1. Consulter `DECISIONS.md` et les `decisions/DEC-*` pertinentes
2. Si l'information n'est pas dans la doc, **demander à Hassan**
   plutôt que supposer

### Accès fichiers

Utiliser **MCP Filesystem** pour lire les fichiers du repo.
Base path : `/Users/hassanafif/Library/Mobile Documents/com~apple~CloudDocs/Developer/my-projects/production/optimAI/`

### Projets liés

| Projet | Relation | Base path |
|--------|----------|-----------|
| **TBS** | Cas d'usage majeur (Swift, builds, Docker) | `.../production/TelegramBotsServer/` |
| **Bassmati** | Cas d'usage majeur (Go, Caddy, QNAP), source du pattern doc | `.../production/bassmati/` |
| **QNAP** | Cas d'usage majeur (Docker, network) | `.../production/QNAP/` |

### Repo GitHub

- **URL** : https://github.com/afifamily/optimAI (privé, créé 2026-05-17)
- **Branche** : `main`
- **Premier push** : prévu après validation du commit bootstrap par Hassan

## Méthodologie de travail avec Claude (DEC-009)

### Répartition Desktop / CLI / Hassan

DEC-009 étend DEC-013 Bassmati pour optimAI :

| Acteur | Rôle | Périmètre |
|--------|------|-----------|
| **Claude Desktop** | Cortex / chef d'orchestre | Architecture, décisions, planification, documentation, briefs CLI. Écritures MCP limitées aux fichiers courts (< 200 lignes). |
| **Claude CLI** | Hands intelligente | Bootstrap technique, implémentation Python, tests, debugging itératif. Garde sa faculté de penser et choisir. |
| **Hassan** | Validateur / opérateur sensible | Décisions, opérations privilégiées (sudo, GitHub, install Osaurus, secrets). |

### Convention briefs CLI

Quand Desktop a besoin que CLI prenne le relais, il produit un brief
dans `.drafts/claude/CLI/CLI_PROMPT_NNN_*.md` avec :

- Contexte et objectif
- Prérequis (état attendu du repo avant)
- Liste précise des actions
- Critère de validation
- DEC pertinentes à référencer

CLI lit ce brief en début de session et exécute, tout en gardant son
autonomie de jugement.

### Fallback Desktop → CLI

Si une écriture Desktop via MCP Filesystem échoue (timeout iCloud,
fichier verrouillé, contenu trop long), Desktop bascule immédiatement
en mode "préparation de brief CLI" sans insister.

### Résolution de problèmes

Avant de proposer une solution :

1. Consulter les DEC-XXX (`DECISIONS.md`) et la `TROUBLESHOOTING.md`
   d'optimAI (à venir Phase 1)
2. Si lié à un cas d'usage TBS / Bassmati / QNAP, consulter le
   `DECISIONS.md` ou `TROUBLESHOOTING.md` du projet concerné
3. Si lié à l'infrastructure Osaurus ou MLX, consulter `docs/` puis
   web search

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
                     │  + session_id (KV cache)
                     ▼
┌─────────────────────────────────────────────────┐
│  HANDS — Osaurus + Qwen3-Coder-Next 8-bit MLX   │
│  Tool-calling natif, exécution shell sandbox    │
│  Mac Studio M2 Max 96 GB                         │
└─────────────────────────────────────────────────┘
```

Détails dans les DEC :
- DEC-001 : Architecture trois couches
- DEC-002 : Custom minimal Python (pas de framework)
- DEC-003 : Osaurus + MLX
- DEC-004 : Qwen3-Coder-Next 8-bit
- DEC-005 : MCP stdio via FastMCP
- DEC-006 : Patterns A et D prioritaires
- DEC-007 : Limites worker
- DEC-008 : Garde-fous sécurité

## Stack technique

| Composant | Technologie | Justification |
|-----------|-------------|---------------|
| Langage | Python 3.12+ | Écosystème MCP + Osaurus client + asyncio |
| Project manager | `uv` | Recommandé par le SDK MCP officiel, rapide |
| Serveur MCP | `fastmcp` | Standard de facto, ~70% des serveurs MCP |
| Client Osaurus | `httpx` async | OpenAI-compatible, retry/timeout natifs |
| Validation | `pydantic` v2 | Schemas Task Spec / Report (livré avec FastMCP) |
| Tests | `pytest` | Standard Python, fixtures JSON pour cas réels |
| Linter | `ruff` | Vitesse, configuration simple |
| Type checker | `mypy` (optionnel Phase 1) | Sûreté de type sur les schemas |

## Build & Run Commands

> **Note** : commandes définitives à compléter après bootstrap CLI
> (CLI_PROMPT_001). Cette section sera enrichie par la session CLI #1.

### Environnement de dev (placeholder)

```bash
cd "/Users/hassanafif/.../production/optimAI"
uv sync                          # Install deps
uv run pytest                    # Run tests
uv run python -m optimai.server  # Run MCP server (stdio)
```

### Osaurus (à installer en Phase 1 step 3)

```bash
# Installation via Homebrew (à confirmer après web search)
# Pull modèle :
osaurus pull mlx-community/Qwen3-Coder-Next-8bit
osaurus serve                    # http://127.0.0.1:8080
```

## Sécurité — Checklist

Détail complet dans DEC-008.

- [x] Blacklist commandes shell (`rm -rf /`, `sudo`, `git push`, etc.)
- [x] Sandbox chemin (workdir uniquement en écriture)
- [x] Secrets `.env` jamais dans les prompts du worker
- [x] Échec explicite, pas de fallback risqué
- [x] Limites worker (10 iter / 5 min / 10 KB)
- [ ] Sandboxing Docker (Phase 4, optionnel)
- [ ] Détection regex tokens hardcodés (à implémenter Phase 1 step 4)

## Environment Variables

Voir `.env.example` (à créer dans CLI_PROMPT_001) pour la liste
complète.

Clés critiques (Phase 1) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `OSAURUS_URL` | `http://127.0.0.1:8080/v1` | Endpoint OpenAI-compatible |
| `OPTIMAI_MODEL` | `qwen3-coder-next-8bit` | Modèle worker |
| `OPTIMAI_MAX_ITERATIONS` | `10` | Limite boucle worker |
| `OPTIMAI_TIMEOUT_SECONDS` | `300` | Budget temps total (5 min) |
| `OPTIMAI_MAX_OUTPUT_BYTES` | `10240` | Troncature output shell |
| `OPTIMAI_BLACKLIST_FILE` | `config/blacklist.txt` | Liste commandes interdites |
| `OPTIMAI_LOG_LEVEL` | `INFO` | Verbosité logs |

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
| Desktop #1 | 2026-05-17 | (à compléter) | Initiation, DEC-001 → DEC-010, structure documentaire, brief CLI #1 |
