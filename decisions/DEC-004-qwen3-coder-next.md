# DEC-004 : Qwen3-Coder-Next 8-bit MLX (worker)

**Date** : 2026-05-17
**Statut** : ✅ Accepted (Plan B activé par [DEC-013](DEC-013-plan-b-qwen3-coder-30b-a3b.md) le 2026-05-17 — voir section "Plan B" en bas)

## Contexte

Choix du modèle qui jouera le rôle de "Hands". Le hardware cible est un
Mac Studio M2 Max 96 GB unified memory. Le modèle doit être bon pour le
tool-calling (Pattern D) et le diagnostic itératif (Pattern A), pas pour
de la génération créative ou du raisonnement abstrait.

## Alternatives évaluées

| Modèle | Architecture | Taille MLX | SWE-bench | Tool-calling | Vitesse |
|--------|-------------|------------|-----------|--------------|---------|
| Gemma 4 27B Q8 | Dense | ~28 GB | Moyen | OK | Moyenne |
| Qwen3.6 27B dense | Dense | ~28 GB | 77.2% | OK | Moyenne |
| **Qwen3-Coder-Next 8-bit** | **MoE 80B / 3B actifs** | **~85 GB** | ~Claude Sonnet | **Excellent** | **Rapide (3B actifs)** |
| Qwen3-Coder-Next 4-bit | MoE 80B / 3B actifs | ~45 GB | ~Claude Sonnet | Excellent | Très rapide |
| Qwen3-Coder-30B-A3B 4-bit | MoE 30B / 3B actifs | ~17 GB | ~Claude Sonnet sur coding | Excellent | Très rapide |

## Décision

**Qwen3-Coder-Next en 8-bit MLX** comme défaut, avec **Qwen3-Coder-Next 4-bit**
comme fallback si le 8-bit s'avère trop juste en mémoire ou trop lent en
pratique.

Modèle Hugging Face : `mlx-community/Qwen3-Coder-Next-8bit`.

## Rationale

1. **Conçu pour les agents coding** — Qwen3-Coder-Next est entraîné
   spécifiquement pour l'exécution d'outils, l'interaction avec
   l'environnement et le tool-calling, ce qui matche exactement nos
   Patterns A et D.
2. **MoE 80B / 3B actifs** — Punch d'un modèle 80B avec la vitesse d'un
   3B au moment de l'inférence. Sur 96 GB unified memory en 8-bit, on
   tient confortablement (modèle ~85 GB + contexte + OS).
3. **Performance ~Claude Sonnet sur les benchmarks agentic** d'après
   la documentation MLX community.
4. **Disponible en MLX** — `mlx-community/Qwen3-Coder-Next-8bit` et
   variantes 4-bit, bf16 sont publiées et maintenues.

## Implémentation

- Téléchargement via Osaurus Model Manager (in-app) ou `mlx_lm` CLI
- `OPTIMAI_MODEL=qwen3-coder-next-8bit` dans `.env`
- Benchmark à faire en Phase 1 sur 3–5 cas réels (XCTest, commandes
  Docker QNAP, etc.) pour valider le choix 8-bit vs 4-bit

## Plan B

> **⚠️ Activé le 2026-05-17 par [DEC-013](DEC-013-plan-b-qwen3-coder-30b-a3b.md)**
>
> Lors de l'install en session CLI #2 (Osaurus Model Manager + observation
> mémoire dispo 48/96 GB), il a été décidé de partir directement sur
> `mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit` (17.2 GB, variante
> standard) plutôt que Coder-Next 8-bit ou 4-bit. Le retour vers
> Coder-Next reste possible en Phase 4 sur cas concrets.

Si Qwen3-Coder-Next 8-bit consomme trop de mémoire ou produit un TTFT
trop élevé en pratique :
- Bascule sur **Qwen3-Coder-Next 4-bit** (~45 GB) — même modèle, moins
  précis mais plus rapide.
- Sinon, **Qwen3-Coder-30B-A3B-Instruct 4-bit** (~17 GB) — modèle plus
  léger mais excellent rapport qualité/vitesse pour le coding.

## Trade-offs

- ✅ Excellence en tool-calling et tâches agentic
- ✅ Architecture MoE = rapidité d'inférence malgré la taille totale
- ❌ ~85 GB en 8-bit laisse peu de marge pour contexte long
- ❌ Modèle MoE plus complexe à fine-tuner si besoin futur (pas dans
  le périmètre Phase 1)
