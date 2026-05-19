# DEC-014 : Osaurus — limite sur templates Jinja externes complexes (Qwen3-Coder non supporté)

**Date** : 2026-05-17
**Statut** : ✅ Accepted
**Relation** : Force l'abandon du modèle de DEC-013, supersédé par [DEC-015](DEC-015-qwen2-5-coder-32b-instruct.md)

## Contexte

Session CLI #2 (suite). Après pull du modèle
`mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit` (DEC-013) et tentative
de test via Osaurus v0.18.24, deux échecs successifs ont été observés :

1. **`/v1/chat/completions` HTTP** : réponses dégénérées du type
   "2+2+2+2+...", `prompt_tokens` bloqué à 25 (preuve que le template
   n'est pas appliqué).
2. **`osaurus run` interactif** (après reset propre de toutes les
   instances Osaurus) : sortie dégénérée identique, isolant le problème
   au **couple modèle + Osaurus**, pas au path HTTP.

Test de contrôle : le modèle Apple Foundation utilisé par Osaurus en
interne répond correctement ("Paris.") → le pipeline de chat
templating d'Osaurus fonctionne pour les templates simples.

## Diagnostic

Le fichier `chat_template.jinja` de Qwen3-Coder fait 6722 caractères
et contient des macros Jinja avancées pour le tool-calling (XML tags,
branches conditionnelles, format de fonction). Osaurus v0.18.24 :

- ✅ Sait appliquer des templates simples (Apple Foundation, modèles
  curés du catalog OsaurusAI)
- ❌ Ne lit pas `chat_template.jinja` séparé (convention transformers
  ≥ 4.43)
- ❌ Ne lit pas non plus `chat_template` ré-injecté dans
  `tokenizer_config.json` (Option 1 testée par CLI #2, sans effet
  après reset propre des instances et re-pull mental du modèle)
- ❌ Retombe silencieusement en mode "complétion brute" (concaténation
  des messages sans formatting), ce qui fait dégénérer tout modèle
  Instruct

## Décision

**Abandonner Qwen3-Coder-30B-A3B-Instruct-4bit comme modèle worker.**

Bascule documentée séparément en [DEC-015](DEC-015-qwen2-5-coder-32b-instruct.md)
vers un modèle avec template simple et embarqué dans
`tokenizer_config.json`.

### Critères de sélection d'un modèle compatible Osaurus

À partir de cet incident, optimAI ajoute un **checkpoint de
compatibilité** à valider avant tout pull d'un modèle worker :

1. Le fichier `tokenizer_config.json` du modèle contient une clé
   `chat_template` non vide
2. Le template n'utilise pas de macros Jinja avancées (au mieux : pas
   de `{% macro %}`, pas de format tool-calling complexe inline)
3. Test interactif `osaurus run <model>` produit une réponse cohérente
   à un prompt simple **avant** d'investir dans l'intégration HTTP

Si l'un de ces critères tombe → modèle écarté, on documente, on cherche
un autre candidat.

## Règles d'usage Osaurus dans optimAI

L'incident a révélé des frictions opérationnelles supplémentaires qu'il
faut codifier :

### Règle 1 — Une seule instance Osaurus à la fois

Osaurus v0.18.x est une application GUI menubar persistante. Sa CLI
`osaurus serve` ne détecte pas l'instance GUI déjà active et tente de
démarrer une nouvelle instance qui plante sur le port (1337 déjà pris).
Plusieurs instances en parallèle = pollution mémoire et confusion sur
"quelle instance reçoit mes requêtes".

**Règle** : CLI ne lance **JAMAIS** `osaurus serve`. L'instance Osaurus
est gérée exclusivement par Hassan via la menubar (Power ⏻ pour
arrêter, lancement via Applications/Spotlight pour démarrer).

### Règle 2 — Health-check via HTTP, pas CLI

Pour vérifier qu'Osaurus tourne, le seul appel autorisé depuis CLI est :

```bash
curl -s http://127.0.0.1:1337/v1/models
```

Pas de `osaurus status`, pas de `osaurus serve`, pas de `osaurus run`.

### Règle 3 — Recharger un modèle = redémarrer Osaurus

Les modèles MLX sont chargés en mémoire au démarrage. Toute modification
de fichier modèle (ex. `tokenizer_config.json`) sur disque nécessite un
**redémarrage complet** d'Osaurus (Power off via menubar, puis relance
manuelle) pour être prise en compte.

**Règle** : si une modif fichier modèle est nécessaire (cas rare en
théorie après DEC-014/DEC-015), CLI prépare la modif, **demande à
Hassan de redémarrer Osaurus**, puis seulement teste l'effet.

### Règle 4 — Cleanup des instances orphelines

Si plusieurs instances Osaurus apparaissent dans la menubar (icônes
multiples) ou via `ps aux | grep -i osaurus`, **toutes les fermer**
proprement via leur menubar (Power ⏻) ou via `kill <PID>` pour les
process orphelins, **sauf** celle qui écoute effectivement sur 1337
(`lsof -i :1337 | grep LISTEN` → PID à préserver).

## Implémentation

- `config/blacklist.txt` étendu (session CLI #3+) pour bloquer les
  commandes interdites :

  ```
  # Forbid direct osaurus serve invocation (DEC-014 Règle 1)
  \bosaurus\s+serve\b
  ```

- `CLAUDE.md` mis à jour avec une section "Règles Osaurus" qui résume
  les 4 règles ci-dessus pour les sessions Claude futures.

## À signaler upstream

Issue à ouvrir sur le repo Osaurus (https://github.com/dinoki-ai/osaurus
ou équivalent) pour signaler :

1. `chat_template.jinja` séparé non lu (convention transformers ≥ 4.43)
2. Pas de message d'erreur ni warning quand le template est absent →
   sortie dégénérée silencieuse
3. CLI `osaurus serve` ne détecte pas l'instance GUI active

Pas urgent côté optimAI (on a contourné via DEC-015). À faire quand
quelqu'un aura le temps.

## Trade-offs

- ✅ Diagnostic capturé, on ne reproduira pas l'erreur sur un autre
  modèle (checkpoint pré-pull)
- ✅ Règles opérationnelles claires pour les sessions futures
- ✅ Procédure de cleanup multi-instances documentée
- ❌ Perte du modèle "idéal" (DEC-013) sur un point d'intégration
  technique upstream — acceptable, plusieurs alternatives existent
- ❌ Dépendance maintenue à Osaurus avec ses limites — à réévaluer en
  Phase 4 si l'écosystème évolue (Osaurus v0.19+, ou alternative
  mlx-lm.server natif)
