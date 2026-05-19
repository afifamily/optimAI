# ROADMAP — optimAI

## Vue d'ensemble

Quatre phases, livrables incrémentaux. Chaque phase produit quelque
chose d'utilisable avant la suivante.

| Phase | Objectif | Statut |
|-------|----------|--------|
| **Phase 1** | Bootstrap + PoC Patterns A & D | 🚧 En cours (étape 4) |
| **Phase 2** | Patterns B (Patch) & C (Create) | 📝 Planifiée |
| **Phase 3** | Enrichissement collaboratif via TBS/Bassmati/QNAP | 📝 Planifiée |
| **Phase 4** | Robustesse & observabilité | 📝 Planifiée |

---

## Phase 1 — Bootstrap + PoC (en cours)

**Objectif** : Patterns A (Diagnose) et D (Execute) fonctionnels,
intégrés à Claude Desktop et CLI, validés sur le cas XCTest TBS.

### Étapes

1. ✅ **Architecture validée** — DEC-001 → DEC-011 (Desktop #1, Desktop #2)
2. ✅ **Bootstrap technique** (CLI_PROMPT_001, session CLI #1, commit `9deed6e`)
   - Structure dossiers, `pyproject.toml`, `.gitignore`, `.env.example`,
     `config/blacklist.txt` initial
   - `uv sync` + Python 3.12.13 épinglé (DEC-011)
   - Git initialisé, remote `origin` configuré
3. ✅ **Setup environnement local — chaîne d'inférence validée**
   (CLI_PROMPT_002 PATCH #3, sessions CLI #2 + Desktop #5/#6, commit
   local `05d8bae` + cleanup DEC-019)
   - Stack pivotée Osaurus → `mlx_lm.server` après diagnostic
     discriminant (DEC-016/017)
   - Modèle worker confirmé : `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit`
     (~18 GB, DEC-018)
   - Tests live : `prompt_tokens=39` (template appliqué), réponses
     cohérentes (4 + Paris), KV cache fonctionnel, Fibonacci
     memoization en multi-tour
   - `.env.example` + `.env` finalisés (variables `MLX_SERVER_URL`,
     `OPTIMAI_MODEL` HF-id complet)
   - `config/blacklist.txt` consolidé (anti-`mlx_lm.server --host 0.0.0.0`
     + anti-`osaurus serve` en défense en profondeur)
   - Cleanup Osaurus exécuté (DEC-019 ✅ Accepted, ~19 GB récupérés)
4. 🔄 **Module `shell.py` + Module `worker.py` + premier test Pattern A**
   (CLI_PROMPT_003, session CLI #3 à venir)
   - `shell.py` : exécution sandboxée (blacklist, sandbox chemin,
     timeouts, troncature 10 KB), tests unitaires exhaustifs
   - `worker.py` : client HTTP OpenAI-compat vers `mlx_lm.server`,
     boucle d'itérations bornée (DEC-007), KV cache transparent
   - Premier test Pattern A bout-en-bout sur fixture XCTest (cas TBS)
5. 📝 **Schemas Pydantic**
   - `DiagnoseSpec`, `DiagnoseReport`
   - `ExecuteSpec`, `ExecuteReport`
6. 📝 **Pattern A — Diagnose** (complétion)
   - Module `patterns/diagnose.py` implémentation complète
   - Système prompt worker (en anglais), boucle d'investigation
   - Tests sur fixtures TBS troubleshooting
7. 📝 **Pattern D — Execute**
   - Module `patterns/execute.py`
   - Test sur pack de commandes shell typique (build, test, validation)
8. 📝 **Serveur MCP**
   - Exposition `optimai_diagnose` et `optimai_execute`
   - Transport stdio via FastMCP (DEC-005)
9. 📝 **Intégration Claude Desktop**
   - Entrée dans `claude_desktop_config.json`
   - Test bout-en-bout
10. 📝 **Intégration Claude CLI**
    - Entrée dans `.mcp.json` des projets TBS / Bassmati / QNAP
    - Test bout-en-bout depuis chaque projet
11. 📝 **Documentation**
    - `docs/ARCHITECTURE.md` (diagramme + flux)
    - `docs/PATTERNS.md` (spec Patterns A & D, exemples)
    - `TROUBLESHOOTING.md` initial

**Critère de complétion Phase 1** : Hassan peut, depuis Claude Desktop
ou Claude CLI dans n'importe quel projet, demander "diagnose ce
problème" ou "execute ce pack de commandes", et le travail est fait
en local avec un rapport compressé qui retourne au Cortex.

---

## Phase 2 — Patterns B & C

**Objectif** : Étendre aux modifications de fichiers (Patch) et créations
(Create), avec garde-fous renforcés.

### Étapes prévues

- Pattern B (Patch) : instructions ciblées de modification
  (ligne, recherche, remplacement) avec diff preview et rollback
- Pattern C (Create) : création de fichiers depuis une spec, avec
  validation syntaxique (Swift, Python, Go selon le projet)
- Snapshots automatiques avant modification (git stash ou copie
  temporaire)
- Tests d'intégration sur les patterns combinés (A+B, D+C)

---

## Phase 3 — Enrichissement collaboratif

**Objectif** : Faire émerger de nouveaux patterns à partir des sessions
passées des autres projets.

### Étapes prévues

- Prompt structuré pour chaque instance Claude (TBS, Bassmati, QNAP)
  qui explore `conversation_search` sur ses 50 dernières sessions
- Format de sortie : liste de patterns avec exemples concrets
- Hassan valide les patterns proposés
- Nouveaux patterns ajoutés au Dispatcher (E, F, ...)
- Évolution potentielle vers un framework si la complexité l'exige
  (Smolagents, à reconsidérer à ce stade — voir DEC-002)

---

## Phase 4 — Robustesse & observabilité

**Objectif** : Production-grade, mesurable, débugable.

### Étapes prévues

- Métriques tokens économisés (comparaison "avec optimAI" vs "sans")
- Logs structurés des sessions (JSON, queryables)
- Fallback Cortex si worker échoue 2 fois de suite
- Sandboxing Docker optionnel (durcissement DEC-008)
- Whitelist `sudo` configurable par projet
- Dashboard simple (optionnel — uniquement si utile)
- **Autostart `mlx_lm.server` via launchd LaunchAgent** (cf. note
  DEC-017, Phase 1 reste en lancement manuel)
- **Benchmark contrôlé Qwen2.5 vs Qwen3-Coder** sur cas réels
  TBS/Bassmati/QNAP (cf. note DEC-018 — réévaluation rationnelle sur
  données après que la chaîne ait prouvé sa stabilité)
- **Désactiver macOS Low Power Mode** avant les benchmarks (détecté
  pendant les sessions de debug Osaurus, à ne pas oublier)

---

## Hors périmètre (pour l'instant)

- Multi-utilisateurs (optimAI est un outil personnel pour Hassan)
- Déploiement sur QNAP (Mac Studio doit rester la machine d'inférence)
- Modèles cloud comme fallback automatique (sauf si Phase 3 le justifie)
- Worker en GPU non-Apple (le projet est explicitement Apple Silicon)
- Re-test d'Osaurus (DEC-019 ferme la porte ; ré-ouverture possible
  uniquement après une v1.0 stable d'Osaurus, et seulement si une
  raison technique sérieuse le motive)
