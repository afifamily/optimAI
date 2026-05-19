# DEC-018 : Qwen2.5-Coder-32B-Instruct-4bit confirmé comme worker (Phase 1)

**Date** : 2026-05-19
**Statut** : ✅ Accepted
**Supersède** : [DEC-015](DEC-015-qwen2-5-coder-32b-instruct.md) (bonnes
conclusions, mauvaises prémisses)
**Validé par** : tests live `mlx_lm.server` session CLI #2 (2026-05-19)

## Contexte

DEC-015 avait sélectionné `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit`
en pensant que le template embarqué résoudrait le problème Osaurus.
DEC-016 a montré que le diagnostic était erroné — le problème venait
d'Osaurus, pas du template. Le choix du modèle reste-t-il bon ?

**Oui**, et cette fois validé par des preuves directes.

## Validation live (session CLI #2, 2026-05-19)

Configuration de test :
- Serveur : `mlx_lm.server` v0.31.3 (Apple ML Explore officiel)
- Modèle : `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit`
- Hardware : Mac Studio M2 Max 96 GB
- Cache HF officiel : `~/.cache/huggingface/hub/`

### Test 1 — Raisonnement simple

Prompt : "What is 2+2 and what is the capital of France?"
Réponse :
```json
{
  "content": "2+2 equals 4, and the capital of France is Paris.",
  "finish_reason": "stop",
  "prompt_tokens": 39,
  "completion_tokens": 16
}
```

`prompt_tokens=39` (vs 25 sans template) confirme l'application du
chat template Qwen2.5 (system + user + assistant markers en ChatML).

### Test 2 — Génération de code (Pattern A/D representative)

Prompt : "Write a Python function that returns the nth Fibonacci
number using memoization. Keep it under 10 lines."

Réponse : fonction Python idiomatique avec `def fibonacci(n, memo={})`,
récursion + cache, conforme à la contrainte de longueur, commentaire
explicatif. `cached_tokens: 5` → KV cache fonctionnel entre requêtes
(impact direct sur l'efficacité des boucles itératives Patterns A et D).

## Pourquoi rester sur Qwen2.5-Coder-32B (et pas revenir à Qwen3-Coder)

Question posée par Hassan : "puisque Qwen2.5 a fonctionné et le
problème n'est pas lié au modèle, pourquoi ne pas revenir à Qwen3 ?"

Réponse argumentée :

1. **Diagnostic Qwen3 pollué par Osaurus.** On n'a jamais réellement
   testé Qwen3-Coder avec un serveur fonctionnel. Toutes les
   "dégénérations" venaient d'Osaurus. Retourner à Qwen3 = retest
   from scratch + re-download (~17 GB pour 30B-A3B ou ~85 GB pour
   Coder-Next).
2. **Qwen2.5-Coder-32B vient de prouver qu'il marche.** Tests validés
   (raisonnement, code, multi-tour KV cache). Baseline stable et
   mesurée. Règle d'ingénierie : on ne change pas ce qui marche.
3. **Bénéfice Qwen3 marginal en Phase 1.** Coder-Next a un
   tool-calling natif sophistiqué, mais notre Dispatcher orchestre
   via JSON structuré dans le payload (Patterns A et D), pas via le
   format OpenAI tools strict. On n'utilise pas ce superpouvoir.
4. **Phase 4 est faite pour ça.** Benchmark contrôlé Qwen2.5 vs Qwen3
   prévu sur cas réels TBS/Bassmati/QNAP, mlx_lm.server pour les deux,
   mêmes Patterns A et D. Décision rationnelle sur données plutôt que
   sur intuition.

## Décision

**Modèle worker Phase 1 confirmé** :
`mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` (~18 GB).

Aucun changement vs DEC-015 sur le choix de modèle lui-même. Cette
DEC simplement le **valide rétrospectivement** sur des bases solides
(tests live mlx_lm.server, pas hypothèses sur le template Osaurus).

## Caractéristiques validées

| Aspect | Mesure live |
|--------|-------------|
| Quantization | 4-bit |
| Architecture | dense 32B |
| Taille fichier | ~18 GB |
| Template appliqué | ✅ (prompt_tokens=39 vs 25 sans) |
| Context window | 128K (yarn rope scaling factor 4.0) |
| KV cache | ✅ fonctionnel (cached_tokens=5 observé) |
| Vitesse inférence | Quelques secondes pour réponse courte |
| Qualité code | Idiomatique, respecte les contraintes |

## Note Phase 4 — Réévaluation Qwen3-Coder

Une fois `mlx_lm.server` stable et plusieurs sessions optimAI passées
sans incident, **réévaluer Qwen3-Coder en benchmark contrôlé** :

Protocole proposé :

1. **Cas de test** : 5-10 cas réels extraits de TBS/Bassmati/QNAP
   troubleshooting (XCTest, Docker QNAP, Caddy, etc.)
2. **Candidats** :
   - `mlx-community/Qwen2.5-Coder-32B-Instruct-4bit` (baseline DEC-018)
   - `mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit` (DEC-013
     abandonné par erreur)
   - `mlx-community/Qwen3-Coder-Next-4bit` (~45 GB, si mémoire le
     permet à ce moment)
3. **Métriques** :
   - Taux de succès Pattern A (diagnostic correct)
   - Taux de succès Pattern D (commandes exécutées sans erreur)
   - Tokens générés (efficacité)
   - Vitesse end-to-end (TTFT + génération)
4. **Décision** : si Qwen3 gagne sur ≥3 métriques sur 4, bumper le
   modèle worker via nouvelle DEC. Sinon, rester sur Qwen2.5.

## Trade-offs (rappel DEC-015, toujours valides)

- ✅ Validé en live avec mlx_lm.server
- ✅ Coding abilities ~GPT-4o sur benchmarks publics
- ✅ Quantization 4-bit éprouvée, ~68k téléchargements/mois sur
  mlx-community
- ✅ Contexte 128K suffisant pour Patterns A/D
- ❌ Dense 32B donc inférence plus lente qu'un MoE équivalent —
  acceptable pour Phase 1, à benchmarker Phase 4
- ❌ Pas de tool-calling natif "deluxe" — mitigé par le Dispatcher qui
  parse du JSON structuré
