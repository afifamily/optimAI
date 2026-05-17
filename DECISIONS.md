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
| [DEC-003](decisions/DEC-003-osaurus-over-ollama.md) | Osaurus + MLX comme couche d'inférence | ✅ | 2026-05-17 |
| [DEC-004](decisions/DEC-004-qwen3-coder-next.md) | Qwen3-Coder-Next 8-bit MLX (worker) | ✅ | 2026-05-17 |
| [DEC-005](decisions/DEC-005-mcp-stdio-local.md) | MCP stdio local via FastMCP | ✅ | 2026-05-17 |
| [DEC-006](decisions/DEC-006-patterns-priority-A-D.md) | Patterns prioritaires — A (Diagnose) + D (Execute) | ✅ | 2026-05-17 |
| [DEC-007](decisions/DEC-007-loop-limits.md) | Limites worker — 10 itérations / 5 min / 10 KB output | ✅ | 2026-05-17 |
| [DEC-008](decisions/DEC-008-security-guardrails.md) | Garde-fous sécurité — blacklist, sandbox path, secrets isolés | ✅ | 2026-05-17 |
| [DEC-009](decisions/DEC-009-meta-architecture-desktop-cli.md) | Méta-architecture — Desktop = Cortex, CLI = Hands intelligente | ✅ | 2026-05-17 |
| [DEC-010](decisions/DEC-010-git-private-repo.md) | Git activé, repo privé GitHub | ✅ | 2026-05-17 |

## Décisions à venir

_Aucune décision en cours de rédaction._

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
