# optimAI

> **Statut** : ✅ Phase 1 complète (étapes 1–11) — Patterns A & D intégrés Desktop + CLI
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
│  HANDS — Qwen2.5-Coder-32B via mlx_lm.server    │
│  Exécute, itère, vérifie (MLX, Apple Silicon)   │
└─────────────────────────────────────────────────┘
```

**Économie de tokens estimée : ~80 %** sur les tâches mécaniques.
**Bénéfice annexe** : Hassan récupère le temps qu'il perdait à
exécuter les commandes shell du mode `/optimized`.

## Documentation

| Fichier | Contenu |
|---------|---------|
| [`DECISIONS.md`](DECISIONS.md) | Index des décisions architecturales (DEC-001 → 023) |
| [`ROADMAP.md`](ROADMAP.md) | Phases 1 → 4 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 3 couches, flux d'une requête, garde-fous |
| [`docs/PATTERNS.md`](docs/PATTERNS.md) | Spec Patterns A & D, schémas E/S, exemples |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | Pièges d'exploitation + table de triage |
| [`CLAUDE.md`](CLAUDE.md) | Contexte projet pour les sessions Claude futures |

## Stack

- **Python 3.12+** géré via `uv`
- **FastMCP** (serveur MCP stdio)
- **mlx_lm.server** (inférence MLX sur Apple Silicon, DEC-017)
- **Qwen2.5-Coder-32B-Instruct-4bit** (modèle worker, DEC-018)
- **httpx async** (client OpenAI-compatible)
- **Pydantic v2** (schemas Task Spec / Report)

## Projets liés

| Projet | Relation | Path |
|--------|----------|------|
| **TBS** | Cas d'usage majeur (diagnostics Swift, builds, Docker) | `.../production/TelegramBotsServer/` |
| **Bassmati** | Cas d'usage majeur (Go, Caddy, QNAP), source du pattern documentaire | `.../production/bassmati/` |
| **QNAP** | Cas d'usage majeur (Docker, network, troubleshooting) | `.../production/QNAP/` |

## Hardware cible

Mac Studio M2 Max, 96 GB unified memory. Modèle
Qwen2.5-Coder-32B-Instruct-4bit MLX (~18 GB) tient très confortablement
avec large marge pour OS et contexte.

## Status

Phase 1 complète — voir [`ROADMAP.md`](ROADMAP.md) pour le détail et les
phases 2 → 4 à venir.
