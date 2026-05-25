# ROADMAP — optimAI

## Vue d'ensemble

Quatre phases, livrables incrémentaux. Chaque phase produit quelque
chose d'utilisable avant la suivante.

| Phase | Objectif | Statut |
|-------|----------|--------|
| **Phase 1** | Bootstrap + PoC Patterns A & D | ✅ Complète (étapes 1–11) |
| **Phase 2** | Patterns B (Patch) & C (Create) | ✅ Complète |
| **Phase 3** | Enrichissement collaboratif via TBS/Bassmati/QNAP | 🔄 En cours |
| **Phase 4** | Robustesse & observabilité | 📝 Planifiée |

---

## Phase 1 — Bootstrap + PoC (complète)

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
4. ✅ **`config.py` + `shell.py` + `worker.py` + schemas A + PoC Pattern A**
   (CLI_PROMPT_003, session CLI #3, commit local `96c70ca`)
   - `config.py` : Settings pydantic, source unique des limites DEC-007,
     singleton `lru_cache`
   - `shell.py` : exécution sandboxée (blacklist avant spawn, sandbox
     `cwd`, timeouts, env explicite sans secrets, troncature 10 KB),
     30 tests
   - `worker.py` : client async OpenAI-compat vers `mlx_lm.server`,
     extraction `cached_tokens` (KV cache), erreurs explicites,
     10 tests mockés
   - PoC scripté `scripts/poc_diagnose_xctest.py` : boucle Cortex-light
     worker→shell→worker, **converge en 2 itérations** sur le cas XCTest
     TBS (`status=complete`)
   - Sanity : **52 tests passent, ruff clean, PoC exit 0**
5. ✅ **Schemas Pydantic** (complet)
   - ✅ `DiagnoseSpec`, `DiagnoseReport` (Pattern A, CLI #3, 7 tests)
   - ✅ `ExecuteSpec` (pack ordonné non-vide) / `ExecuteReport` (compact :
     `summary` + `failed_command`) (Pattern D, CLI #5) ; validateur
     `workdir` factorisé en helper partagé ; `StopReason` enrichi de
     `command_timeout`
6. ✅ **Dispatcher (moteur + registre) + Pattern A propre**
   (CLI_PROMPT_004, session CLI #4, commit local `57382f0`, DEC-021)
   - `patterns/base.py` : Protocol `Pattern` (5 méthodes) + `Step`
     dataclass + registre `@register` / `get_pattern` / `available_patterns`
   - `dispatcher.py` : moteur de boucle **unique et agnostique du
     pattern**, applique DEC-007 (compteur + `asyncio.wait_for` global +
     per-cmd timeout récupérable) et DEC-008 (blacklist + scrub
     `operator_text` pré-vol)
   - `patterns/diagnose.py` : stratégie A ; domain knowledge XCTest
     **retiré du prompt → injecté via `spec.context`** (contrat
     Cortex↔Hands, DEC-021)
   - Tests : 52 → 91 actifs (+39) + 1 smoke `@pytest.mark.live` ;
     2 gardes architecturaux verts (aucun import Diagnose dans
     `dispatcher.py`, aucun XCTest en dur dans le prompt)
   - Smoke live validé par Hassan : converge en 2 itérations
     (`status=complete`), zéro régression vs CLI #3
7. ✅ **Pattern D — Execute** (CLI_PROMPT_005, session CLI #5, commit local
   `210fecd`, DEC-022)
   - `patterns/execute.py` : stratégie D branchée sur le moteur, sémantique
     option (1) — pack ordonné worker-driven, pas d'improvisation mutante
   - Hook `on_command_timeout` (DEC-022) : Execute = `abort` (commandes
     mutantes, état post-timeout inconnu) ; Diagnose = `recover` explicite ;
     défaut sûr `abort` garanti par le moteur
   - **Test empirique DEC-021 réussi** : le contrat a tenu sur un 2ᵉ
     pattern par extension rétrocompatible (DEC-021 → ✅)
   - Tests : 91 → 124 actifs (+33) ; garde `no_execute_imports` ajoutée
8. ✅ **Serveur MCP** (CLI_PROMPT_006, session CLI #6, commit local `1a92b6e`)
   - `server.py` : serveur FastMCP stdio (DEC-005) **piloté par le
     registre** (DEC-021) — itère `available_patterns()` → un outil
     `optimai_<name>` par pattern via `Tool.from_function`, schéma
     d'entrée **aplati** depuis `spec_model.model_fields` ; zéro liste
     d'outils en dur
   - Hygiène stdio : logging fichier + miroir stderr (ERROR only),
     **jamais stdout** (canal JSON-RPC) ; vérifié par test unitaire +
     smoke subprocess (`printf '' | … > stdout.txt` → vide)
   - `tool_description` ajouté au Protocol `Pattern` (extension
     rétrocompatible) + déclaré par Diagnose/Execute ; `PatternRejected`
     → `ToolError` à la frontière MCP
   - Tests : 124 → 134 (+10) ; garde DEC-021
     `test_server_tools_match_registry` + **preuve dynamique**
     (`_GhostPattern` ajouté au registre apparaît comme outil sans
     toucher `server.py`) ; ruff clean
9. ✅ **Intégration Claude Desktop** (session Desktop #10, 2026-05-21)
   - Entrée `optimai` ajoutée sous `mcpServers` dans
     `claude_desktop_config.json` (commande `/opt/homebrew/bin/uv`,
     `--directory <repo>` pour résoudre le `.env` au cwd) ; clé ajoutée
     **à côté** de `preferences` (un seul fichier sur Claude Desktop
     1.8089.1) ; aucun secret en config (lu depuis `.env`)
   - Serveur listé **running** ; les deux outils `optimai_diagnose` /
     `optimai_execute` chargés avec schéma aplati attendu (`goal`,
     `workdir` requis ; `allowed_read_paths?` / `extra_blacklist?`
     optionnels — `default_factory` matérialisés)
   - **Test bout-en-bout réel validé** : `optimai_diagnose` (goal =
     version Python, workdir = repo) → `DiagnoseReport` `status=complete`,
     `stop_reason=converged`, `iterations_used=3` ; chaîne Cortex → MCP →
     dispatch → worker `mlx_lm.server` → shell → report prouvée en prod
10. ✅ **Intégration Claude CLI** (session Desktop #11, 2026-05-21, DEC-023)
    - Scope **`user`** (`~/.claude.json`) plutôt que `.mcp.json` par projet
      (DEC-023) : une entrée visible dans **tous** les projets, aucun fichier
      déposé ni gitignoré dans TBS / Bassmati / QNAP. Import via
      `claude mcp add-from-claude-desktop --scope user` (réutilise l'entrée
      Desktop validée étape 9)
    - Runbook : `.drafts/claude/CLI/RUNBOOK_etape10_claude_cli.md` (opération
      Hassan, exécutée étape par étape)
    - Vérifié : `claude mcp get optimai` → scope user, connecté ; `/mcp`
      dans TBS / Bassmati / QNAP → 2 outils chargés ; `--directory` figé sur
      optimAI indépendant du projet appelant
    - **Test bout-en-bout réel par projet** : `optimai_diagnose` (workdir =
      repo cible) → `DiagnoseReport` `status=complete`,
      `stop_reason=converged`, 2 itérations, depuis TBS / Bassmati / QNAP et
      avec trois Cortex (Opus 4.7, Sonnet 4.6, Haiku 4.5) — invariant
      `workdir` ≠ `--directory` confirmé en pratique
    - Pattern D validé live (étape 11) : `optimai_execute` sur pack mutant de
      2 commandes ordonnées (`echo >` + vérif) → `status=complete`,
      `converged`, `failed_command=null`, les 2 commandes à `exit=0` —
      sémantique mutante prouvée, distincte du read-only Diagnose
11. ✅ **Documentation** (session Desktop #11, 2026-05-21)
    - `docs/ARCHITECTURE.md` : 3 couches, flux Mermaid, Dispatcher détaillé,
      limites DEC-007, 4 couches garde-fous DEC-008, worker, transport stdio
    - `docs/PATTERNS.md` : contrat commun, spec A & D (schémas E/S exacts +
      `tool_description`), exemple Diagnose **réel** (trace étape 10), exemple
      Execute **réel** (trace étape 11, pack mutant), vocabulaire `stop_reason`,
      section « `workdir` : pourquoi pas de fallback »
    - `TROUBLESHOOTING.md` : table de triage + pièges conceptuels (`workdir`
      ≠ `--directory`, chemin absolu `uv`, `.env`/cwd, hygiène stdout, worker,
      `add-json`, faux positif blacklist, reconnexion stdio)

**Critère de complétion Phase 1** : Hassan peut, depuis Claude Desktop
ou Claude CLI dans n'importe quel projet, demander "diagnose ce
problème" ou "execute ce pack de commandes", et le travail est fait
en local avec un rapport compressé qui retourne au Cortex.

---

## Phase 2 — Patterns B & C (complète)

**Objectif** : Étendre aux modifications de fichiers (Patch) et créations
(Create), avec garde-fous renforcés. **Périmètre de réversibilité fixé par
[DEC-024](decisions/DEC-024-reversibility-scope.md)** : atomicité intra-appel
seulement (la réversibilité de lot inter-appels est reportée post-Phase 3 —
voir Phase 4).

### Étapes (livrées CLI #7–#9, commits `fb6d2b5` / `9b7dffd` + CLI #9)

- ✅ **Pattern B (Patch)** : édits ciblés recherche-remplacement (`old`/`new`
  par fichier) fournis par le Cortex, appliqués de façon **déterministe**
  (DEC-024), avec **diff preview** (`difflib`) et **atomicité intra-appel**
  (restauration de l'état d'avant l'appel sur échec)
- ✅ **Pattern C (Create)** : création de fichiers depuis une spec (chemin +
  contenu fournis par le Cortex), avec **validation syntaxique** via shell
  (Swift / Python / Go) et même atomicité intra-appel
- ✅ **Atomicité intra-appel** via helper de snapshot (`snapshot.py`) : copie
  temporaire éphémère des fichiers touchés (**pas** `git stash`), restaurée sur
  échec, nettoyée sur succès
- ✅ Acte mutant **déterministe et Cortex-sourced** ; worker = validation +
  verdict, pas mutation (DEC-024) — pari sémantique confirmé en smoke live
- ✅ **Test DEC-021 sur la phase de mutation** : branchée par hooks optionnels
  (`mutate`/`enrich_report` via `getattr`), 0 signature touchée, moteur non
  refondu → DEC-021 tient (3è/4è preuves)
- ✅ Sémantique du statut d'échec durcie (DEC-024 amendée + précisée) :
  cascade 2 couches (Layer 1 déterministe non contournable + Layer 2 worker
  additif) ; un outil de validation absent (exit 127) ne rollback pas un
  fichier valide (dégradation propre côté code via `shutil.which`)
- ✅ Tests d'intégration patterns combinés (A+B, D+C)

---

## Phase 3 — Enrichissement collaboratif (en cours)

**Objectif** : Faire émerger de nouveaux patterns à partir des sessions
passées des autres projets.

### Fait (Desktop #13, 2026-05-25)

- ✅ **Méthodologie de collecte** ([DEC-025](decisions/DEC-025-phase3-pattern-collection.md))
  : instrument générique paramétré par projet
  (`.drafts/claude/phase3/COLLECT_PROMPT.md`), lancé depuis chaque espace-projet
  Claude (scope `conversation_search` par projet), avec accès au repo optimAI
  pour comparer les candidats à l'existant. Banc d'essai TBS d'abord, puis
  généralisation Bassmati + QNAP.
- ✅ **Trois collectes exécutées** → agrégation cross-projet
  `docs/PATTERN_CANDIDATES.md`. Résultat : un seul nouveau pattern à construire
  (E/Scan, prouvé sur les 3 projets) ; le reste de la valeur locale déjà
  couvert par A/D.
- ✅ **Pattern E (Scan/Audit)** (CLI #10, commit `fd810e0`) : read-only,
  motifs `required`/`forbidden`/`secret_patterns` Cortex-sourced, sources FS
  (grep) + HTTP (GET), report `matches` + verdict pass/fail. 5ᵉ preuve DEC-021
  (`base.py` + `server.py` strictement non touchés).
- ✅ **Redaction des valeurs de secrets en sortie**
  ([DEC-026](decisions/DEC-026-secret-value-redaction-in-reports.md)) : une
  valeur de secret peut entrer (motif à chercher) mais ne ressort jamais en
  clair — redaction déterministe côté Dispatcher sur les 3 vecteurs
  (`matches.text/pattern`, `commands_executed.cmd`, champs libres) avant retour
  Cortex ET avant log.

### À venir

- **Priorisation d'optimAI par le Cortex** (sujet d'ouverture Desktop #14) :
  comment Claude (Desktop + CLI) préfère optimAI avant d'aller chercher un
  autre outil (ex. bascule via skills) + traçabilité des cas où optimAI a été
  ignoré, pour identifier de nouveaux patterns prospects. (Transverse Phase
  3→Phase 4 : enrichissement *via l'usage* plutôt que *via l'historique*.)
- **Usages D/A déjà délégables** à documenter comme specs-types réutilisables
  (build-test, diagnose, migrations, lancer-script, doc-scan local — voir
  `docs/PATTERN_CANDIDATES.md`, File A).
- **`ssh-remote`** : dimension d'exécution distante (gate l'opérationnel
  QNAP/prod, File B de `PATTERN_CANDIDATES.md`) — DEC dédiée (extension
  sandbox→hôte distant), pilote read-only qnap-01.
- Évolution potentielle vers un framework si la complexité l'exige
  (Smolagents, à reconsidérer — voir DEC-002). Non justifié à ce jour.

---

## Phase 4 — Robustesse & observabilité

**Objectif** : Production-grade, mesurable, débugable.

### Étapes prévues

- **Réversibilité de lot inter-appels — autorité git locale (post-Phase 3,
  reportée par [DEC-024](decisions/DEC-024-reversibility-scope.md))** : outils
  `optimai_checkpoint` / `optimai_checkpoint_resolve`, branche temporaire
  `optimai/*` portant l'état du lot (statelessness préservée — l'état vit
  dans git, pas en mémoire), diff de lot via `git diff`, garde-fous (working
  tree propre, namespace `optimai/*`, **jamais de push**, `discard` autonome /
  `merge` gated). Reconnue inévitable, à concevoir **après** l'enrichissement
  Phase 3 pour couvrir un maximum de situations. Esquisse conservée dans
  DEC-024 ; fera l'objet d'une DEC dédiée.
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
