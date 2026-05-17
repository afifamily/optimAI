# ROADMAP — optimAI

## Vue d'ensemble

Quatre phases, livrables incrémentaux. Chaque phase produit quelque
chose d'utilisable avant la suivante.

| Phase | Objectif | Statut |
|-------|----------|--------|
| **Phase 1** | Bootstrap + PoC Patterns A & D | 🚧 En cours |
| **Phase 2** | Patterns B (Patch) & C (Create) | 📝 Planifiée |
| **Phase 3** | Enrichissement collaboratif via TBS/Bassmati/QNAP | 📝 Planifiée |
| **Phase 4** | Robustesse & observabilité | 📝 Planifiée |

---

## Phase 1 — Bootstrap + PoC (en cours)

**Objectif** : Patterns A (Diagnose) et D (Execute) fonctionnels,
intégrés à Claude Desktop et CLI, validés sur le cas XCTest TBS.

### Étapes

1. ✅ **Architecture validée** — Décisions DEC-001 → DEC-010 + DEC-011
2. ✅ **Bootstrap technique** (CLI_PROMPT_001, session CLI #1)
   - `git init`, commit `9deed6e`, remote `origin` configuré (push à venir)
   - Structure dossiers créée
   - `pyproject.toml` via `uv` (fastmcp 3.3.1, httpx 0.28.1, pydantic 2.13.4)
   - `.python-version` épinglé sur 3.12 (DEC-011)
   - `.gitignore`, `.env.example`, `config/blacklist.txt` initial
3. 🔄 **Setup environnement local** (prochaine session, CLI_PROMPT_002)
   - Install Osaurus sur Mac Studio
   - Pull `mlx-community/Qwen3-Coder-Next-8bit`
   - Vérification santé serveur Osaurus
4. 📝 **Module `shell.py`** — exécution sandboxée
   - Blacklist commandes
   - Sandbox chemin (workdir)
   - Timeouts, troncature output
   - Tests unitaires
5. 📝 **Module `worker.py`** — client Osaurus
   - Tool-calling OpenAI-style
   - Session reuse (KV cache via `session_id`)
   - Test isolé (ex : "liste les fichiers de /tmp")
6. 📝 **Schemas Pydantic**
   - `DiagnoseSpec`, `DiagnoseReport`
   - `ExecuteSpec`, `ExecuteReport`
7. 📝 **Pattern A — Diagnose**
   - Implémentation complète
   - Test sur fixture XCTest (cas TBS troubleshooting #N)
8. 📝 **Pattern D — Execute**
   - Implémentation complète
   - Test sur pack de commandes shell typique
9. 📝 **Serveur MCP**
   - Exposition `optimai_diagnose` et `optimai_execute`
   - Transport stdio via FastMCP
10. 📝 **Intégration Claude Desktop**
    - Entrée dans `claude_desktop_config.json`
    - Test bout-en-bout
11. 📝 **Intégration Claude CLI**
    - Entrée dans `.mcp.json` des projets TBS / Bassmati / QNAP
    - Test bout-en-bout depuis chaque projet
12. 📝 **Documentation**
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

---

## Hors périmètre (pour l'instant)

- Multi-utilisateurs (optimAI est un outil personnel pour Hassan)
- Déploiement sur QNAP (Mac Studio doit rester la machine d'inférence)
- Modèles cloud comme fallback automatique (sauf si Phase 3 le justifie)
- Worker en GPU non-Apple (le projet est explicitement Apple Silicon)
