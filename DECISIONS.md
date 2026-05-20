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
| [DEC-020](decisions/DEC-020-project-local-disk-git-sync.md) | Projet hors iCloud — disque local, sync via Git | 🔄 | 2026-05-20 |
| [DEC-021](decisions/DEC-021-dispatcher-engine-pattern-registry.md) | Architecture Dispatcher — moteur unique + registre de patterns (Strategy) | 📝 | 2026-05-20 |

## Décisions à venir

_Aucune décision en cours de rédaction._ La candidate DEC-021 (contrat
Cortex↔Hands : domaine via `spec.context`) a été fusionnée dans la
DEC-021 ci-dessus (même question : « qu'est-ce qu'un pattern et que
doit-il fournir ? »).

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
- **DEC-020 rédigée** (🔄 In progress) : sortie iCloud → `~/Developer/optimAI`
  local, Git unique mécanisme de sync. Justifications : MCP Filesystem non
  fiable sur chemin iCloud (impact Desktop à chaque session) + install
  editable flaky (impact runtime étape 9) ; projet intrinsèquement lié au
  Mac Studio (env Qwen), MacBook en appoint sans test → perte de sync
  native sans conséquence. `.drafts/` déménage avec le projet (non-sync
  inter-machines assumé). Owner du `mv` = Hassan (entrelacé avec le repoint
  MCP, Hassan-only ; timing critique : `mv` avant repoint).
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
