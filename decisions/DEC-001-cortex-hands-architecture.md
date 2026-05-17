# DEC-001 : Architecture Cortex / Dispatcher / Hands

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

L'usage quotidien de Claude Desktop, CLI et API consomme des tokens en grandes
quantités, principalement pour des opérations mécaniques : lecture de logs,
itérations shell, modifications répétées de fichiers, exécution de packs de
commandes. Les optimisations au niveau de l'organisation des repos
(DECISIONS.md compact, fichiers découpés, etc.) ne suffisent plus.

Le skill `~/.claude/skills/workflow-optimized.md` fait économiser des tokens
en demandant à Hassan d'exécuter lui-même les commandes shell, Git, etc. Le
trade-off actuel est explicite : on gagne en tokens, on perd en temps humain.
**optimAI doit régler ce trade-off une fois pour toute.**

## Alternatives évaluées

| Option | Avantages | Inconvénients |
|--------|-----------|---------------|
| A. Tout en cloud Claude | Simple, qualité maximale | Coût tokens élevé, le problème actuel |
| B. Tout en local (un seul modèle) | Coût zéro après hardware | Qualité insuffisante pour le raisonnement complexe |
| C. **Hybride Cortex/Hands** | Raisonnement Claude + exécution locale | Plus de pièces mobiles à orchestrer |

## Décision

Architecture à trois couches :

```
┌─────────────────────────────────────────────────┐
│  CORTEX — Claude Desktop / CLI / API            │
│  Comprend, décide, formule des Task Specs       │
└────────────────────┬────────────────────────────┘
                     │  MCP (JSON-RPC, stdio)
                     ▼
┌─────────────────────────────────────────────────┐
│  DISPATCHER — Python, serveur MCP local         │
│  Reçoit Task Specs typées, orchestre la boucle  │
│  worker ↔ shell, applique les garde-fous,       │
│  renvoie un rapport compressé                   │
└────────────────────┬────────────────────────────┘
                     │  HTTP OpenAI-compatible + session_id
                     ▼
┌─────────────────────────────────────────────────┐
│  HANDS — Modèle local via Osaurus               │
│  Exécute, itère, vérifie, propose les commandes │
│  via tool-calling natif                         │
└─────────────────────────────────────────────────┘
```

**Cortex** garde le raisonnement de haut niveau et la décision. Il ne gaspille
plus de tokens à lire des logs ou itérer sur des erreurs.

**Dispatcher** est la pièce centrale. Il traduit les Task Specs en boucle
d'exécution, applique sécurité et limites, et renvoie au Cortex un rapport
JSON condensé (le 80% de l'économie de tokens se fait ici).

**Hands** exécute les opérations mécaniques en local, gratuitement après
l'achat du Mac Studio.

## Implémentation

- Dispatcher = projet `optimAI` (ce repo)
- Première version : Patterns A (Diagnose) et D (Execute) — voir DEC-006
- Communication Cortex ↔ Dispatcher : MCP stdio — voir DEC-005
- Modèle Hands : Qwen3-Coder-Next 8-bit via Osaurus — voir DEC-003, DEC-004

## Trade-offs

- ✅ Économie de tokens estimée ~80% sur les tâches mécaniques
- ✅ Hassan récupère le temps qu'il perd actuellement avec `/optimized`
- ✅ Architecture extensible (nouveaux patterns ajoutables incrémentalement)
- ❌ Plus de composants à maintenir (Dispatcher Python + Osaurus + modèle)
- ❌ Dépendance hardware (Mac Studio doit rester allumé pour que ça marche)
- ❌ Le worker local peut échouer là où Claude réussirait — fallback Cortex
  prévu en Phase 4
