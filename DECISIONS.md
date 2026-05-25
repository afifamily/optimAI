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
| [DEC-003](decisions/DEC-003-osaurus-over-ollama.md) | Osaurus + MLX comme couche d'inférence | 🔁 | 2026-05-17 |
| [DEC-004](decisions/DEC-004-qwen3-coder-next.md) | Qwen3-Coder-Next 8-bit MLX (worker) | ✅ | 2026-05-17 |
| [DEC-005](decisions/DEC-005-mcp-stdio-local.md) | MCP stdio local via FastMCP | ✅ | 2026-05-17 |
| [DEC-006](decisions/DEC-006-patterns-priority-A-D.md) | Patterns prioritaires — A (Diagnose) + D (Execute) | ✅ | 2026-05-17 |
| [DEC-007](decisions/DEC-007-loop-limits.md) | Limites worker — 10 itérations / 5 min / 10 KB output | ✅ | 2026-05-17 |
| [DEC-008](decisions/DEC-008-security-guardrails.md) | Garde-fous sécurité — blacklist, sandbox path, secrets isolés | ✅ | 2026-05-17 |
| [DEC-009](decisions/DEC-009-meta-architecture-desktop-cli.md) | Méta-architecture — Desktop = Cortex, CLI = Hands intelligente | ✅ | 2026-05-17 |
| [DEC-010](decisions/DEC-010-git-private-repo.md) | Git activé, repo privé GitHub | ✅ | 2026-05-17 |
| [DEC-011](decisions/DEC-011-python-3-12-baseline.md) | Python 3.12 baseline (`.python-version` épinglée) | ✅ | 2026-05-17 |
| [DEC-012](decisions/DEC-012-osaurus-port-1337.md) | Port Osaurus 1337, écoute 127.0.0.1, `--expose` interdit | ✅ | 2026-05-17 |
| [DEC-013](decisions/DEC-013-plan-b-qwen3-coder-30b-a3b.md) | Plan B activé — Qwen3-Coder-30B-A3B-Instruct-4bit (worker effectif) | 🔁 | 2026-05-17 |
| [DEC-014](decisions/DEC-014-osaurus-template-limitation.md) | Osaurus — limite sur templates Jinja externes complexes + règles d'usage | 🔁 | 2026-05-17 |
| [DEC-015](decisions/DEC-015-qwen2-5-coder-32b-instruct.md) | Plan C — Qwen2.5-Coder-32B-Instruct-4bit (worker effectif) | 🔁 | 2026-05-17 |
| [DEC-016](decisions/DEC-016-osaurus-diagnostic-corrected.md) | Diagnostic Osaurus corrigé — serveur fautif, pas les modèles | ✅ | 2026-05-19 |
| [DEC-017](decisions/DEC-017-mlx-lm-server-replaces-osaurus.md) | Bascule Osaurus → `mlx_lm.server` comme serveur d'inférence | ✅ | 2026-05-19 |
| [DEC-018](decisions/DEC-018-qwen2-5-coder-32b-confirmed.md) | Qwen2.5-Coder-32B-Instruct-4bit confirmé comme worker (Phase 1) | ✅ | 2026-05-19 |
| [DEC-019](decisions/DEC-019-osaurus-cleanup.md) | Cleanup Osaurus de la machine | ✅ | 2026-05-19 |
| [DEC-020](decisions/DEC-020-project-local-disk-git-sync.md) | Projet hors iCloud — disque local, sync via Git | ✅ | 2026-05-20 |
| [DEC-021](decisions/DEC-021-dispatcher-engine-pattern-registry.md) | Architecture Dispatcher — moteur unique + registre de patterns (Strategy) | ✅ | 2026-05-20 |
| [DEC-022](decisions/DEC-022-per-command-timeout-policy.md) | Politique de timeout par-commande — par-pattern (Diagnose recover / Execute abort) | ✅ | 2026-05-20 |
| [DEC-023](decisions/DEC-023-claude-cli-user-scope.md) | Intégration Claude CLI — scope `user` (`~/.claude.json`) | ✅ | 2026-05-21 |
| [DEC-024](decisions/DEC-024-reversibility-scope.md) | Périmètre réversibilité — atomicité intra-appel (Phase 2), lot reporté | ✅ | 2026-05-23 |
| [DEC-025](decisions/DEC-025-phase3-pattern-collection.md) | Méthodologie de collecte de patterns (Phase 3) | ✅ | 2026-05-25 |
| [DEC-026](decisions/DEC-026-secret-value-redaction-in-reports.md) | Non-divulgation des valeurs de secrets en sortie (reports & logs) | ✅ | 2026-05-25 |

## Décisions à venir

DEC-023 actée Desktop #11 (scope `user` pour l'intégration Claude CLI ;
exécution via runbook étape 10 — opération Hassan — à venir). DEC-021 et
DEC-022 sont passées
✅ Accepted (Desktop #9, sur preuve CLI #5 : le contrat `Pattern` a tenu
sur un 2ᵉ pattern par extension rétrocompatible).

