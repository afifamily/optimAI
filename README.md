# optimAI

> **Statut** : 🚧 Phase 1 — Bootstrap & PoC
> **Démarrage** : 2026-05-17

Architecture hybride "Cortex / Hands" pour réduire la consommation de
tokens Claude sur les tâches mécaniques (lecture de logs, packs de
commandes shell, diagnostics itératifs), tout en automatisant ce que
Hassan exécute aujourd'hui à la main en mode `/optimized`.

## Idée en 30 secondes

```
┌─────────────────────────────────────────────────┐
│  CORTEX — Claude Desktop / CLI / API            │
│  Comprend, décide, formule des Task Specs       │
└────────────────────┬────────────────────────────┘
                     │  MCP stdio
                     ▼
┌─────────────────────────────────────────────────┐
│  DISPATCHER — Python, serveur MCP local         │
│  Orchestre la boucle, applique les garde-fous,  │
│  renvoie un rapport compressé                   │
└────────────────────┬────────────────────────────┘
                     │  HTTP OpenAI-compatible
                     ▼
┌─────────────────────────────────────────────────┐
│  HANDS — Qwen3-Coder-Next via Osaurus (MLX)     │
│  Exécute, itère, vérifie, tool-calling natif    │
└─────────────────────────────────────────────────┘
```

**Économie de tokens estimée : ~80 %** sur les tâches mécaniques.
**Bénéfice annexe** : Hassan récupère le temps qu'il perdait à
exécuter les commandes shell du mode `/optimized`.

## Documentation

| Fichier | Contenu |
|---------|---------|
| [`DECISIONS.md`](DECISIONS.md) | Index des 10 décisions architecturales |
| [`ROADMAP.md`](ROADMAP.md) | Phases 1 → 4 |
| [`CLAUDE.md`](CLAUDE.md) | Contexte projet pour les sessions Claude futures |

## Stack

- **Python 3.12+** géré via `uv`
- **FastMCP** (serveur MCP stdio)
- **Osaurus** (inférence MLX sur Apple Silicon)
- **Qwen3-Coder-Next 8-bit** (modèle worker)
- **httpx async** (client OpenAI-compatible)
- **Pydantic v2** (schemas Task Spec / Report)

## Projets liés

| Projet | Relation | Path |
|--------|----------|------|
| **TBS** | Cas d'usage majeur (diagnostics Swift, builds, Docker) | `.../production/TelegramBotsServer/` |
| **Bassmati** | Cas d'usage majeur (Go, Caddy, QNAP), source du pattern documentaire | `.../production/bassmati/` |
| **QNAP** | Cas d'usage majeur (Docker, network, troubleshooting) | `.../production/QNAP/` |

## Hardware cible

Mac Studio M2 Max, 96 GB unified memory. Modèle Qwen3-Coder-Next 8-bit
MLX (~85 GB) tient confortablement avec marge pour OS et contexte.

## Status

Phase 1 en cours — voir [`ROADMAP.md`](ROADMAP.md) pour le détail.
