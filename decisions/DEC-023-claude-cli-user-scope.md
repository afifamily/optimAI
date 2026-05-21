# DEC-023 : Intégration Claude CLI — scope `user` (`~/.claude.json`), pas project/local

**Date** : 2026-05-21
**Statut** : ✅ Accepted (choix de scope acté Desktop #11 sur validation
Hassan ; exécution via le runbook étape 10 + test e2e par projet restent à
faire — voir « Implémentation »)
**Déclencheur** : HANDOVER Desktop #10 (point « vérifier, ne pas deviner »
le format `.mcp.json` attendu par Claude CLI) + vérification sur la doc
officielle Claude Code (`code.claude.com/docs/en/mcp`, Desktop #11)
**Lié à** : [DEC-005](DEC-005-mcp-stdio-local.md) (MCP stdio local —
l'intégration CLI réutilise le même serveur), [DEC-020](DEC-020-project-local-disk-git-sync.md)
(repo local sur le Mac Studio → chemin absolu, non portable),
[DEC-009](DEC-009-meta-architecture-desktop-cli.md) (édition config hôte =
Hassan), ROADMAP Phase 1 étape 10

## Contexte

L'étape 9 (Desktop #10) a intégré optimai dans **Claude Desktop** :
une entrée sous `mcpServers` dans `claude_desktop_config.json`, serveur
stdio lancé par `/opt/homebrew/bin/uv --directory <repo> run python -m
optimai.server`, validée bout-en-bout (`optimai_diagnose` réel,
`status=complete`).

L'étape 10 vise le **critère de complétion Phase 1** : « depuis Claude
Desktop **ou CLI**, dans **n'importe quel projet** (TBS / Bassmati / QNAP),
demander un diagnose / execute et obtenir un rapport compressé ». Côté CLI,
il faut donc rendre les outils `optimai_diagnose` / `optimai_execute`
visibles depuis chaque projet.

Le HANDOVER #10 avait raison de ne **pas** supposer que le format CLI est
identique à Desktop. Vérification faite sur la doc officielle :

- **La forme d'une entrée est quasi identique à Desktop** : même clé racine
  `mcpServers`, mêmes champs `command` / `args` / `env`, `"type": "stdio"`
  facultatif (inféré de la présence de `command`). Expansion de variables
  d'env (`${VAR}`, `${VAR:-defaut}`) supportée — non nécessaire ici (aucun
  secret dans l'entrée, le `.env` est lu par `config.py` au cwd `--directory`).
- **La vraie différence est la notion de *scope*** : Claude CLI stocke la
  config MCP à **trois** endroits, qui changent *où* vit la config et
  *dans quels projets* l'outil apparaît :

  | Scope | Apparaît dans | Partagé équipe | Stocké dans |
  |-------|---------------|----------------|-------------|
  | `local` (défaut) | projet courant seulement | non | `~/.claude.json` (sous le chemin projet) |
  | `project` | projet courant seulement | oui (via Git) | `.mcp.json` à la racine du repo |
  | `user` | **tous** tes projets | non (privé) | `~/.claude.json` (global) |

C'est ce choix de scope qu'il fallait trancher — pas la syntaxe de l'entrée.

## Alternatives évaluées

| Option | Visibilité | Pollue les repos ? | Portable ? | Maintenance | Verdict |
|--------|-----------|--------------------|-----------|-------------|---------|
| **`project`** (`.mcp.json` × 3 repos) | par-projet (les 3) | oui (1 fichier/repo) | ❌ chemin absolu Mac-bound | 3× fichiers + approbation CLI par repo | Écartée |
| **`local`** (défaut, `~/.claude.json` par chemin projet) | par-projet (les 3) | non | s/o (hors repo) | 3× `claude mcp add` séparés | Écartée |
| **`user`** (`~/.claude.json`, une entrée) | **tous** les projets | non | s/o (hors repo) | 1 commande | **Retenue** |

Détail du rejet de `project` (l'option « naturelle » qu'on aurait pu
choisir par défaut) : un `.mcp.json` committé est *conçu* pour être
portable et partagé en équipe. Or notre entrée porte un **chemin absolu**
`/Users/hassanafif/Developer/optimAI` (DEC-020 : repo local lié au Mac
Studio). Committer ce fichier donnerait l'illusion d'un partage qui
**casserait sur toute autre machine** — à rebours de la raison d'être du
scope project. Il faudrait alors le gitignorer dans chaque repo, ce qui
combat le grain de la fonctionnalité. De plus, Claude CLI demande une
**approbation** avant d'utiliser un serveur project-scopé (sécurité), à
refaire par repo.

## Décision

**Intégrer optimai au scope `user`** : une entrée unique dans
`~/.claude.json`, qui rend `optimai_diagnose` / `optimai_execute` visibles
depuis **tous** les projets de Hassan sur le Mac Studio, sans déposer ni
gitignorer quoi que ce soit dans aucun repo.

Rationale :
- optimAI est un **outil personnel** (ROADMAP « hors périmètre :
  multi-utilisateurs ») → la dimension « partage équipe » de project scope
  est sans objet.
- optimAI est **lié au Mac Studio** (DEC-020) → un chemin absolu est correct
  pour Hassan mais non committable ; user scope (hors repo) évite le piège.
- Le critère Phase 1 vise « **n'importe quel** projet » → user scope le
  satisfait littéralement et en une commande, là où project/local
  demanderaient 3 opérations et ne couvriraient que les 3 repos nommés.
- **La question gitignore du HANDOVER #10 devient sans objet** : rien
  n'atterrit dans TBS / Bassmati / QNAP.

## Implémentation (par Hassan — DEC-009, édition config hôte)

Opération réservée à Hassan : `claude mcp …` écrit dans `~/.claude.json`
(config hôte). Détail des commandes, vérifications et test e2e dans
**`.drafts/claude/CLI/RUNBOOK_etape10_claude_cli.md`** (Desktop #11). Deux
voies équivalentes, au choix :

- **Réutiliser l'entrée Desktop déjà validée** (recommandé — source unique
  conceptuelle) : `claude mcp add-from-claude-desktop --scope user` puis
  sélectionner `optimai` (macOS supporté).
- **Poser l'entrée explicitement** :

  ```bash
  claude mcp add-json --scope user optimai \
    '{"type":"stdio","command":"/opt/homebrew/bin/uv","args":["--directory","/Users/hassanafif/Developer/optimAI","run","python","-m","optimai.server"]}'
  ```

Ne **pas** éditer `~/.claude.json` à la main (gros fichier, contient
projets + historique) → passer par `claude mcp …`.

Invariant `workdir` ≠ `--directory` (à garder en tête, détaillé dans le
runbook) : le `--directory` du serveur reste **toujours** optimAI (résout
`.env` / blacklist / `.venv`), quel que soit le projet depuis lequel
`claude` est lancé ; le `workdir` *passé à l'outil* est la **cible
d'investigation** (ex. le repo TBS). Claude CLI injecte aussi une variable
`CLAUDE_PROJECT_DIR` (dossier de lancement) dans l'env du serveur ; on ne
l'utilise **pas** (on veut un cwd figé sur optimAI, pas le dossier appelant).

Statut d'exécution : **en attente**. La DEC acte le *choix* ; l'exécution
(commandes ci-dessus + au moins un `optimai_diagnose` réel par projet,
worker `mlx_lm.server` lancé) clôt l'étape 10 de la ROADMAP. La chaîne
elle-même (serveur, dispatch, worker) est déjà prouvée en prod via Desktop
(étape 9) — l'étape 10 ne re-teste que la *visibilité CLI*, pas le moteur.

## Trade-offs

- ✅ Une seule commande, une seule source de vérité, visible partout
- ✅ Zéro fichier dans aucun repo → question gitignore sans objet, pas de
  chemin absolu non portable committé
- ✅ Privé à Hassan (cohérent avec la prudence secrets, même si ici aucun
  secret en clair)
- ✅ Réutilisable tel quel depuis l'entrée Desktop validée
  (`add-from-claude-desktop`)
- ⚠️ Charge optimai dans **tous** les projets, pas seulement les 3 nommés —
  sans conséquence pour un outil perso universel (Tool Search de Claude CLI
  défère de toute façon le chargement des schémas)
- ❌ Pas de versioning de la config d'intégration — acceptable : la config
  est triviale (4 args) et reproductible par une commande documentée ici

## Note technique (pour le futur)

- Les serveurs **stdio ne sont pas *auto*-reconnectés** par Claude CLI
  (l'auto-reconnexion avec backoff est réservée aux serveurs HTTP/SSE) : si
  le serveur meurt, tenter d'abord `/mcp` → `Reconnect` (reconnexion
  manuelle, sans quitter la session), relancer `claude` seulement si
  échec. Confirmé par le menu `/mcp` observé à l'étape 10 (Desktop #11).
- Avertissement Claude CLI si la sortie d'un outil MCP dépasse ~10 000
  tokens (`MAX_MCP_OUTPUT_TOKENS`, défaut 25 000) — nos reports A & D sont
  compacts par conception, large marge.
- Démarrage lent du serveur : `MCP_TIMEOUT` (ms) ajustable côté CLI si
  besoin.
