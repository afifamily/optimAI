# DEC-008 : Garde-fous sécurité — blacklist, sandbox path, secrets isolés

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Le worker local exécute des commandes shell sur la machine de Hassan,
sur instruction d'un modèle qui peut halluciner. Sans garde-fous, une
mauvaise interprétation d'un Task Spec peut produire `rm -rf` sur le
mauvais répertoire, ou exfiltrer des secrets via une commande `curl`
malicieusement formulée.

Cohérence avec les préférences utilisateur : "Préfère échouer
explicitement plutôt que d'avoir des fallbacks risqués", "Très attentif
à la sécurité (passwords, secrets, .env)".

## Décision

Quatre niveaux de protection, **tous appliqués simultanément** :

### 1. Blacklist de commandes (Phase 1)

Commandes refusées par défaut, échec explicite si le worker tente de les
exécuter :

- `rm -rf /` et toute commande `rm -rf` sur un path commençant par `/`
  hors du `workdir`
- `sudo` (sauf whitelist explicite par Task Spec — non implémenté en
  Phase 1, toujours refusé)
- `git push`, `git push --force` (Hassan gère Git lui-même — DEC-013
  Bassmati)
- `curl ... | sh`, `wget ... | sh`, `bash <(...)`
- `chmod 777`, `chmod -R 777`
- Toute commande contenant `> /dev/sd*` ou `dd of=/dev/`
- Toute commande contenant des tokens GitHub / API keys hardcodés
  (détection par regex sur les patterns `ghp_*`, `sk-*`, `xoxb-*`, etc.)

### 2. Sandbox de chemin

Le worker ne peut écrire qu'à l'intérieur du `workdir` passé par le
Cortex dans le Task Spec. Toute écriture hors de ce chemin est refusée
(résolution `realpath` pour bloquer les symlinks malveillants).

La lecture reste autorisée plus largement (le worker peut consulter
`/etc/`, les logs système, etc.) — la limitation est sur l'écriture.

### 3. Secrets isolés du modèle

Le fichier `.env` est lu par le **Dispatcher** au startup et chargé
dans l'environnement du subprocess shell. Les valeurs **ne transitent
jamais dans les prompts envoyés au worker**.

Exemple : si une commande shell utilise `$GITHUB_TOKEN`, le shell
résout la variable au moment de l'exécution, mais le worker ne voit
que la commande littérale `curl -H "Authorization: Bearer $GITHUB_TOKEN" ...`.

### 4. Échec explicite, pas de fallback

Si une commande échoue de manière inattendue (exit non-zero non prévu
par le Task Spec, command not found, permission denied), le worker
**s'arrête immédiatement** et remonte au Cortex. Il n'improvise pas
de correctif, n'enchaîne pas avec une commande alternative non
demandée.

## Implémentation

- `src/optimai/shell.py` :
  - Fonction `is_blacklisted(cmd: str) -> tuple[bool, str]` qui
    renvoie `(True, raison)` ou `(False, "")`
  - Fonction `resolve_workdir(path, workdir) -> Path` qui valide le
    sandbox (raise `SandboxViolation` si tentative d'évasion)
  - Subprocess lancé avec `env=` explicite (pas d'héritage automatique
    de l'env Python)
- `src/optimai/worker.py` : système prompt du worker indique
  explicitement les commandes interdites pour réduire les tentatives
  inutiles
- `tests/test_shell.py` : tests unitaires exhaustifs sur la blacklist
  et le sandbox

## Évolution prévue

- **Phase 4** : durcissement optionnel via Docker container (sandbox
  filesystem complet, network isolé). Non en Phase 1 pour rester
  custom minimal (DEC-002).
- **Phase 3+** : whitelist `sudo` configurable par projet — utile pour
  certains cas (ex. `sudo xcode-select`) si Hassan le souhaite, sinon
  refus permanent.

## Trade-offs

- ✅ Défense en profondeur : 4 couches indépendantes
- ✅ Sécurité par défaut, opt-in pour les exceptions futures
- ✅ Échec explicite cohérent avec préférences Hassan
- ❌ Pas de sandboxing filesystem complet (Phase 4) — acceptable, le
  Mac Studio est une machine de confiance
- ❌ Une commande contournée par obfuscation reste un risque
  théorique — mitigation : le modèle local n'a pas d'intention
  adversariale, c'est de l'hallucination qu'on protège
