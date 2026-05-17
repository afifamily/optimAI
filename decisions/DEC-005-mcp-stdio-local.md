# DEC-005 : MCP stdio local via FastMCP

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Le Cortex (Claude Desktop / CLI) doit appeler le Dispatcher. Trois transports
sont envisageables : fichiers JSON via watch-folder, stdio (subprocess +
JSON-RPC), HTTP/SSE.

En janvier 2026 (planification initiale Opus 4.6), l'idée était de partir
sur fichiers JSON en Phase 1, puis migrer vers MCP en Phase 2. Depuis,
MCP est devenu **le standard de facto** : Anthropic a donné le protocole
à la Linux Foundation fin 2025, OpenAI, Google et Microsoft le supportent
nativement, et FastMCP est mature.

## Alternatives évaluées

| Transport | Setup | Intégration Claude | Latence | Maturité |
|-----------|-------|--------------------|---------|----------|
| Fichiers JSON watch | Trivial | Manuelle | Élevée | Non standard |
| **MCP stdio (FastMCP)** | **Simple** | **Native** | **Faible** | **Standard** |
| MCP Streamable HTTP | Plus complexe | Native | Faible | Standard, mais réseau |
| gRPC custom | Lourd | Manuelle | Faible | Non standard |

## Décision

**MCP stdio dès la Phase 1**, via la bibliothèque **FastMCP** (~70% des
serveurs MCP en production l'utilisent).

Transport stdio explicitement choisi (pas HTTP) car :
- Le Dispatcher tourne en local, sur la même machine que le Cortex
- Pas besoin de TLS, OAuth, ou réseau exposé
- Subprocess launch par Claude Desktop / CLI = isolation native
- Plus simple à débugger (un seul process à inspecter)

## Implémentation

- `src/optimai/server.py` : serveur FastMCP qui expose deux outils
  Phase 1 :
  - `optimai_diagnose` (Pattern A)
  - `optimai_execute` (Pattern D)
- Configuration Claude Desktop : entrée dans
  `~/Library/Application Support/Claude/claude_desktop_config.json`
- Configuration Claude CLI : entrée dans `.mcp.json` du projet utilisateur
  (chaque projet qui veut utiliser optimAI référence le serveur)
- Migration possible vers Streamable HTTP plus tard si besoin (un
  changement de transport = une ligne)

## Trade-offs

- ✅ Intégration native dans Claude Desktop / CLI (zéro friction)
- ✅ Transport robuste, JSON-RPC bien défini
- ✅ FastMCP gère le boilerplate (schema generation, validation, lifecycle)
- ✅ Migration future vers HTTP sans réécriture
- ❌ stdio = Dispatcher relancé à chaque session Claude (overhead léger
  d'init) — mitigation : le worker Osaurus reste persistant, donc le
  KV cache est préservé entre lancements du Dispatcher
- ❌ Pas de partage entre plusieurs instances Claude simultanées —
  acceptable pour un usage solo
