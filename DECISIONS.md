# DECISIONS — optimAI

Index des décisions architecturales. Chaque décision est dans son propre fichier
sous `decisions/DEC-NNN-slug.md`.

## Convention

- ID séquentiel : `DEC-NNN` (zero-padded)
- Slug : kebab-case anglais court
- Statut : ✅ Accepted | 🔄 In progress | 📝 Proposed | ⛔ Deprecated | 🔁 Superseded
- Date au format ISO dans le fichier individuel

Pour ajouter une nouvelle décision, voir `decisions/README.md`.

## Index

| ID | Titre | Statut | Date |
|----|-------|--------|------|
| [DEC-001](decisions/DEC-001-cortex-hands-architecture.md) | Architecture Cortex / Dispatcher / Hands | ✅ | 2026-05-17 |
| [DEC-002](decisions/DEC-002-custom-minimal-python.md) | Custom minimal Python (pas LangGraph/Smolagents) | ✅ | 2026-05-17 |
| [DEC-003](decisions/DEC-003-osaurus-over-ollama.md) | Osaurus + MLX comme couche d'inférence | 🔁 | 2026-05-17 |
| [DEC-004](decisions/DEC-004-qwen3-coder-next.md) | Qwen3-Coder-Next 8-bit MLX (worker) | ✅ | 2026-05-17 |
| [DEC-005](decisions/DEC-005-mcp-stdio-local.md) | MCP stdio local via FastMCP | ✅ | 2026-05-17 |
| [DEC-006](decisions/DEC-006-patterns-priority-A-D.md) | Patterns prioritaires — A (Diagnose) + D (Execute) | ✅ | 2026-05-17 |
| [DEC-007](decisions/DEC-007-loop-limits.md) | Limites worker — 10 itérations / 5 min / 10 KB output | ✅ | 2026-05-17 |
| [DEC-008](decisions/DEC-008-security-guardrails.md) | Garde-fous sécurité — blacklist, sandbox path, secrets isolés | ✅ | 2026-05-17 |
| [DEC-009](decisions/DEC-009-meta-architecture-desktop-cli.md) | Méta-architecture — Desktop = Cortex, CLI = Hands intelligente | ✅ | 2026-05-17 |
| [DEC-010](decisions/DEC-010-git-private-repo.md) | Git activé, repo privé GitHub | ✅ | 2026-05-17 |
| [DEC-011](decisions/DEC-011-python-3-12-baseline.md) | Python 3.12 baseline (`.python-version` épinglée) | ✅ | 2026-05-17 |
| [DEC-012](decisions/DEC-012-osaurus-port-1337.md) | Port Osaurus 1337, écoute 127.0.0.1, `--expose` interdit | ✅ | 2026-05-17 |
| [DEC-013](decisions/DEC-013-plan-b-qwen3-coder-30b-a3b.md) | Plan B activé — Qwen3-Coder-30B-A3B-Instruct-4bit (worker effectif) | 🔁 | 2026-05-17 |
| [DEC-014](decisions/DEC-014-osaurus-template-limitation.md) | Osaurus — limite sur templates Jinja externes complexes + règles d'usage | 🔁 | 2026-05-17 |
| [DEC-015](decisions/DEC-015-qwen2-5-coder-32b-instruct.md) | Plan C — Qwen2.5-Coder-32B-Instruct-4bit (worker effectif) | 🔁 | 2026-05-17 |
| [DEC-016](decisions/DEC-016-osaurus-diagnostic-corrected.md) | Diagnostic Osaurus corrigé — serveur fautif, pas les modèles | ✅ | 2026-05-19 |
| [DEC-017](decisions/DEC-017-mlx-lm-server-replaces-osaurus.md) | Bascule Osaurus → `mlx_lm.server` comme serveur d'inférence | ✅ | 2026-05-19 |
| [DEC-018](decisions/DEC-018-qwen2-5-coder-32b-confirmed.md) | Qwen2.5-Coder-32B-Instruct-4bit confirmé comme worker (Phase 1) | ✅ | 2026-05-19 |
| [DEC-019](decisions/DEC-019-osaurus-cleanup.md) | Cleanup Osaurus de la machine | 📝 | 2026-05-19 |

## Décisions à venir

_Aucune décision en cours de rédaction._

## Évolution majeure 2026-05-19

Après test discriminant en session CLI #2 (3 modèles MLX testés sur
Osaurus, tous échoués avec `prompt_tokens=25` identique), il a été
établi que **Osaurus v0.18.28 n'applique pas les chat templates aux
modèles utilisateur**. Le diagnostic provisoire de DEC-014 était
erroné.

Conséquence : **bascule Osaurus → `mlx_lm.server`** (Apple ML Explore
officiel). Confirmé par tests live : `prompt_tokens=39` (template
appliqué), réponses cohérentes, KV cache fonctionnel.

4 nouvelles décisions (DEC-016 → DEC-019) consolident cette bascule :

- DEC-016 : diagnostic corrigé (supersède DEC-014)
- DEC-017 : `mlx_lm.server` remplace Osaurus (supersède DEC-003)
- DEC-018 : Qwen2.5-Coder-32B-Instruct-4bit confirmé sur preuves
  (supersède DEC-015 dont les prémisses étaient fausses)
- DEC-019 : cleanup Osaurus de la machine (📝 Proposed, à exécuter
  après validation finale)

## Notes de session

### Session Desktop #1 (2026-05-17)

- Initiation du projet, validation de l'architecture cible et capture des
  10 premières décisions (DEC-001 → DEC-010).
- Pivot par rapport à la conception initiale de janvier (Opus 4.6) :
  - Ollama → **Osaurus** (MLX natif Apple Silicon, KV cache session reuse,
    tool-calling natif OpenAI-style).
  - Gemma 4 27B → **Qwen3-Coder-Next 8-bit** (conçu pour agents coding, MoE
    80B/3B actifs, disponible en MLX sur mlx-community).
  - Fichiers JSON Phase 1 puis MCP Phase 2 → **MCP stdio dès Phase 1**
    (le protocole est devenu standard de facto en 2026, FastMCP est mature).
  - Un seul cas d'usage (XCTest) → **quatre patterns typés** dont A et D
    prioritaires (couverture des cas réels Desktop + CLI).
- Adoption du pattern documentaire Bassmati : index + fichiers individuels.
- Cohérence transverse avec TBS/Bassmati/QNAP confirmée (DEC-013 Bassmati
  étendue par DEC-009 ici).

### Session CLI #1 (2026-05-17)

- Bootstrap technique exécuté selon `CLI_PROMPT_001` :
  structure de dossiers, `pyproject.toml`, `.gitignore`, `.env.example`,
  `config/blacklist.txt`, placeholders Python, tests squelette.
- Deps résolues : fastmcp 3.3.1, httpx 0.28.1, pydantic 2.13.4 (+ dev:
  pytest 9.0.3, pytest-asyncio 1.3.0, ruff 0.15.13).
- Décision prise pendant la session : Python 3.12 épinglé via
  `.python-version` plutôt que laisser uv résoudre vers 3.14.5
  (captée a posteriori en **DEC-011**).
- Sanity checks passés : `uv sync`, `uv run pytest` (no tests ran),
  `uv run ruff check .`.
- Git initialisé, commit `9deed6e`, remote `origin` configuré. Premier
  `git push -u origin main` réservé à Hassan (DEC-009).
- Écarts mineurs assumés vs brief : `pyproject.toml` écrit directement
  (dossier non-vide à cause des `.md` Desktop), `.gitkeep` ajouté dans
  `scripts/` et `docs/`, `uv.lock` versionné.
