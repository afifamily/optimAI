# DEC-016 : Diagnostic Osaurus corrigé — serveur fautif, pas les modèles

**Date** : 2026-05-19
**Statut** : ✅ Accepted
**Supersède** : [DEC-014](DEC-014-osaurus-template-limitation.md)
**Conséquence** : déclenche [DEC-017](DEC-017-mlx-lm-server-replaces-osaurus.md) et [DEC-019](DEC-019-osaurus-cleanup.md)

## Contexte

DEC-014 a établi un diagnostic provisoire : "Osaurus v0.18.x ne sait
pas appliquer les chat templates Jinja complexes en fichiers séparés".
DEC-015 a fait basculer le modèle worker vers
`Qwen2.5-Coder-32B-Instruct-4bit` (template simple embarqué dans
`tokenizer_config.json`) sur cette base.

Session CLI #2 (2026-05-19) a procédé au test discriminant : **trois
modèles MLX testés**, tous échoués à l'identique sur Osaurus v0.18.28.

## Test discriminant

| Modèle | Taille | Archi | Template | `prompt_tokens` Osaurus | Résultat |
|--------|--------|-------|----------|-------------------------|----------|
| Qwen3-Coder-30B-A3B-Instruct-4bit | 30B MoE | MoE | `.jinja` séparé, 6722 chars, macros avancées | **25** | ❌ "2+2+2+..." |
| Qwen2.5-Coder-32B-Instruct-4bit | 32B | dense | embarqué, 2507 chars, simple | **25** | ❌ "2+2+2+..." |
| Qwen2.5-3B-Instruct-4bit | 3B | dense | embarqué, 2509 chars, simple | **25** | ❌ "2+2+2+..." |

**`prompt_tokens` figé à exactement 25 dans les trois cas** —
indépendamment de la taille (3B → 32B), de l'architecture (MoE/dense),
de la complexité du template, et de sa localisation (embarqué vs
fichier séparé).

Test de contrôle additionnel : `Qwen2.5-Coder-32B-Instruct-4bit` servi
par `mlx_lm.server` (Apple ML Explore officiel) renvoie immédiatement :

- `prompt_tokens: 39` (template **bien appliqué**, +14 tokens de
  ChatML system/user/assistant markers vs 25 sans template)
- `content: "2+2 equals 4, and the capital of France is Paris."`
- `finish_reason: "stop"`

Le pipeline mlx-lm sait appliquer le template du même modèle, sur le
même fichier disque. Le différentiel = serveur Osaurus.

## Diagnostic corrigé

**Osaurus v0.18.28 n'applique pas les chat templates aux modèles MLX
fournis par l'utilisateur (déposés dans `~/MLXModels/`).** Il les
liste, les charge, fait tourner l'inférence — mais envoie au modèle les
messages bruts concaténés en texte sans formatting ChatML / Qwen / etc.

Tout modèle Instruct reçoit alors un input malformé et dégénère en
complétion brute. Seul le modèle Apple Foundation intégré à Osaurus
fonctionne — probablement parce qu'Osaurus applique son propre
template hardcodé en interne pour ce modèle, sans passer par la couche
HF.

## Hypothèses des bugs Osaurus observés (pour issue upstream)

À signaler au repo Osaurus quand quelqu'un aura le temps :

1. **Templates non appliqués aux modèles `~/MLXModels/`** — sans warning,
   sans erreur dans les logs visibles. Sortie dégénérée silencieuse.
2. **Dual storage incohérent** — `osaurus pull <model>` télécharge dans
   `~/.osaurus/models/`, mais le serveur indexe `~/MLXModels/`. Les
   deux ne sont pas d'accord. Modèle pull via CLI invisible du serveur.
3. **Multi-instance non détectée** — CLI `osaurus serve` ne détecte
   pas l'instance GUI active et tente un nouveau bind sur 1337 (échoue
   silencieusement, app erreur visible mais process zombie possible).
4. **Crash SIGABRT au quit** — log conservé localement
   (`Osaurus-0-18-28-quit-unexpectedly_20260519080300.log`,
   `.drafts/reports/`).
5. **Pas d'accès facile aux logs applicatifs** — pas de "View Logs"
   dans le menu menubar, fichier diag macOS contient des warnings
   ressource mais pas de debug applicatif.

## Décisions induites

DEC-016 invalide les prémisses de DEC-014 (cause racine erronée) et
de DEC-015 (qui était basée sur DEC-014).

Conséquences immédiates :

- DEC-014 → 🔁 Superseded by DEC-016
- DEC-015 → 🔁 Superseded by [DEC-018](DEC-018-qwen2-5-coder-32b-confirmed.md)
  (mais le modèle Qwen2.5-Coder-32B reste choisi — c'était le bon
  modèle, pour les mauvaises raisons documentées)
- DEC-003 → réévaluation, voir [DEC-017](DEC-017-mlx-lm-server-replaces-osaurus.md)
- DEC-019 : procédure de cleanup Osaurus de la machine

## Trade-offs

- ✅ Cause racine identifiée et validée par test discriminant
- ✅ Solution disponible (mlx_lm.server officiel) validée en live
- ✅ Bugs Osaurus documentés pour signalement upstream
- ❌ ~24h d'effort sur Osaurus essentiellement perdues — acceptable, la
  méthodologie a tenu (escalade au bon moment, pas de patch hasardeux,
  diagnostic CLI rigoureux)

## Note méthodologique

Cette décision illustre une force de la méthodologie optimAI :
DEC-014 avait été acté en bonne foi sur les données disponibles, mais
le test discriminant suivant a permis de l'invalider proprement. Le
système `decisions/DEC-NNN` avec statut 🔁 Superseded permet de
préserver la trace de l'erreur (utile pour comprendre pourquoi telle
règle existait) tout en pointant clairement vers la décision
remplaçante.

**Sans le pattern documentaire Bassmati adopté en Desktop session #1,
ce parcours d'erreur serait probablement reconstruit ou oublié.**
