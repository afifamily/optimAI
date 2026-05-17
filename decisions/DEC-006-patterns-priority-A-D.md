# DEC-006 : Patterns prioritaires — A (Diagnose) + D (Execute)

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Quatre patterns ont été identifiés comme couvrant la grande majorité des
tâches mécaniques quotidiennes — celles qui consomment le plus de tokens
aujourd'hui ou qui forcent Hassan à exécuter manuellement en mode
`/optimized` :

- **Pattern A — Diagnose** : Claude formule un objectif d'investigation
  (ex : "swift test échoue avec `no such module XCTest`, diagnose"). Le
  worker boucle (shell → output → analyse → commande suivante), puis
  renvoie un rapport structuré (cause racine, preuve, fix temporaire,
  fix permanent). Pas de modification de fichiers en sortie.

- **Pattern B — Patch** : Claude formule une instruction de modification
  ciblée ("dans `Sources/Foo.swift`, ligne 42, remplace `oldFunc()` par
  `newFunc()`"). Le worker applique, vérifie le diff, lance les tests si
  demandés, rapporte succès/échec avec preuves.

- **Pattern C — Create** : Claude fournit une spec de fichier (chemin,
  contenu, contexte). Le worker crée, vérifie qu'il compile/parse,
  rapporte.

- **Pattern D — Execute** : Claude fournit une séquence de commandes
  shell avec résultats attendus et branchements conditionnels. Le worker
  exécute, vérifie chaque résultat, branche selon les conditions, et
  rapporte de manière sommaire (pas de log brut).

## Décision

**Patterns A et D prioritaires** pour la Phase 1.

Patterns B (Patch) et C (Create) reportés à la Phase 2 — ils nécessitent
des garde-fous plus stricts sur la modification de fichiers (validation
syntaxique, snapshots, rollback).

## Rationale

- A et D couvrent les cas les plus universels et les plus fréquents.
- A est l'archétype "boucle de diagnostic" qu'on a illustré avec le cas
  XCTest — couvre une grande famille de problèmes (Docker, network,
  build, tests, env).
- D couvre tous les cas du mode `/optimized` actuel (packs de commandes
  shell avec vérification) — c'est exactement le pattern que Hassan
  exécute aujourd'hui à la main.
- B et C nécessitent des garde-fous supplémentaires (diff preview,
  validation syntaxique, rollback) qui mériteraient leurs propres
  décisions.

## Implémentation

- Deux outils MCP exposés en Phase 1 : `optimai_diagnose` et
  `optimai_execute`.
- Schemas Pydantic dédiés : `DiagnoseSpec` / `DiagnoseReport`,
  `ExecuteSpec` / `ExecuteReport`.
- Le serveur MCP ne sait rien d'autre — Patterns B et C ne seront pas
  exposés au Cortex avant validation.

## Patterns à venir (Phase 2)

| Pattern | Outil MCP | Phase |
|---------|-----------|-------|
| B (Patch) | `optimai_patch` | Phase 2 |
| C (Create) | `optimai_create` | Phase 2 |

Pour la Phase 2, les patterns devront aussi tenir compte des cas d'usage
remontés par les instances Claude des projets TBS, Bassmati, QNAP — voir
ROADMAP.md (Phase 3 : enrichissement collaboratif).

## Trade-offs

- ✅ Périmètre Phase 1 réduit, livrable en quelques sessions
- ✅ Couvre l'essentiel des cas mode `/optimized`
- ❌ N'automatise pas encore les modifications de fichiers (B/C)
- ❌ Hassan continuera à appliquer certains patches à la main jusqu'à
  Phase 2 — acceptable, gain immédiat sur A et D
