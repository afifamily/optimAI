# Troubleshooting — optimAI

> Pièges d'exploitation et diagnostic, capitalisés des étapes 9–10 (intégration
> Desktop + CLI). Pour l'architecture et les schémas, voir
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) et [`docs/PATTERNS.md`](docs/PATTERNS.md).

## Où regarder en premier

- **Logs serveur** : `logs/optimai.log` dans le repo optimAI (chemin
  `OPTIMAI_LOG_FILE`). Toute la vie du serveur y passe (enregistrement des
  outils, chaque itération, chaque commande shell, timeouts, violations).
- **État côté CLI** : `claude mcp get optimai` (déclaration + statut),
  `/mcp` dans une session (connexion + liste des outils + `Reconnect`).
- **Niveau de log** : `OPTIMAI_LOG_LEVEL=DEBUG` (défaut `INFO`). En DEBUG, les
  200 premiers caractères de stdout sont logués — utile, mais peut contenir des
  secrets, à n'activer que ponctuellement.

## Table de triage

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| `optimai` absent de `claude mcp list` | ajout échoué / mauvais scope | Refaire l'ajout (`--scope user`), voir [RUNBOOK étape 10](.drafts/claude/CLI/RUNBOOK_etape10_claude_cli.md) |
| `optimai` listé mais `/mcp` le marque en erreur au boot | env Python / `.venv` / chemin `uv` | Vérifier `which uv` = `/opt/homebrew/bin/uv` ; lire `logs/optimai.log` |
| Outils listés, mais l'appel échoue/traîne puis report `worker_error` | `mlx_lm.server` pas lancé | Lancer le worker (voir plus bas) |
| Report `blacklist_violation` sur une commande légitime | faux positif blacklist | Voir « Faux positif blacklist » |
| Report `error` avec « workdir does not exist » à l'appel | `workdir` inexistant ou mal résolu | Passer un chemin **absolu existant** |
| Le diagnostic investigue le mauvais dossier | `workdir` non passé ou pointé sur optimAI | Voir « `workdir` ≠ `--directory` » |
| Serveur tombé en cours de session | processus stdio mort | `/mcp` → `Reconnect` ; relancer `claude` si échec |
| `add-json` échoue | JSON mal formé / options après le nom | Voir « `claude mcp add-json` » |
| Sortie d'outil tronquée côté CLI | dépasse `MAX_MCP_OUTPUT_TOKENS` (~25 000) | Improbable (reports compacts) ; sinon réduire le périmètre |
| Démarrage serveur trop lent (timeout connexion) | budget de connexion CLI | `MCP_TIMEOUT=10000 claude` |

## Pièges conceptuels (les vrais coûteux)

### `workdir` (argument outil) ≠ `--directory` (lancement serveur)

Ce sont **deux chemins différents** qu'il ne faut jamais confondre :

- `--directory /Users/hassanafif/Developer/optimAI` est le `cwd` de **lancement
  du serveur**. Il reste **toujours** optimAI, quel que soit le projet depuis
  lequel `claude` est lancé. C'est ce qui fait que le serveur résout son `.env`,
  sa blacklist et son `.venv` au bon endroit.
- `workdir` est l'argument **passé à l'outil** : la **cible d'investigation**
  (ex. le repo TBS). C'est là que le worker exécute les commandes.

Symptôme d'une confusion : un diagnostic qui tourne sur optimAI au lieu du repo
visé. Correction : passer explicitement `workdir` = repo cible dans la demande
au Cortex.

**Pas de fallback `CLAUDE_PROJECT_DIR`.** Le CLI injecte cette variable
(dossier de lancement) dans l'env du serveur, mais optimAI ne s'en sert pas :
`workdir` est `required` et un appel sans lui échoue explicitement, par
conception (frontière Cortex/serveur DEC-001, échec explicite DEC-008 §4). Le
détail du raisonnement est dans [`docs/PATTERNS.md`](docs/PATTERNS.md#workdir--pourquoi-il-ny-a-pas-de-fallback).
`CLAUDE_PROJECT_DIR` a une place légitime *côté Cortex* (qui peut choisir de la
lire pour remplir `workdir`), jamais *côté serveur*.

### Chemin absolu de `uv` dans l'entrée MCP

L'entrée utilise `/opt/homebrew/bin/uv`, **jamais** le nom court `uv`. Le
processus qui lance le serveur n'a pas forcément le même PATH qu'un shell
interactif ; un `uv` non résolu = serveur qui ne démarre pas. Vérifier :
`which uv`.

### `.env` résolu au `cwd`, donc au `--directory`

`config.py` lit `.env` relativement au `cwd` (`env_file=".env"`). Comme le `cwd`
est fixé par `--directory` sur le repo optimAI, le `.env` du repo est bien lu —
mais **uniquement** parce que `--directory` pointe là. Modifier `--directory`
sans déplacer `.env` casserait la résolution.

### Hygiène stdout (transport stdio)

stdout est le canal JSON-RPC : tout `print`/bannière sur stdout corromprait le
protocole. Le logging est routé vers fichier + miroir `ERROR` sur stderr. Une
bannière FastMCP sur **stderr** au démarrage est normale et inoffensive.

## Lancer / vérifier le worker (opération Hassan)

Le serveur d'inférence n'est pas géré par optimAI. Le lancer dans un terminal
dédié :

```bash
mlx_lm.server \
  --model mlx-community/Qwen2.5-Coder-32B-Instruct-4bit \
  --host 127.0.0.1 --port 1337 --log-level INFO
```

Tant qu'il n'écoute pas sur `127.0.0.1:1337` (loopback, DEC-012), tout appel
d'outil converge vers un report `worker_error`. Vérifier qu'il tourne avant de
conclure à un bug d'optimAI.

## `claude mcp add-json` — forme exacte

Les options (`--scope`) viennent **avant** le nom du serveur, et le JSON doit
être valide (guillemets internes échappés ou quotes simples autour) :

```bash
claude mcp add-json --scope user optimai \
  '{"type":"stdio","command":"/opt/homebrew/bin/uv","args":["--directory","/Users/hassanafif/Developer/optimAI","run","python","-m","optimai.server"]}'
```

Alternative sans JSON manuel : `claude mcp add-from-claude-desktop --scope user`
(réutilise l'entrée Desktop validée). Ne **pas** éditer `~/.claude.json` à la
main.

## Faux positif blacklist

La blacklist (`config/blacklist.txt`) matche par `search` (regex n'importe où
dans la commande), et le `goal`/pack est scanné en pré-vol. Un faux positif
bloque l'appel avec `PatternRejected` / `blacklist_violation`. Options :
affiner le pattern fautif dans le fichier, ou — pour une tâche ponctuelle —
ajuster via `extra_blacklist` côté spec (qui *ajoute*, ne retire pas). Une regex
invalide dans le fichier échoue au **chargement** (`ShellError`), pas au
runtime : vérifier `logs/optimai.log` au démarrage.

## Reconnexion (serveur stdio)

Les serveurs **stdio ne sont pas *auto*-reconnectés** (l'auto-reconnexion avec
backoff est réservée aux serveurs HTTP/SSE). S'il tombe : `/mcp` → `Reconnect`
(reconnexion **manuelle**, sans quitter la session) ; relancer `claude`
seulement si ce Reconnect échoue.
