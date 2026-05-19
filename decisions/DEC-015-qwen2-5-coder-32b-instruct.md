# DEC-015 : Qwen2.5-Coder-32B-Instruct-4bit (worker effectif — Plan C)

**Date** : 2026-05-17
**Statut** : ✅ Accepted
**Supersède** : [DEC-013](DEC-013-plan-b-qwen3-coder-30b-a3b.md) (Plan B abandonné)
**Cause** : [DEC-014](DEC-014-osaurus-template-limitation.md) (limite Osaurus)

## Contexte

DEC-013 a activé le Plan B avec
`mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit`. Session CLI #2 a
révélé qu'Osaurus v0.18.24 ne sait pas appliquer le chat template de
Qwen3-Coder (template Jinja complexe en fichier séparé), produisant
des sorties dégénérées y compris en mode interactif `osaurus run`
après reset propre des instances (cf. DEC-014).

Plan C : changer de modèle vers un candidat compatible Osaurus.

## Décision

Modèle worker effectif :
**`mlx-community/Qwen2.5-Coder-32B-Instruct-4bit`** (~18 GB).

## Pourquoi ce modèle

### Critères DEC-014 satisfaits

| Critère | Vérification |
|---------|--------------|
| `tokenizer_config.json` contient `chat_template` non vide | ✅ Convention transformers ≤ 4.42 — template embarqué directement |
| Template Jinja simple (pas de macros avancées) | ✅ Template Qwen2.5-Coder est simple, sans format tool-calling inline complexe |
| Validation `osaurus run` cohérente avant intégration HTTP | À valider en pull (étape 1 du CLI_PROMPT_002 patché) |

### Qualité

- **Coding abilities matching GPT-4o** selon la fiche modèle officielle
  Qwen — état de l'art open-source au moment de sa sortie
- **Modèle dense 32B** (pas MoE) : comportement plus prévisible que
  Coder-Next, moins de surprises de quantization
- **Long-context 128K** via yarn rope scaling factor 4.0 — largement
  suffisant pour Patterns A et D (versus 256K natif de Coder-Next que
  l'on perd, acceptable)
- **Très utilisé sur Apple Silicon en production** : benchmarks Aider
  documentent l'efficacité du couple Qwen2.5-Coder-32B + MLX, ~68k
  téléchargements/mois sur les variantes mlx-community

### Coût mémoire

- ~18 GB en 4-bit → tient confortablement dans les 61 GB libres
  observés (cf. screenshot Osaurus 2026-05-17 22:00, après cleanup)
- Marge ~43 GB pour contexte long, autres apps, MLX overhead

### Variante choisie : mlx-community standard

Trois variantes 4-bit existent :

| Variante | Note |
|----------|------|
| **`mlx-community/Qwen2.5-Coder-32B-Instruct-4bit`** | ✅ Choix retenu — convention mlx-community, référence standard |
| `lmstudio-community/Qwen2.5-Coder-32B-Instruct-MLX-4bit` | Alternative valable (yarn rope documenté explicite, mainteneur bartowski) |
| `mlx-community/Qwen2.5-Coder-32B-Instruct-8bit` | ~32 GB, qualité supérieure mais inutile pour ce modèle dense en quantization standard 4-bit déjà excellente |

Décision : **mlx-community standard 4-bit** pour cohérence avec
DEC-004/DEC-013 et nos conventions documentaires.

## Trade-offs vs Qwen3-Coder

| Aspect | Qwen3-Coder (abandonné) | **Qwen2.5-Coder-32B (retenu)** |
|--------|-------------------------|-------------------------------|
| Architecture | MoE 30B / 3B actifs | **Dense 32B** |
| Contexte | 256K natif | 128K avec yarn rope |
| Date sortie | 2026 | 2024 (novembre) |
| Spécialisation agents | Conçu pour agents/tools | Coding général + suit instructions |
| Tool-calling natif | Excellent (macros Jinja) | Simple (via instructions) |
| Vitesse inférence | Très rapide (3B actifs) | Plus lente (dense 32B) |
| **Compatible Osaurus** | ❌ DEC-014 | ✅ Template simple embarqué |
| Téléchargements/mois | ~5k | ~68k+ |

**Verdict** : on perd la rapidité d'inférence MoE et le tool-calling
"deluxe", on gagne la **fiabilité opérationnelle**. C'est le bon
arbitrage pour la Phase 1 : mieux vaut un modèle qui marche
qu'un modèle théoriquement meilleur qui plante.

### Impact sur les Patterns A et D

- **Pattern A (Diagnose)** : tool-calling pas critique, le worker peut
  proposer des commandes shell en JSON parsé par le Dispatcher. Aucun
  impact.
- **Pattern D (Execute)** : idem, le Dispatcher orchestre via JSON
  structuré. Aucun impact.

Le tool-calling natif OpenAI-style était un *plus* annoncé dans DEC-003,
pas une exigence. Le Dispatcher peut parser du JSON émis par le worker
sans nécessiter le format OpenAI tools strict.

## Plan Phase 4 (rappel hors-périmètre)

Quand l'archi sera prouvée :

1. Évaluer si Osaurus a évolué (v0.19+) et supporte maintenant
   `chat_template.jinja` séparé → re-tester Qwen3-Coder
2. Évaluer alternative à Osaurus si nécessaire (mlx-lm.server natif,
   LM Studio CLI, etc.) pour bénéficier des modèles plus récents
3. Benchmarker quantizations DWQ-v2 du Qwen2.5-Coder-32B si Phase 4
   met en évidence un besoin qualité supérieur

## Implémentation

### Mises à jour induites

| Fichier | Modification |
|---------|-------------|
| `decisions/DEC-013-plan-b-qwen3-coder-30b-a3b.md` | Statut → 🔁 Superseded by DEC-015 |
| `.drafts/claude/CLI/CLI_PROMPT_002_osaurus_setup.md` | Patch #2 : nouveau modèle, procédure cleanup ancien, commande huggingface-cli mise à jour |
| `.env.example` (CLI session #2 finalisation) | `OPTIMAI_MODEL=qwen2.5-coder-32b-instruct-4bit` |
| `CLAUDE.md` (Desktop session #5 post-CLI #2) | Stack mise à jour |
| `ROADMAP.md` (Desktop session #5) | Note Phase 4 : retester Qwen3-Coder si Osaurus évolue |

### Cleanup de l'ancien modèle

Pour libérer les ~17 GB inutilement occupés par
`mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit` :

```bash
rm -rf "$HOME/MLXModels/mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
```

À faire par CLI dans le PATCH #2 du brief, avec confirmation Hassan
avant exécution (opération irréversible).

## Trade-offs

- ✅ Modèle reconnu compatible Osaurus avec template simple embarqué
- ✅ Qualité coding ~GPT-4o, validée par benchmarks publics
- ✅ Très utilisé en production Apple Silicon
- ✅ Mémoire confortable sur la machine cible
- ✅ Plan Phase 4 documenté pour re-évaluer
- ❌ Perte de la spécialisation "agents/tool-calling natif" de
  Qwen3-Coder — acceptable, le Dispatcher orchestre quand même via
  JSON structuré
- ❌ Pas de MoE, donc inférence plus lente — acceptable, le critère
  est "ça marche" pas "c'est le plus rapide"