## Évolution majeure 2026-05-19

Après test discriminant en session CLI #2 (3 modèles MLX testés sur
Osaurus, tous échoués avec `prompt_tokens=25` identique), il a été
établi que **Osaurus v0.18.28 n'applique pas les chat templates aux
modèles utilisateur**. Le diagnostic provisoire de DEC-014 était
erroné.

Conséquence : **bascule Osaurus → `mlx_lm.server`** (Apple ML Explore
officiel). Confirmé par tests live : `prompt_tokens=39` (template
appliqué), réponses cohérentes, KV cache fonctionnel.

4 nouvelles décisions (DEC-016 → DEC-019) consolident cette bascule :

- DEC-016 : diagnostic corrigé (supersède DEC-014)
- DEC-017 : `mlx_lm.server` remplace Osaurus (supersède DEC-003)
- DEC-018 : Qwen2.5-Coder-32B-Instruct-4bit confirmé sur preuves
  (supersède DEC-015 dont les prémisses étaient fausses)
- DEC-019 : cleanup Osaurus de la machine (✅ Accepted Desktop session
  #6, post CLI #2 PATCH #3 validé, commit local `05d8bae`)

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

### Session CLI #1 (2026-05-17)

- Bootstrap technique exécuté selon `CLI_PROMPT_001` :
  structure de dossiers, `pyproject.toml`, `.gitignore`, `.env.example`,
  `config/blacklist.txt`, placeholders Python, tests squelette.
- Deps résolues : fastmcp 3.3.1, httpx 0.28.1, pydantic 2.13.4 (+ dev:
  pytest 9.0.3, pytest-asyncio 1.3.0, ruff 0.15.13).
- Décision prise pendant la session : Python 3.12 épinglé via
  `.python-version` plutôt que laisser uv résoudre vers 3.14.5
  (captée a posteriori en **DEC-011**).
- Sanity checks passés : `uv sync`, `uv run pytest` (no tests ran),
  `uv run ruff check .`.
- Git initialisé, commit `9deed6e`, remote `origin` configuré. Premier
  `git push -u origin main` réservé à Hassan (DEC-009).
- Écarts mineurs assumés vs brief : `pyproject.toml` écrit directement
  (dossier non-vide à cause des `.md` Desktop), `.gitkeep` ajouté dans
  `scripts/` et `docs/`, `uv.lock` versionné.

### Session CLI #2 (2026-05-18 / 2026-05-19)

Session longue, en deux temps, séparée par Desktop #5.

**Première partie (2026-05-18 → 2026-05-19 matin) — diagnostic Osaurus**

- Install Osaurus v0.18.28 (par Hassan), pull successif de
  Qwen3-Coder-30B-A3B-Instruct-4bit (Plan B), puis
  Qwen2.5-Coder-32B-Instruct-4bit (Plan C), tous deux échouent en
  inférence avec sortie dégénérée "2+2+2+..." sur prompt simple.
- Hypothèse DEC-014 (template Jinja complexe non appliqué) acceptée
  initialement. Plan C (DEC-015) tenté sur cette base : Qwen2.5-Coder
  a un template embarqué simple, devrait fonctionner. Échec identique.
- **Test discriminant proposé par CLI** : ajouter un troisième modèle
  (Qwen2.5-3B-Instruct-4bit, template simple, taille 10× plus petite)
  pour discriminer "template" vs "taille" vs "serveur". Résultat :
  les 3 modèles donnent `prompt_tokens=25` figé, indépendamment de
  tout. **Conclusion : c'est Osaurus qui n'applique pas les templates**,
  pas une caractéristique des modèles.
- Validation finale par test croisé : `mlx_lm.server` (Apple ML
  Explore) lancé sur le même fichier modèle Qwen2.5-Coder-32B →
  `prompt_tokens=39`, contenu cohérent. La preuve est dans le
  serveur, pas dans le modèle.
- Session mise en pause en attendant que Desktop #5 capture les
  décisions.

**Deuxième partie (2026-05-19) — PATCH #3 du brief, validation finale**

- Reprise après acceptation Desktop #5 des DEC-016/017/018/019 et
  émission du PATCH #3 dans le brief CLI_PROMPT_002.
- 3 tests live sur `mlx_lm.server` + Qwen2.5-Coder-32B-Instruct-4bit :
  - `/v1/models` → modèle exposé
  - `/v1/chat/completions` simple → `prompt_tokens=39`, "2+2 equals
    4, and the capital of France is Paris.", `finish_reason: "stop"`
  - Fibonacci memoization < 10 lignes → code Python idiomatique,
    `cached_tokens: 5` (KV cache fonctionnel)
- `.env.example` réécrit (variables renommées `OSAURUS_URL` →
  `MLX_SERVER_URL`, `OPTIMAI_MODEL` avec id HF complet), `.env` local
  créé, `config/blacklist.txt` consolidé (anti-`mlx_lm.server --host
  0.0.0.0` ajouté, règles anti-Osaurus conservées en défense en
  profondeur).
- Sanity checks tous passés : `uv run python -c "import optimai"`,
  `uv run ruff check .`, `uv run pytest`, `git check-ignore -v .env`.
- Commit local `05d8bae` (push réservé à Hassan, DEC-009). Étapes 1-8
  du PATCH #3 toutes ✅, étapes 11-12 confiées à Desktop #6.
- Leçon principale (cf. règle ajoutée à CLAUDE.md) : un diagnostic
  basé sur une hypothèse plausible mais non testée par discrimination
  peut coûter ~24h. Toujours prévoir le test discriminant **dans la
  DEC elle-même**.

### Session Desktop #5 (2026-05-19)

- Bascule documentaire post-test-discriminant CLI #2 : DEC-016
  (diagnostic corrigé, supersède DEC-014), DEC-017 (`mlx_lm.server`
  remplace Osaurus, supersède DEC-003), DEC-018 (Qwen2.5-Coder-32B
  confirmé sur preuves, supersède DEC-015), DEC-019 (cleanup Osaurus,
  📝 Proposed).
- Encadrés "Statut final — Superseded" ajoutés en tête de DEC-003,
  DEC-014, DEC-015.
- Émission du PATCH #3 dans `.drafts/claude/CLI/CLI_PROMPT_002_osaurus_setup.md`.
- Rédaction du `HANDOVER_session_2026-05-19.md` pour assurer la reprise
  (chronologie complète, état machine snapshot, ce-que-faire / ce-que-
  ne-pas-faire pour la session suivante).
- Commit Desktop #5 fait par Hassan (`git push` à sa charge, DEC-009).

### Session Desktop #6 (2026-05-19)

- DEC-019 passée à ✅ Accepted (déclencheur : commit local CLI #2
  `05d8bae`, tous critères ✅, chaîne mlx_lm.server prouvée stable).
- Cleanup Osaurus exécuté étape par étape avec validation explicite
  Hassan avant chaque `rm -rf` (DEC-009) :
  - Vérification préalable que la nouvelle chaîne tient (test 2+2,
    `prompt_tokens=34`)
  - `brew uninstall --cask osaurus` (réversible, OK)
  - `rm -rf ~/.osaurus/` (~6 MB, OK)
  - `rm -rf ~/MLXModels/` (**~19 GB libérés**, après vérification
    `lsof -p <mlx_lm.server>` confirmant aucune dépendance vivante)
  - Caches macOS, plists, HTTPStorages, DiagnosticReport `.ips`,
    Crash plist, DMG Downloads, caches Homebrew résiduels
  - Vérification fonctionnelle finale : `mlx_lm.server` HTTP 200,
    `/v1/models` ne liste plus que l'entrée HF officielle (l'entrée
    locale `~/MLXModels/...` a disparu immédiatement)
