# DEC-019 : Cleanup Osaurus de la machine

**Date** : 2026-05-19
**Statut** : 📝 Proposed (à exécuter après validation finale de la
chaîne mlx_lm.server en CLI #3)
**Cause** : [DEC-017](DEC-017-mlx-lm-server-replaces-osaurus.md)

## Contexte

Osaurus a été installé en session CLI #2 (Hassan, opération privilégiée
DEC-009) via `brew install --cask osaurus`. Plusieurs résidus
subsistent maintenant inutilement sur la machine :

- App `/Applications/Osaurus.app` (~10 MB)
- CLI binary `/opt/homebrew/bin/osaurus` (~5 MB)
- Cask metadata Homebrew
- Dossier modèles legacy `~/MLXModels/mlx-community/Qwen2.5-Coder-32B-Instruct-4bit/`
  (~17 GB, dupliqué dans `~/.cache/huggingface/hub/` désormais)
- Dossier `~/.osaurus/` (config + modèles `osaurus pull`)
- Caches/logs divers macOS

DEC-019 trace la procédure de cleanup propre.

## Décision

**Exécuter le cleanup uniquement après validation finale de la chaîne
mlx_lm.server** (CLI session #3, PATCH #3 du brief, étapes finales
validées + commit fait).

Le but est de ne pas démolir le filet de sécurité avant d'avoir prouvé
que la nouvelle stack tient sur au moins 2-3 sessions consécutives.

## Procédure de cleanup

À exécuter **par Hassan uniquement** (opération privilégiée, DEC-009).
CLI peut **présenter** chaque commande mais ne l'exécute pas.

### Étape 1 — Vérifier que la nouvelle chaîne marche

Préconditions :
- `mlx_lm.server` lancé en local et a servi au moins 3 requêtes
  cohérentes
- `.env` du projet pointe sur `OSAURUS_URL=http://127.0.0.1:1337/v1`
  (le nom de variable reste `OSAURUS_URL` ou est renommé en
  `MLX_LM_SERVER_URL` selon la décision finale du PATCH #3 ; ce qui
  compte c'est que ça pointe sur le bon serveur)
- Aucune référence à `osaurus` dans le code Python du projet

### Étape 2 — Arrêter Osaurus définitivement

```bash
# Si l'app tourne encore : menubar → Power (⏻)
# Vérifier qu'aucun process ne reste
ps aux | grep -i osaurus | grep -v grep
lsof -i :1337   # doit montrer mlx_lm.server, pas Osaurus
```

### Étape 3 — Désinstaller l'app et le CLI

```bash
# Désinstall via Homebrew
brew uninstall --cask osaurus

# Vérifier qu'il ne reste rien
which osaurus            # doit retourner vide
ls -la /Applications/Osaurus.app 2>/dev/null   # doit retourner "No such file"
ls -la /opt/homebrew/bin/osaurus 2>/dev/null   # idem
```

### Étape 4 — Nettoyer les données utilisateur

⚠️ **Validation explicite Hassan avant chaque `rm -rf`** (irréversible).

```bash
# Dossier de config Osaurus
ls -la "$HOME/.osaurus/"
du -sh "$HOME/.osaurus/"
# Après validation :
rm -rf "$HOME/.osaurus/"

# Modèles legacy dans ~/MLXModels/
# (le modèle Qwen2.5-Coder-32B est désormais dans ~/.cache/huggingface/hub/
# servi par mlx_lm.server, plus besoin du legacy)
ls -la "$HOME/MLXModels/"
du -sh "$HOME/MLXModels/"
# Après validation :
rm -rf "$HOME/MLXModels/"
```

### Étape 5 — Caches macOS et préférences

```bash
# Caches applicatifs
rm -rf "$HOME/Library/Caches/com.dinoki.osaurus" 2>/dev/null
rm -rf "$HOME/Library/Caches/ai.osaurus.app" 2>/dev/null

# Préférences (plist)
find "$HOME/Library/Preferences" -iname "*osaurus*" -ls
# Si présents : rm -f ...

# Application Support
rm -rf "$HOME/Library/Application Support/Osaurus" 2>/dev/null

# Logs DiagnosticReports (les .diag qu'on a vus pendant le debug)
find "$HOME/Library/Logs/DiagnosticReports" -iname "*osaurus*" -ls
# Optionnel : supprimer ou archiver
```

### Étape 6 — Vérification post-cleanup

```bash
# Plus aucune trace système
find "$HOME" -iname "*osaurus*" 2>/dev/null | head -20
mdfind -name osaurus 2>/dev/null | head -20

# Espace disque libéré
df -h "$HOME"
```

### Étape 7 — Mise à jour blacklist

`config/blacklist.txt` contient encore des règles "anti-osaurus" qui
n'ont plus de raison d'être (Règles DEC-012 et DEC-014). Les laisser
ne coûte rien (pure défense en profondeur si quelqu'un retentait
d'installer Osaurus un jour) ou les retirer.

**Recommandation** : **laisser les règles** avec un commentaire
historique. Coût : 3 lignes regex jamais matchées. Bénéfice : si une
future session Claude tente d'invoquer `osaurus serve`, blacklist
bloque. Trace historique préservée.

À renforcer dans la blacklist (PATCH #3 du brief) :

```
# Forbid mlx_lm.server LAN exposure (DEC-012, DEC-017)
\bmlx_lm\.server\s+.*--host\s+(0\.0\.0\.0|::)
```

## Bénéfices attendus

- ✅ ~17 GB d'espace disque récupérés (modèle legacy `~/MLXModels/`)
- ✅ Pas de confusion future "quel serveur tourne ?" entre Osaurus et
  mlx_lm.server
- ✅ Pas de relance accidentelle d'Osaurus via menubar
- ✅ Une seule source de vérité pour les modèles MLX
  (`~/.cache/huggingface/hub/`)

## Trade-offs

- ❌ Si un jour Osaurus corrige ses bugs et qu'on voudrait re-tester,
  re-installation nécessaire — acceptable, c'est trivial via Homebrew
- ❌ Cleanup `rm -rf` est irréversible — mitigé par les validations
  explicites étape par étape

## Note méthodologique

DEC-019 est consciemment laissée 📝 Proposed (pas ✅ Accepted)
tant que la nouvelle chaîne n'a pas prouvé sa stabilité. C'est un
principe optimAI : on ne supprime pas le filet de sécurité avant
d'avoir validé le remplacement.

Quand CLI #3 PATCH #3 sera validé et committé, Desktop session #6
passera DEC-019 à ✅ Accepted et Hassan exécutera la procédure.
