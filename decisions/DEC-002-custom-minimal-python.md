# DEC-002 : Custom minimal Python (pas LangGraph/Smolagents)

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Pour le Dispatcher, plusieurs frameworks d'orchestration LLM existent en
Python (LangGraph, Smolagents, LlamaIndex Agents, AutoGen, etc.). Le choix
du framework — ou son absence — conditionne la complexité, la dette
technique et la souplesse du projet.

## Alternatives évaluées

| Option | Lignes de code estimées | Complexité | Souplesse | Dette deps |
|--------|------------------------|------------|-----------|------------|
| A. **Custom minimal** | ~300–500 | Faible | Maximale | Minimale |
| B. Smolagents (Hugging Face) | ~150 | Faible | Bonne | Moyenne |
| C. LangGraph | ~200 | Moyenne | Moyenne | Lourde (LangChain) |
| D. AutoGen / CrewAI | ~150 | Moyenne | Bonne | Lourde |

## Décision

**Custom minimal Python** pour la Phase 1 : un loop d'orchestration écrit à
la main (~300–500 lignes), avec dépendances minimales : `fastmcp`, `httpx`,
`pydantic`, `pytest` pour les tests.

Migration vers Smolagents possible en Phase 3+ si la complexité dépasse ce
qu'il est raisonnable de maintenir à la main. Pas avant.

## Rationale

- Le périmètre Phase 1 (deux patterns, un seul worker, un seul transport)
  est trop simple pour justifier un framework.
- Hassan préfère comprendre exactement ce qui se passe — un framework
  cacherait la mécanique sans gain réel à cette échelle.
- Les frameworks ajoutent des abstractions conçues pour des workflows
  complexes (graphes d'agents, branchements conditionnels, mémoire
  partagée) dont on n'a pas besoin tout de suite.
- La dette de dépendances (notamment LangChain) est notoire pour les
  ruptures d'API entre versions mineures.

## Implémentation

- `src/optimai/dispatcher.py` : boucle d'orchestration principale
- `src/optimai/worker.py` : client Osaurus (OpenAI-compatible)
- `src/optimai/patterns/diagnose.py`, `execute.py` : implémentations
  par pattern
- `pyproject.toml` géré via `uv` (recommandé par le SDK MCP officiel)

## Trade-offs

- ✅ Compréhension totale du code, debugging direct
- ✅ Pas de dette de dépendances lourdes
- ✅ Migration framework possible plus tard sans réécriture totale
- ❌ Plus de code à écrire au départ (~300 lignes vs ~150)
- ❌ Réinvention de patterns connus (retry, timeout, etc.) — mitigation :
  utiliser `httpx` (retry/timeout natifs) et `asyncio` (timeout natif)
