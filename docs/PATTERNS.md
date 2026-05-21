# Patterns — optimAI (Phase 1)

> Spécification des deux patterns prioritaires (DEC-006) : **A — Diagnose** et
> **D — Execute**. Schémas d'entrée/sortie tirés de `src/optimai/schemas/`,
> descriptions d'outil tirées des classes de pattern. Patterns B et C reportés
> en Phase 2 (DEC-006).

## Le contrat commun (DEC-021)

Un pattern est une *stratégie* fine qui possède : un `system_prompt`, le message
utilisateur initial, le parseur de sortie worker, le constructeur de report, et
sa politique de timeout par-commande. La boucle du Dispatcher est commune et
agnostique (voir [`ARCHITECTURE.md`](ARCHITECTURE.md) §3).

Chaque pattern est exposé comme un outil MCP `optimai_<name>`, dont le serveur
**aplatit** les champs du spec en arguments nommés (le Cortex passe `goal`,
`context`, `workdir`… directement, pas un objet `spec` imbriqué).

Champs communs aux deux specs :

| Champ | Type | Requis | Rôle |
|-------|------|--------|------|
| `goal` | `str` (≥ 5 car.) | ✅ | Objectif formulé par le Cortex |
| `context` | `str` | — (défaut `""`) | Savoir métier : causes typiques, commandes à tenter, ce qu'un échec signifie. **Non scanné** par la blacklist (peut citer des tokens) |
| `workdir` | `Path` | ✅ | Racine sandbox / cible d'investigation. **Doit exister** (validé à la construction) |
| `allowed_read_paths` | `list[Path]` | — (défaut `[]`) | Chemins lecture seule supplémentaires (le `workdir` est inclus d'office) |
| `extra_blacklist` | `list[str]` | — (défaut `[]`) | Patterns regex blacklist propres à la tâche, ajoutés à la base |

---

## Pattern A — Diagnose

`tool_description` (ce que le Cortex lit pour choisir l'outil) :

> Read-only environment investigation. Given a `goal` and domain `context`, the
> worker inspects toolchain state with informational shell commands (no sudo, no
> mutations) and returns a verdict: root cause, evidence, temporary fix,
> permanent fix.

**Quand l'utiliser** : diagnostiquer *pourquoi* un outil de build/test échoue
sur le poste. Read-only par conception — le prompt système interdit sudo,
modifications, installs, et le scan de gros arbres de fichiers (le diagnostic
porte sur l'**état de la toolchain**, pas sur un checkout projet).

**Entrée** : `DiagnoseSpec` = champs communs ci-dessus (pas de champ propre).

**Sortie** : `DiagnoseReport`

| Champ | Type | Rempli quand |
|-------|------|--------------|
| `status` | `complete` \| `incomplete` \| `error` | toujours |
| `root_cause` | `str \| null` | `null` si non `complete` |
| `evidence` | `list[str]` | observations (commande + extrait de sortie) |
| `temporary_fix` | `str \| null` | si le worker en propose un |
| `permanent_fix` | `str \| null` | si le worker en propose un |
| `iterations_used` | `int` | toujours |
| `stop_reason` | `StopReason` (voir plus bas) | toujours |
| `commands_executed` | `list[{cmd, exit, stdout_truncated}]` | trace de chaque commande |
| `notes` | `str` (≤ 1 KB) | notes worker |

**Politique timeout par-commande : `recover` (DEC-022).** Les commandes sont
informationnelles → une commande lente isolée tuée puis remplacée par une plus
ciblée ne laisse aucun effet de bord. La boucle réinjecte « TIMED OUT » et
continue.

### Exemple réel (trace CLI, étape 10 — projet TBS)

Appel émis par le Cortex (Claude CLI), `workdir` pointé sur le repo **cible** :

```text
optimai_diagnose(
  goal:    "vérifier quelle version de Python est disponible dans ce dossier",
  workdir: "/Users/hassanafif/.../production/TelegramBotsServer"
)
```

Report renvoyé :

```json
{
  "status": "complete",
  "root_cause": "Python 3.12.13 is the version available in the PATH.",
  "evidence": ["Python 3.12.13"],
  "temporary_fix": null,
  "permanent_fix": null,
  "iterations_used": 2,
  "stop_reason": "converged",
  "commands_executed": [
    { "cmd": "python --version || python3 --version", "exit": 0, "stdout_truncated": false }
  ],
  "notes": "..."
}
```

Convergence en 2 itérations, une seule commande read-only. Le même appel a
renvoyé un report identique depuis bassmati et QNAP (étape 10), avec trois
Cortex différents (Opus 4.7, Sonnet 4.6, Haiku 4.5) — l'outil ne dépend pas du
modèle Cortex.

---

## Pattern D — Execute

`tool_description` :

> Run an ordered, pre-validated pack of shell commands (mutating). The worker
> proceeds through `commands` one at a time, may interleave short read-only
> diagnostics, and reports a compact verdict (summary + which command failed if
> any). Aborts on per-command timeout — partial mutations are surfaced, never
> improvised around.

**Quand l'utiliser** : exécuter un **pack ordonné et pré-validé** de commandes
mutantes (build, install, déplacement de fichiers…). Le pack vient du Cortex et
est la **seule** mutation autorisée : le worker l'exécute une commande à la
fois, peut intercaler **une** commande read-only de diagnostic pour interpréter
un résultat, mais ne propose jamais de commande mutante hors pack (sémantique
option 1, DEC-006 / brief CLI #5).

**Entrée** : `ExecuteSpec` = champs communs **+** :

| Champ | Type | Requis | Rôle |
|-------|------|--------|------|
| `commands` | `list[str]` (≥ 1, non vides) | ✅ | Pack ordonné de commandes shell à exécuter une à une |

Note sécurité : pour Execute, l'`operator_text` scanné par la blacklist est le
`goal` **concaténé au pack** — les commandes du pack sont elles aussi un vecteur
opérateur à vérifier.

**Sortie** : `ExecuteReport` (intentionnellement compact — le stdout/stderr
complet ne remonte jamais)

| Champ | Type | Rempli quand |
|-------|------|--------------|
| `status` | `complete` \| `incomplete` \| `error` | toujours |
| `summary` | `str \| null` (≤ 1 KB) | verdict une ligne si `complete` |
| `failed_command` | `str \| null` | commande du pack en échec/abort, sinon `null` |
| `iterations_used` | `int` | toujours |
| `stop_reason` | `StopReason` | toujours |
| `commands_executed` | `list[{cmd, exit, stdout_truncated}]` | trace de chaque commande |
| `notes` | `str` (≤ 1 KB) | notes worker |

Sur `error`, `build_report` remonte la dernière commande tentée comme
`failed_command` : le Cortex voit où la chaîne s'est arrêtée sans dérouler la
trace.

**Politique timeout par-commande : `abort` (DEC-022).** Les commandes mutent
l'état. Une commande tuée en cours peut avoir laissé un effet de bord partiel
(fichier à moitié écrit, build intermédiaire, package partiellement installé).
La boucle s'arrête avec `stop_reason="command_timeout"` / `status="error"` et
signale l'incohérence — le Cortex décide d'avancer ou de revenir en arrière en
connaissance de cause, plutôt que d'improviser sur un état inconnu.

### Exemple réel (trace CLI, étape 11 — dossier de test jetable)

Appel émis par le Cortex (Claude CLI, Sonnet 4.6), pack mutant de deux commandes
ordonnées dans un dossier jetable :

```text
optimai_execute(
  goal:     "créer un fichier marqueur et y inscrire une ligne, puis vérifier",
  context:  "dossier de test jetable. succès = le fichier marker.txt contient 'optimai-ok'",
  workdir:  "/tmp/optimai-exec-test",
  commands: ["echo 'optimai-ok' > marker.txt", "test -f marker.txt && cat marker.txt"]
)
```

Report renvoyé :

```json
{
  "status": "complete",
  "summary": "Le fichier marker.txt a été créé et contient 'optimai-ok'",
  "failed_command": null,
  "iterations_used": 3,
  "stop_reason": "converged",
  "commands_executed": [
    { "cmd": "echo 'optimai-ok' > marker.txt", "exit": 0, "stdout_truncated": false },
    { "cmd": "test -f marker.txt && cat marker.txt", "exit": 0, "stdout_truncated": false }
  ],
  "notes": "La vérification a réussi, le fichier marker.txt contient 'optimai-ok'"
}
```

Le pack est exécuté **dans l'ordre** : la 1ʳᵉ commande mute l'état (création de
`marker.txt`), la 2ᵉ — dépendante — la confirme. C'est la sémantique propre à
Execute, distincte de Diagnose (read-only) : `summary` rempli, `failed_command`
à `null`, les deux commandes du pack à `exit: 0`.

---

## Vocabulaire `stop_reason` (partagé, `report.py`)

| Valeur | Sens | `status` typique |
|--------|------|------------------|
| `converged` | le worker a livré un verdict final | `complete` |
| `max_iterations` | 10 itérations atteintes sans report (DEC-007) | `incomplete` |
| `timeout` | budget global 300 s dépassé (DEC-007) | `incomplete` |
| `command_timeout` | timeout par-commande sous politique `abort` (DEC-022) | `error` |
| `blacklist_violation` | une commande a matché la blacklist (DEC-008 §1) | `error` |
| `sandbox_violation` | chemin hors sandbox (DEC-008 §2) | `error` |
| `worker_error` | échec d'appel worker, ou sortie invalide 2× | `error` |
| `shell_error` | échec d'exécution shell | `error` |

Le `Literal` est commun aux deux reports : `DiagnoseReport` accepte donc
techniquement `command_timeout` bien qu'il ne le produise jamais en pratique
(sa politique est `recover`). Choix assumé CLI #5 : un vocabulaire complet
partagé plutôt qu'un `Literal` par report.

---

## `workdir` : pourquoi il n'y a pas de fallback

Question légitime : quand le Cortex est Claude CLI, pourquoi ne pas utiliser la
variable `CLAUDE_PROJECT_DIR` (injectée par le CLI dans l'env du serveur) comme
valeur de repli quand `workdir` est absent ? Réponse : **on ne le fait pas, par
conception**, pour trois raisons cumulatives.

1. **Frontière Cortex/serveur (DEC-001).** Décider *où* investiguer appartient
   au Cortex ; `workdir` est l'expression de cette décision. Un serveur qui
   devine le `workdir` prendrait une décision qui n'est pas la sienne. Le
   serveur doit rester bête et déterministe.
2. **Ce ne serait pas un fallback général.** `CLAUDE_PROJECT_DIR` n'existe que
   pour le Cortex *CLI* — pas Desktop, pas l'API. Un repli qui ne couvre qu'un
   transport sur trois rendrait le serveur *CLI-aware*, alors qu'il ignore
   aujourd'hui totalement qui l'appelle (force de DEC-005).
3. **Ce serait un piège silencieux (DEC-008 §4).** `workdir` est `required` :
   un appel sans `workdir` échoue immédiatement et explicitement → le Cortex se
   corrige. Avec fallback, l'appel *réussirait silencieusement* mais
   investiguerait le dossier de lancement de `claude`, pas la cible voulue —
   et pour **Execute**, des commandes mutantes pourraient s'exécuter dans le
   mauvais dossier. C'est exactement le « fallback risqué » que DEC-022 a refusé
   pour le timeout Execute.

Où `CLAUDE_PROJECT_DIR` a sa place : **côté Cortex**, qui peut choisir de la
lire pour *remplir lui-même* `workdir` s'il juge que le dossier courant est la
bonne cible. La décision reste au Cortex ; le serveur, lui, ne s'en sert pas et
fixe toujours son `cwd` de lancement sur le repo optimAI via `--directory` (ne
pas confondre les deux — voir [`../TROUBLESHOOTING.md`](../TROUBLESHOOTING.md)).