- Correction docstring `src/optimai/worker.py` pour aligner sur DEC-017
  (référence remplacée DEC-003 → DEC-017/018, mention `mlx_lm.server`).
- Mise à jour `CLAUDE.md` : stack mlx_lm.server, `uv sync --extra dev`,
  variables d'env renommées, règles de sécurité actualisées, historique
  sessions complété jusqu'à Desktop #6.
- Mise à jour `ROADMAP.md` : Phase 1 étape 3 ✅ (chaîne d'inférence
  validée + cleanup), étape 4 reformulée pour CLI #3 (shell.py +
  worker.py + premier test Pattern A), Phase 4 enrichie (launchd
  autostart, benchmark Qwen2.5 vs Qwen3-Coder, Low Power Mode).
- Note de session CLI #2 + Desktop #5 + Desktop #6 ajoutées dans
  `DECISIONS.md` (cette section).
- Rédaction `CLI_PROMPT_003_shell_worker_pattern_a.md` (brief pour
  CLI #3 : implémentation `shell.py` + `worker.py` + premier test
  bout-en-bout du Pattern A sur cas XCTest TBS).

### Session CLI #3 (2026-05-19)

- Brief `CLI_PROMPT_003` exécuté bout-en-bout. 5 livrables : `config.py`
  (Settings pydantic, limites DEC-007, singleton `lru_cache`), schemas
  Pattern A (`DiagnoseSpec` + `DiagnoseReport` ; `Execute*` hors
  périmètre), `shell.py` (sandboxé : blacklist, sandbox `cwd`, env sans
  secrets, troncature 10 KB), `worker.py` (client async OpenAI-compat,
  extraction `cached_tokens`), PoC scripté XCTest. **52 tests passent,
  ruff clean, PoC converge en 2 itérations** (`status=complete`) sur
  machine en état « Xcode actif ». Commit local `96c70ca` (push réservé
  Hassan, DEC-009).
