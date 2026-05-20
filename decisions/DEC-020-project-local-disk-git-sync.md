# DEC-020 : Projet hors iCloud — disque local, sync via Git uniquement

**Date** : 2026-05-20
**Statut** : 🔄 In progress (décision actée Desktop session #7 ; passe ✅
Accepted une fois le `mv` physique + repoint MCP + re-validation sanity
confirmés au nouveau chemin)
**Déclencheur** : Rapport CLI #3 §6 (install editable `uv` flaky sur
chemin iCloud) + constat Desktop récurrent (commandes MCP Filesystem non
fiables sur chemin iCloud)
**Lié à** : [DEC-011](DEC-011-python-3-12-baseline.md) (reproductibilité
de l'environnement), [DEC-009](DEC-009-meta-architecture-desktop-cli.md)
(répartition Desktop/CLI/Hassan)

## Contexte

Le projet optimAI vit dans iCloud Drive :

```
~/Library/Mobile Documents/com~apple~CloudDocs/Developer/my-projects/production/optimAI
```

Ce chemin pose deux problèmes concrets, l'un côté Desktop, l'autre côté
CLI/runtime :

1. **MCP Filesystem non fiable sur chemin iCloud (impact Desktop).** Les
   opérations MCP Filesystem se comportent mal sur un chemin iCloud
   virtualisé. C'est un irritant à *chaque* session Desktop, sur la
   surface d'outils dont Desktop dépend le plus.

2. **Install editable `uv` flaky (impact CLI/runtime, étape 9).** CLI #3
   a observé un `ModuleNotFoundError: No module named 'optimai'` par
   intermittence sous `uv run`, alors que le `.pth` editable
   (`_editable_impl_optimai.pth`) pointe sur un `src/` qui existe. Cause
   racine : la virtualisation de fichiers d'iCloud Drive (états
   « dataless ») combinée au chemin contenant des espaces et le segment
   `com~apple~CloudDocs`. Contourné en CLI #3 par `pytest pythonpath=src`
   + `sys.path.insert` dans le PoC, mais le problème reste latent et
   touchera `uv run python -m optimai.server` (ROADMAP Phase 1 étape 9).

Contexte d'usage qui rend la sortie d'iCloud acceptable, contrairement à
TBS / Bassmati :

- optimAI est **intrinsèquement lié au Mac Studio** : l'environnement
  d'inférence (`mlx_lm.server` + Qwen2.5-Coder-32B, DEC-017/018) n'existe
  que là. Aucun test réel n'est possible ailleurs.
- Le MacBook ne sert qu'à des **analyses / corrections ponctuelles sans
  test**. Git couvre ce besoin sans difficulté.
- La perte de la sync native multi-machines, bloquante pour TBS/Bassmati,
  est ici sans conséquence pratique.

## Alternatives évaluées

| Option | MCP fiable | Editable sain | Sync MacBook | Verdict |
|--------|-----------|---------------|--------------|---------|
| **Rester iCloud + palliatifs** (`pythonpath=src`, contournements MCP) | ❌ | ⚠️ contourné | ✅ native | Ne corrige pas la racine ; MCP reste cassé |
| **Sortir seulement `.venv` / parties problématiques** | ❌ | ✅ | ✅ native | Demi-mesure, complexité de séparation, MCP reste cassé |
| **Symlink `.drafts/` → iCloud, corps du projet local** | ✅ | ✅ | partielle | Complexité inutile (Desktop+CLI sur Mac Studio) |
| **Projet entier → disque local, Git unique sync** | ✅ | ✅ | via Git | **Retenu** — corrige les deux racines |

## Décision

**Déplacer optimAI vers `~/Developer/optimAI`** (disque local APFS), et
faire de **Git l'unique mécanisme de synchronisation** inter-machines.

- `.drafts/` (gitignored) **déménage avec le projet**. Conséquence
  assumée : il n'est plus synchronisé entre machines. Acceptable car
  Desktop et CLI tournent tous deux sur le Mac Studio ; le MacBook est en
  appoint sans besoin des briefs/handovers.
- La config MCP Filesystem de Claude Desktop (`allowed directories`) est
  **repointée** de l'ancien chemin iCloud vers `~/Developer/optimAI`.
- `pythonpath = ["src"]` (`pyproject.toml`) est **conservé** : il
  redevient un filet de sécurité (layout `src/` standard) au lieu d'être
  une béquille masquant la flakiness iCloud.

## Implémentation

Opération exécutée **par Hassan** (DEC-009). Justification du choix de
l'owner : ~6 commandes délibérées one-shot sur la racine du projet — hors
périmètre de la leçon Desktop #6 (« déléguer à CLI les *batches
d'investigation* > 5 commandes ») — et surtout entrelacée avec le repoint
de la config MCP Desktop, opération Hassan-only dont le timing est
critique (le `mv` physique **doit précéder** le repoint).

Ordre critique :

1. `mkdir -p ~/Developer`
2. `mv "<ancien chemin iCloud>/optimAI" ~/Developer/optimAI` (le `.git`
   suit — historique et remote intacts)
3. `cd ~/Developer/optimAI && rm -rf .venv && uv sync --extra dev` (le
   `.venv` et le `.pth` contiennent des chemins absolus → on régénère, on
   ne déplace pas)
4. Re-validation sanity au nouveau chemin : `uv run ruff check .`,
   `uv run pytest` (52 tests), `uv run python scripts/poc_diagnose_xctest.py`
5. **Repoint MCP Filesystem** Desktop → `~/Developer/optimAI` (config
   applicative, hors-repo)
6. Vérification : nouvelle session Desktop lit bien le projet au nouveau
   chemin

Le runbook détaillé (commandes exactes + checks intermédiaires) est fourni
par Desktop #7 en clôture de session.

Toilettage doc induit (fait par Desktop pendant que l'accès iCloud tient,
déménage avec le projet) :

- `pyproject.toml` : commentaire `pythonpath` mentionnant « iCloud-synced
  project path » → reformulé (raison = layout `src/`, plus = iCloud).
- `.gitignore` : entrées `# iCloud` (`.iCloudDrive`, `.iCloud~*`)
  deviennent mortes — laissées (coût nul) ou retirées.
- `CLAUDE.md` : toute mention de sync iCloud → sync Git ; rappel
  « lancer depuis la racine repo » (le `.env` est résolu relativement au
  `cwd`, `config.py` `env_file=".env"`).

## Trade-offs

- ✅ MCP Filesystem fiable à chaque session Desktop
- ✅ Install editable saine → étape 9 (`server.py`) sans contournement
- ✅ Plus de chemin à espaces / segment `com~apple~CloudDocs`
- ✅ `pythonpath=src` repasse de béquille à filet (échec explicite si
  régression, pas de masquage)
- ❌ Plus de sync native MacBook ↔ Mac Studio — mitigé : usage MacBook
  ponctuel sans test, discipline commit/push avant changement de machine
  (déjà la pratique, DEC-009 réserve le push à Hassan)
- ❌ `.drafts/` non synchronisé inter-machines — mitigé : Desktop + CLI
  sur Mac Studio, MacBook sans besoin des briefs

## Procédure de retour arrière

Réversible trivialement tant que rien n'est commit au nouveau chemin de
façon dépendante : `mv ~/Developer/optimAI "<ancien chemin iCloud>/optimAI"`
+ repoint MCP inverse. Aucune réécriture Git (chemins relatifs partout,
confirmé Desktop #7 : inspection des 5 modules + `pyproject.toml` +
`.env.example` + PoC, zéro chemin absolu iCloud).
