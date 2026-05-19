# DEC-013 : Plan B activé — Qwen3-Coder-30B-A3B-Instruct-4bit (worker effectif Phase 1)

**Date** : 2026-05-17
**Statut** : 🔁 Superseded by [DEC-015](DEC-015-qwen2-5-coder-32b-instruct.md) le 2026-05-17 (cause : [DEC-014](DEC-014-osaurus-template-limitation.md))
**Relation** : Active le **Plan B** de DEC-004 (sans la superseder)

## ⛔ Statut final — Superseded

> **Cette décision a été superseded le 2026-05-17** par
> [DEC-015](DEC-015-qwen2-5-coder-32b-instruct.md).
>
> Cause : la session CLI #2 a révélé qu'Osaurus v0.18.24 ne sait pas
> appliquer le chat template de Qwen3-Coder (template Jinja complexe en
> fichier séparé), cf. [DEC-014](DEC-014-osaurus-template-limitation.md).
> Le modèle produit une sortie dégénérée en `/v1/chat/completions` et
> en `osaurus run` interactif.
>
> Plan C activé : bascule vers
> `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` (DEC-015).

## Contexte

DEC-004 a sélectionné `mlx-community/Qwen3-Coder-Next-8bit` comme modèle
worker par défaut, avec un Plan B documenté :

> Si Qwen3-Coder-Next 8-bit consomme trop de mémoire ou produit un TTFT
> trop élevé en pratique : bascule sur Qwen3-Coder-Next 4-bit (~45 GB) —
> même modèle, moins précis mais plus rapide. Sinon,
> Qwen3-Coder-30B-A3B-Instruct 4-bit (~17 GB) — modèle plus léger mais
> excellent rapport qualité/vitesse pour le coding.

Lors de l'exploration live d'Osaurus (CLI #2, screenshot Model Manager
2026-05-17), trois contraintes nouvelles ont été observées :

1. **Pas de Qwen3-Coder-Next dans le catalog Osaurus** — il faudra
   passer par `huggingface-cli` quoi qu'il arrive (Scénario 2 du brief
   CLI_PROMPT_002). Pas bloquant en soi.
2. **Tous les "Recommended" Osaurus sont des VLM** (Vision Language
   Models) — overhead vision inutile pour un worker code pur.
3. **Mémoire libre observée : 48 GB sur 96 GB** au moment du screenshot.
   Le système a déjà ~48 GB occupés par d'autres applications. Charger
   85 GB est impossible, et 45 GB tiendrait à la limite extrême (zéro
   marge pour contexte 256K ou autres apps qui se lancent).

## Décision

**Activer le Plan B de DEC-004 dès la Phase 1.**

Modèle worker effectif :
**`mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit`** (17.2 GB).

Variante retenue : **standard `-4bit`** (pas DWQ ni DWQ-v2).

## Rationale

### Pourquoi ce modèle

- **Bon pour notre usage agentic coding** — qualité approchant Claude
  Sonnet sur les tâches coding agentiques selon la fiche modèle
  mlx-community.
- **MoE 30B total / 3B actifs** — même paradigme architectural que
  Qwen3-Coder-Next (rapidité d'inférence du 3B avec connaissance d'un
  30B).
- **Contexte 256K natif** — pas de pénalité contextuelle.
- **17.2 GB en RAM** — laisse ~30 GB de marge confortable sur la
  mémoire actuellement disponible, et tient même quand la machine est
  chargée d'autres workloads.
- **5158 téléchargements/mois** sur mlx-community — modèle utilisé en
  production par la communauté.

### Pourquoi la variante standard (pas DWQ/DWQ-v2)

- **Stabilité** — variante de référence, format quantization éprouvé.
- **Compatibilité maximale** — testée par le plus grand nombre
  d'utilisateurs, donc moins de bugs spécifiques à la quantization.
- **Reproductibilité** — moins de risque de drift de comportement entre
  versions de la quantization.
- DWQ et DWQ-v2 (Dynamic Weight Quantization) restent évaluables en
  Phase 4 pour un potentiel gain de qualité, sur cas concrets.

### Pourquoi pas Qwen3-Coder-Next 4-bit (~45 GB)

- Tient à la limite stricte de la mémoire disponible (48 GB free
  observés). Aucune marge pour le contexte long, les autres apps,
  ou les pics d'allocation MLX.
- Le bénéfice attendu (modèle 80B vs 30B, même quantization 4-bit) ne
  justifie pas la fragilité opérationnelle d'un système constamment
  à la limite.
- Garde-le comme option Phase 4 si l'archi prouve sa valeur et qu'un
  upgrade modèle devient pertinent.

## Mises à jour induites

| Fichier | Modification |
|---------|-------------|
| `decisions/DEC-004-qwen3-coder-next.md` | Statut reste ✅, ajout d'une note "Plan B activé par DEC-013" |
| `.drafts/claude/CLI/CLI_PROMPT_002_osaurus_setup.md` | Modèle cible mis à jour, commande `huggingface-cli` adaptée, taille et durée d'installation revisées |
| `.env.example` (modifié par CLI en session #2) | `OPTIMAI_MODEL` reflète le nom retourné par `/v1/models` pour ce modèle |
| `CLAUDE.md` (Desktop #4) | Stack mise à jour |
| `ROADMAP.md` (Desktop #4) | Note Phase 4 : benchmark Coder-Next 4-bit et DWQ variants |

## Plan Phase 4 (rappel hors-périmètre actuel)

Une fois la chaîne Cortex/Dispatcher/Hands fonctionnelle sur le modèle
standard :

1. **Benchmark qualitatif** sur 5–10 cas réels (XCTest TBS, Docker
   QNAP, etc.) :
   - Qwen3-Coder-30B-A3B-Instruct-4bit (baseline)
   - Qwen3-Coder-30B-A3B-Instruct-4bit-dwq-v2 (qualité meilleure ?)
   - Qwen3-Coder-Next 4-bit (modèle plus large)
2. **Décider** sur données réelles si un upgrade modèle est utile.
3. **Bumper** via une nouvelle DEC dédiée.

## Trade-offs

- ✅ Stabilité opérationnelle (modèle léger, marge mémoire confortable)
- ✅ Activation propre d'un Plan B déjà documenté (DEC-004)
- ✅ Qualité agentic coding réputée proche Claude Sonnet
- ✅ Démarrage rapide (17 GB vs 85 GB de download)
- ❌ Modèle "plus petit" que la cible initiale — acceptable, à
  réévaluer Phase 4 sur cas concrets