- Décisions de latitude (DEC-009) : `httpx.MockTransport` plutôt que
  `respx` (zéro dep dev en plus) ; `pytest pythonpath=["src"]` pour
  contourner l'install editable `uv` **flaky sur le chemin iCloud** ;
  `field_validator` de `workdir` attrape `FileNotFoundError` et relève
  `ValueError` (Pydantic v2 ne wrappe pas les `OSError`) ; **timeout
  par-commande traité comme récupérable** (réinjecté au worker ; le vrai
  garde-fou de budget reste le timeout global, DEC-007) ; **system prompt
  cadré** (périmètre toolchain, interdiction de scanner le FS) après une
  v1 trop ouverte qui partait en `find` dans `$HOME` sans converger.
- Remontées principales : install editable `uv` flaky sur chemin iCloud
  (cause racine adressée par DEC-020) ; tendance du worker à
  sur-investiguer tant que le périmètre n'est pas cadré (→ contrat
  Cortex↔Hands, fusionné dans DEC-021).

### Session Desktop #7 (2026-05-20)

- Lecture HANDOVER Desktop #6 + REPORT CLI #3. **Inspection rapide** des
  5 modules livrés : qualité confirmée (échec explicite partout, blacklist
  avant spawn, env minimal sans secrets parent), `owns_client` de
  `worker.chat` pré-satisfait déjà la reco « client partagé » de CLI #4.
  3 observations forward portées au brief CLI #4 : kill de sous-arbre sur
  timeout (à traiter au Pattern D — Execute peut forker), `validate_path_in_sandbox`
  non câblé dans `run()` (intentionnel Phase 1, sandbox = `cwd`), `.env`
  résolu relativement au `cwd` (→ « lancer depuis la racine repo »).
- **DEC-020 rédigée puis exécutée et validée** (✅ Accepted le jour même) :
  sortie iCloud → `~/Developer/optimAI` local, Git unique mécanisme de
  sync. Justifications : MCP Filesystem non fiable sur chemin iCloud
  (impact Desktop à chaque session) + install editable flaky (impact
  runtime étape 9) ; projet intrinsèquement lié au Mac Studio (env Qwen),
  MacBook en appoint sans test → perte de sync native sans conséquence.
  `.drafts/` déménagé avec le projet (non-sync inter-machines assumé).
  Déménagement exécuté par Hassan (Qwen arrêté SIGTERM → `mv` → `.venv`
  régénéré → repoint MCP) ; sanity verte au nouveau chemin (52 tests,
  ruff clean, `import optimai` sain, zéro `ModuleNotFoundError`).
- **DEC-007 annotée** : précision timeout par-commande (récupérable) vs
  timeout global de boucle (= le vrai budget).
