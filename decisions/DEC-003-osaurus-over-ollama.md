# DEC-003 : Osaurus + MLX comme couche d'inférence

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Le Dispatcher doit parler à un modèle local pour exécuter les tâches
mécaniques. Deux serveurs dominent l'écosystème Apple Silicon en 2026 :
Ollama (Go + llama.cpp) et Osaurus (Swift + MLX). LM Studio existe aussi
mais cible plutôt l'usage interactif GUI.

Le hardware cible est un Mac Studio M2 Max 96 GB unified memory — Apple
Silicon natif.

## Alternatives évaluées

| Critère | Ollama | **Osaurus** | LM Studio |
|---------|--------|-------------|-----------|
| Backend | llama.cpp + Metal | **MLX natif** | MLX + llama.cpp |
| Throughput (M-series) | Bon | **~20% supérieur** | Bon |
| TTFT | Très bon | Légèrement plus lent | Bon |
| API OpenAI-compat | Oui | **Oui** | Oui |
| Tool-calling natif | Partiel | **Complet (OpenAI-style)** | Oui |
| KV cache session reuse | Non | **Oui (session_id)** | Partiel |
| Footprint | ~100 MB | **~10 MB** | Lourd (GUI) |
| Plateforme | Multi-OS | **Apple Silicon only** | Multi-OS |
| Licence | MIT | **MIT** | Propriétaire |

## Décision

**Osaurus** comme couche d'inférence pour la Hands.

## Rationale

1. **Performance native sur le M2 Max** — MLX bat llama.cpp+Metal sur
   Apple Silicon, le throughput compte plus que le TTFT pour nos boucles
   itératives.
2. **KV cache session reuse** — Patterns A et D sont multi-tours par
   nature. Avec `session_id`, le KV cache reste chaud entre les itérations,
   accélérant significativement la boucle.
3. **Tool-calling natif** — Le worker émet des appels d'outils
   structurés (style OpenAI), pas du texte libre à parser. Beaucoup plus
   fiable pour le Pattern D (packs de commandes shell).
4. **API OpenAI-compatible** — Le code Dispatcher reste portable.
   Migration ou fallback vers Ollama ou un endpoint cloud reste trivial
   (changement de `base_url`).
5. **Cohérence stack** — Osaurus est en Swift, ce que Hassan préfère,
   et reste léger (~10 MB).

## Implémentation

- Osaurus installé localement sur le Mac Studio
- `OSAURUS_URL=http://127.0.0.1:8080/v1` dans `.env`
- Client `httpx.AsyncClient` côté Dispatcher
- `session_id` ré-utilisé à travers les itérations d'un même Task

## Trade-offs

- ✅ Performance optimale sur le hardware cible
- ✅ KV cache speedup mesurable sur les boucles
- ✅ Tool-calling fiable
- ❌ Apple Silicon only (pas un problème ici, mais ferme la porte à
  déployer le Dispatcher sur le QNAP par exemple)
- ❌ Projet plus jeune qu'Ollama, écosystème en construction
- ❌ Modèles uniquement en MLX (limite le catalogue vs llama.cpp GGUF) —
  mitigation : mlx-community Hugging Face couvre les modèles majeurs