- Docs synchronisées : `ROADMAP.md` (Phase 1 étape 4 ✅, étape 5
  partielle — schemas A faits, Execute restent), `CLAUDE.md` (historique
  CLI #3 + Desktop #7, sync Git, base path, rappel « racine repo »),
  index `DECISIONS.md`, toilettage commentaire `pyproject.toml`.
- **DEC-021 rédigée** (📝 Proposed) : architecture Dispatcher = moteur de
  boucle unique + registre de patterns (Strategy), suite à l'arbitrage
  (b) + anticipation de la croissance du nombre de patterns (Phase 3).
  Écarte explicitement la fragmentation `dispatcher_*.py`. Fusionne
  l'ex-candidate DEC-021 (contrat Cortex↔Hands : domaine via
  `spec.context`). Passe ✅ quand Execute (CLI #5) se branche sans
  retoucher `base.py`.
- Rédaction `CLI_PROMPT_004_*.md` (périmètre **Diagnose seul**, DEC-021) :
  `dispatcher.py` moteur de boucle pur (sans rendu console),
  `patterns/base.py` (Protocol `Pattern` + registre `@register`),
  `patterns/diagnose.py` (stratégie A branchée, system prompt factorisé).
  Execute reporté à CLI #5 (validation du contrat avant 2ᵉ pattern).
  ROADMAP Phase 1 étapes 6 + 8.
- Runbook déménagement fourni à Hassan en clôture de session.

### Session CLI #4 (2026-05-20)

- Brief `CLI_PROMPT_004` exécuté bout-en-bout (périmètre Diagnose seul,
  DEC-021). Livrables (commit local `57382f0`) : `patterns/base.py`
  (Protocol `Pattern` + `Step` dataclass + registre `@register`),
  `dispatcher.py` réécrit (moteur unique agnostique), `patterns/diagnose.py`
  (stratégie A), `patterns/__init__.py` (import side-effect d'enregistrement),
  PoC réduit à un thin wrapper + smoke-test `@pytest.mark.live`.
  **91 tests actifs + 1 live, ruff clean** (+39 vs CLI #3).
- **Validation DEC-021 (sur Diagnose)** : les 2 gardes architecturaux
  passent — `test_dispatcher_module_has_no_diagnose_imports` (le moteur
  ne référence aucun symbole Diagnose) et
  `test_system_prompt_carries_no_xctest_hard_knowledge` (le prompt ne
  contient plus le domain knowledge XCTest). Le contrat `Pattern` a été
  naturel pour Diagnose (découpe ligne-à-ligne du PoC, sans contorsion).
- **Preuve empirique du contrat Cortex↔Hands** : smoke live (validé par
  Hassan, `mlx_lm.server` actif) → le worker choisit `xcode-select -p`
  alors que la commande ne figure plus dans le system prompt mais dans
  `spec.context`. Converge en 2 itérations, verdict identique à CLI #3.
- Décisions de latitude (DEC-009) : `Step` = dataclass frozen à
  discriminant `kind` ; `build_report` reçoit un `final_payload: dict|None`
  extrait par le moteur (le pattern ne walke pas la trace) ; rendu console
  = `logging` standard (pas de callback, DEC-002) ; **4ᵉ méthode
  `operator_text(spec)` ajoutée au Protocol** pour cibler le scrub
  blacklist pré-vol (`spec.goal` vetté, `spec.context` intentionnellement
  épargné car il porte légitimement des fixes nommés).
- Points remontés pour Desktop : (5a) `iterations_used` partagé via
  `list[int]` à 1 élément pour survivre au cancel `asyncio.wait_for`
  (« laid mais isolé » — dette technique) ; (5c) import side-effect dans
  `patterns/__init__.py` → auto-discovery `pkgutil` à envisager en Phase 3
  (YAGNI avant) ; per-cmd timeout récupérable à trancher par DEC pour
  Execute.

### Session Desktop #8 (2026-05-20)

- Lecture du REPORT CLI #4 + **inspection réelle** de `patterns/base.py`
  et `dispatcher.py`. Verdict : excellent résultat, les 2 gardes
  architecturaux sont la vraie victoire (DEC-021 défendue par le code, pas
  par la discipline). Le contrat Cortex↔Hands est prouvé sur Diagnose.
- **DEC-021 reste 📝 Proposed** : le test réel (le contrat tient-il sur un
  2ᵉ pattern ?) n'a pas encore eu lieu — Diagnose seul = un point, pas une
  droite.
- **Critère DEC-021 précisé** (annotation dans la DEC) : le critère
  littéral « sans toucher `base.py` » devient « extension rétrocompatible
  OK / refonte KO » (Open/Closed). Précisé à froid avant CLI #5 pour ne
  pas réinterpréter le critère a posteriori. La 4ᵉ méthode `operator_text`
  déjà ajoutée + le hook `on_command_timeout` pressenti sont des extensions
  rétrocompatibles, donc compatibles avec DEC-021.
- **DEC-022 rédigée** (📝 Proposed) : politique de timeout par-commande
  **par-pattern**. Diagnose = recover (read-only, sûr) ; Execute = abort
  (commande mutante timeoutée = état inconnu, échec explicite DEC-008 §4) ;
  défaut sûr = abort (un pattern qui n'explicite rien n'hérite pas d'une
  récupération risquée). Mécanisme (hook sur le Protocol) = latitude CLI #5,
  premier test concret du critère DEC-021 précisé.
- Dette technique notée (non bloquante) : 5a (`list[int]` holder) — à
  revoir lors d'une passe de refacto du moteur (axe 2 DEC-021).
- Docs synchronisées : `ROADMAP.md` (étape 6 ✅, étape 7 = Execute/CLI #5,
  Phase 1 → étape 7), `CLAUDE.md` (header, stack Dispatcher, historique
  CLI #4 + Desktop #8, compte DEC → 22), index `DECISIONS.md` (DEC-022),
  README CLI (brief #4 ✅, brief #5 émis, correction sync iCloud → DEC-020).
- Rédaction `CLI_PROMPT_005_*.md` (Pattern D Execute, branché sur DEC-022).
  Sémantique Execute tranchée : **option (1) worker-driven dans un pack
  borné** (`ExecuteSpec.commands` fourni par le Cortex ; le worker exécute
  le pack via la boucle, n'improvise aucune commande mutante hors pack).
  Écarté : (2) entièrement scripté — n'utiliserait ni le worker ni la
  boucle, donc ne testerait pas DEC-021. Confirmé par Hassan en clôture.

### Session CLI #5 (2026-05-21)

- Brief `CLI_PROMPT_005` exécuté bout-en-bout (commit local `210fecd`).
  Livrables : hook `on_command_timeout` sur le Protocol (`base.py`),
  branchement `_resolve_timeout_policy` dans le handler `CommandTimeout`
  (`dispatcher.py`) + `stop_reason="command_timeout"`, schemas
  `ExecuteSpec` (pack ordonné non-vide) / `ExecuteReport` (compact :
  `summary` + `failed_command`), `patterns/execute.py` (option (1),
  `abort` sur timeout), Diagnose `recover` explicite. **124 tests actifs
  (+33) + 1 live, ruff clean.** Garde architectural étendu
  (`no_execute_imports`).
- **Verdict DEC-021 = PASSE** : contrat étendu par +1 méthode, 0 signature
  existante modifiée ; moteur changé uniquement à l'endroit du handler
  (consultation générique du hook) ; 2 gardes architecturaux verts.
- Décisions de latitude (DEC-009) : invariant de sûreté DEC-022 placé
  **dans le moteur** (`_resolve_timeout_policy`, défaut `abort`) plutôt
  que dans le Protocol → un pattern qui oublie la méthode OU dont le hook
  lève hérite d'`abort` ; `ExecuteReport` compact (2 champs, la trace
  exhaustive vit dans `commands_executed`) ; auto-fill `failed_command`
  depuis la dernière commande sur `status=error` ; `command_timeout` dans
  le `StopReason` partagé (pas un Literal par report) ;
  `_resolve_existing_workdir` factorisé (sans changer le comportement de
  `DiagnoseSpec`).
- Points remontés (§6) : smoke live Execute **non écrit** (optionnel,
  ~30 lignes — non bloquant car l'intégration hook est couverte par tests
  shell réel + worker mocké) ; smoke live Diagnose non rejoué (régression
  improbable) ; ambivalence Protocol-déclare / moteur-garantit (volontaire,
  safe-by-default) à arbitrer si le Protocol devient un jour strict.

### Session Desktop #9 (2026-05-21)

- Lecture REPORT CLI #5 + **inspection réelle** de `base.py`,
  `dispatcher.py`, `execute.py` (le verdict « PASSE » du résumé vérifié
  dans le code, pas accepté sur parole).
- **DEC-021 → ✅ Accepted** : Execute branché par extension rétrocompatible
  (+1 méthode, 0 signature modifiée), moteur toujours agnostique (2 gardes
  verts), 2 patterns réels désormais (A recover, D abort). Verdict
  empirique ajouté à la DEC.
- **DEC-022 → ✅ Accepted** : hook implémenté, défaut sûr `abort` placé
  dans le moteur. Mention spéciale au `try/except` qui rabat un hook bogué
  sur `abort` — au-delà du strict demandé, bonne application de DEC-008 §4.
- Reliquats notés pour plus tard (non bloquants) : smoke live Execute
  (~30 lignes, à demander si désiré) ; dette `list[int]` holder pour
  `iterations_used` (refacto moteur, axe 2 DEC-021) ; ambivalence
  Protocol-strict vs safe-by-default (préférence actuelle : safe).
- HANDOVER Desktop #9 → #10 rédigé (`.drafts/claude/CLI/HANDOVER_desktop9.md`) :
  Phase 1 quasi-bouclée côté patterns, prochain gros morceau = serveur MCP
  (ROADMAP étape 8).
- Phase 1 : étapes 5 + 7 ✅ (schemas A & D complets ; Pattern D livré).
  Reste étapes 8-11 (serveur MCP, intégrations Desktop/CLI, doc).

### Session Desktop #12 (2026-05-23)

- Reprise Phase 2 (lecture DECISIONS + HANDOVER #11 + ROADMAP). Phase 1
  confirmée close (commit `3f8976e`). Les notes de session #10 et #11 ne sont
  pas détaillées ici — elles sont tracées dans `ROADMAP.md` (étapes 9-11) et
  les HANDOVERs `.drafts/claude/CLI/`.
- **DEC-024 rédigée et actée** (✅ Accepted) : périmètre de réversibilité
  Phase 2. Distinction des deux portées de rollback — **atomicité intra-appel**
  (transactionnelle, dans le pattern) vs **réversibilité de lot inter-appels**
  (point de restauration sur plusieurs appels), la seconde bloquée par la
  statelessness MCP. Phase 2 = atomicité intra-appel seulement (helper snapshot
  dans le pattern, copie temp éphémère, **pas de git**) ; réversibilité de lot
  (autorité git locale, outils `checkpoint`/`resolve`) reconnue **inévitable**
  mais **reportée post-Phase 3** (balance gains/coûts, maturité, dette de compat
  antérieure — verdict Hassan). Corollaire de sûreté acté : l'acte mutant de
  B/C est **déterministe et Cortex-sourced** (édits/contenu fournis dans le
  spec, appliqués par code ; worker = validation + verdict, pas mutation —
  distinct de l'option (2) scriptée écartée pour Execute). Esquisse de la
  portée (2) conservée dans la DEC.
- `ROADMAP.md` mis à jour : Phase 2 précisée (atomicité intra-appel, DEC-024,
  application déterministe, diff `difflib`) ; réversibilité de lot ajoutée
  comme future feature post-Phase 3 (tête de Phase 4).
- Rédaction `CLI_PROMPT_007_patch_create_patterns.md` (brief B+C groupés, sous
  DEC-024 + test DEC-021 sur l'extension du contrat `Pattern` pour la nouvelle
  phase de mutation déterministe). Séquencé B d'abord (banc d'essai du helper
  d'atomicité + extension de contrat), C ensuite ; point d'arrêt naturel après
  B si l'extension dérape (verdict DEC-021 à remonter avant de coder C).
- **CLI #7 livré en une passe** (commit local `fb6d2b5`) : Patterns B & C,
  helper d'atomicité `snapshot.py`, hooks `mutate`/`enrich_report` via `getattr`
  (verdict DEC-021 : ✅ extension rétrocompatible, aucune signature touchée,
  boucle non refondue), 210 tests verts, 4 gardes architecturales OK,
  `optimai_patch`/`optimai_create` exposés sans toucher `server.py`.
- **Incident déploiement MCP (résolu)** : `optimai_patch` semblait absent côté
  Desktop. Cause racine = **plusieurs instances du serveur MCP en collision sur
  stdio** (lancements manuels en parallèle du spawn Desktop) → crash-loop
  `transport closed`, liste d'outils instable. Hypothèses écartées par lecture
  (install périmé, `.pyc`) grâce aux commandes de confirmation avant tout
  correctif. Règle : **un seul lanceur du serveur MCP = Desktop** ; le serveur
  MCP est en **stdio** (n'utilise pas le port 1337, qui est celui de
  `mlx_lm.server`). Accès `~/Library/Logs/Claude` + `/private/tmp` ajoutés au
  Filesystem MCP.
- **Smoke live B/C** (`/private/tmp/optimai-live-bc`, piloté par Desktop via
  MCP, worker réel Qwen) : C-succès ✅, B-succès ✅ (worker bien en rôle
  validateur, ne re-mute pas — pari sémantique DEC-024 confirmé sur vrai
  worker). **B-rollback ❌ → bug structurel trouvé** : validation KO (`exit:1`)
  mais `status="complete"` → pas de rollback → fichier laissé cassé sur disque.
- **DEC-024 amendée** (verdict Hassan) : sémantique du statut d'échec « ceinture
  + bretelles » — socle **déterministe** (moteur force `error` si la commande de
  **validation désignée** sort exit≠0, non contournable) **+** couche **worker**
  additive (déclarer un échec sémantique sur exit 0 + sortie suspecte). Invariant :
  le déterministe prime, le worker ne peut jamais transformer un exit≠0 de
  validation en succès. Impose de lever le `status="complete"` codé en dur de
  `_run_loop`, en restant rétrocompatible A/D (DEC-021). CLI invité à proposer
  une meilleure alternative si l'invariant tient.
- Rédaction `CLI_PROMPT_008_failure_status_fix.md` (correctif + test live
  reproduisant B-rollback). Fichier cassé `hello.py` **conservé** comme cas de
  reproduction. Smoke live restant (C-swift-skip, dégradation propre `swiftc`
  absent) **en attente** après le correctif.
- **CLI #8 livré** (commit `9b7dffd`) : cascade à 2 couches via hooks optionnels
  `is_validation_command` (Layer 1 déterministe) + `worker_declares_failure`
  (Layer 2 additif), Protocol inchangé, A/D inertes, 227 tests. **B-rollback
  re-testé en live après fix : ✅** `status=error` + fichier restauré à l'octet
  (critère de clôture du bug atteint).
- **Smoke C-swift** : `swiftc` **présent** sur la machine → validation Swift
  réelle réussie (bonus : `swiftc -parse` prouvé en live, utile pour TBS). Le
  chemin de *dégradation* (outil absent) n'a donc pas été exercé.
- **Collision trouvée par lecture de `create.py`** (raisonnée, non observée) :
  le Layer 1 déterministe de #8 **rollback un fichier valide si l'outil de
  validation est absent** (`swiftc -parse` → exit 127 → traité comme échec de
  validation). Non déterministe (dépend que le worker fasse `which` d'abord ou
  non). La dégradation propre reposait seulement sur une consigne du
  `system_prompt`, neutralisée par #8 qui a retiré au worker l'autorité sur le
  statut.
- **DEC-024 précisée** (verdict Hassan) : invariant ajouté — *un outil de
  validation absent n'est pas un échec de validation* ; un « command not found »
  (exit 127) ne doit jamais rollback un fichier valide → dégradation propre
  (skip + note), **décidée de façon déterministe côté code**, pas par le worker.
  Comment laissé à CLI (préférence Desktop : vérifier l'outil avant via
  `shutil.which` → `validation_command_for` renvoie `None` → pas de Layer 1).
- Rédaction `CLI_PROMPT_009_validation_tool_absent.md` (résout la collision +
  tests mockés déterministes du cas outil-absent — le trou de couverture).

**Fin de session #12 — clôturée (mise à jour Desktop #13)** : commit CLI `9b7dffd`
(#8) + CLI #9 (`CLI_PROMPT_009`, cas outil-absent) exécutés et poussés. Phase 2
close. Les artefacts Desktop #12 ont été committés par Hassan (DEC-009).

### Session Desktop #13 (2026-05-25)

- **Lancement de la Phase 3** (enrichissement collaboratif). Reprise via
  DECISIONS + HANDOVER #12 + ROADMAP ; Phase 2 confirmée close.
- **DEC-025 actée** (✅) : méthodologie de collecte de patterns. Instrument
  générique paramétré par projet (`.drafts/claude/phase3/COLLECT_PROMPT.md`),
  lancé depuis chaque espace-projet Claude (contrainte : scope
  `conversation_search` par projet — une seule instance ne peut pas collecter
  cross-projet) ; accès au repo optimAI pour comparer les candidats à
  l'existant (réducteur de faux positifs) ; banc d'essai TBS d'abord. Passée ✅
  sur preuve (rapport TBS exploitable, filtrage juste, 0 correction requise).
- **Trois collectes exécutées par Hassan** (TBS pilote, puis Bassmati + QNAP) →
  rapports `.drafts/claude/phase3/CANDIDATES_*.md` → **agrégation cross-projet**
  `docs/PATTERN_CANDIDATES.md`. Résultats structurants : (a) un seul nouveau
  pattern à construire — **E/Scan**, prouvé sur les 3 projets ; (b) le reste de
  la valeur locale déjà couvert par A/D (specs-types à documenter) ; (c)
  **découverte : `ssh-remote` est une *dimension d'exécution distante*
  transverse** (pas un pattern) qui gate l'opérationnel QNAP/prod — dossier
  d'instruction déjà prêt dans `PATTERN_CANDIDATES.md` (File B) pour une DEC
  future.
- **DEC-026 actée** (✅, validée par Hassan sur 3 points) : non-divulgation des
  valeurs de secrets en sortie. Raffinement de DEC-008 §3 — la vraie tension
  n'est pas l'entrée (le worker peut voir une valeur fournie comme motif, via
  `context`) mais la **sortie** (report remonté au Cortex + log disque). Trois
  vecteurs de fuite identifiés par lecture des schémas : `matches[].text`,
  `commands_executed[].cmd` (la commande `grep "<valeur>"` contient le motif !),
  champs libres. Redaction **déterministe côté Dispatcher** (pas le worker —
  cohérent DEC-024), avant retour ET avant log. Coût fonctionnel nul (compte +
  localisation suffisent).
- **Brief `CLI_PROMPT_010` → Pattern E livré (CLI #10, commit `fd810e0`)** :
  read-only (moule Diagnose, politique `recover`), motifs
  `required`/`forbidden`/`secret_patterns` Cortex-sourced, sources FS (grep) +
  HTTP (GET), report `ScanReport` (forme nouvelle : `matches` + verdict
  pass/fail). **307 tests (+58), 5 gardes architecturales** (`no_scan_imports`
  nouveau), ruff clean. **5ᵉ preuve DEC-021** : `base.py` et `server.py`
  **strictement non touchés** ; redaction branchée via `getattr(spec,
  "secret_patterns", [])` ; `optimai_scan` exposé par le registre. DEC-026
  vérifiée sur les 3 vecteurs + persistance log (filtre logging sur handlers
  `optimai`) + inertie A/D/B/C.
- **Convention « Session CLI ID » généralisée** (demande Hassan) : tout REPORT CLI
  consigne désormais son ID de session en en-tête — inscrit dans la structure-type
  des briefs (README CLI). Garde le lien brief→report→session.
- **Housekeeping docs** (rattrapage du reliquat #11/#12) : `ROADMAP.md` (Phase 2
  → ✅, Phase 3 → 🔄 avec le fait/à-venir, sujet priorisation ajouté), `CLAUDE.md`
  (en-tête Phase 3, compte DEC 22→26, historique #11→#13), index `DECISIONS.md`
  (DEC-025/026), README CLI (briefs #009/#010, convention Session CLI ID).
- **À committer par Hassan (DEC-009)** — versionné : `decisions/DEC-025-*.md`,
  `decisions/DEC-026-*.md`, `docs/PATTERN_CANDIDATES.md`, `DECISIONS.md`,
  `ROADMAP.md`, `CLAUDE.md` (commit docs proposé « docs: Phase 3 — pattern
  collection + secret-value redaction », companion de `fd810e0`). Non versionné
  (gitignored, `.drafts/`) : instrument de collecte, 3 rapports CANDIDATES, brief
  #010, README CLI.
- **Sujet d'ouverture Desktop #14** : priorisation d'optimAI par le Cortex (voir
  HANDOVER #14).