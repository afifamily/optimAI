# DEC-007 : Limites worker — 10 itérations / 5 min / 10 KB output

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Le worker local peut boucler indéfiniment s'il ne converge pas. Sans
limites, un Pattern A mal formulé peut consommer toute la mémoire avec
des outputs accumulés, ou tourner pendant des heures sans rendre la main
au Cortex. Il faut des bornes strictes.

## Décision

Trois limites cumulables, configurables via `.env` :

| Limite | Valeur par défaut | Variable d'env |
|--------|-------------------|----------------|
| Itérations max par tâche | **10** | `OPTIMAI_MAX_ITERATIONS` |
| Budget temps total | **5 minutes** | `OPTIMAI_TIMEOUT_SECONDS=300` |
| Output shell tronqué | **10 KB par commande** | `OPTIMAI_MAX_OUTPUT_BYTES=10240` |

Au-delà de la limite, le worker s'arrête et renvoie un rapport partiel
au Cortex avec `status: "incomplete"` et le motif (`max_iterations`,
`timeout`, `output_truncated`).

L'output tronqué est résumé par le worker lui-même avant troncature
finale (le worker voit l'output complet, mais ce qui remonte au Cortex
est condensé).

## Rationale

- **10 itérations** couvre largement les cas typiques de Pattern A
  (3–6 itérations en pratique pour le diagnostic XCTest). Au-delà, le
  problème dépasse les capacités du worker — le Cortex doit reprendre.
- **5 minutes** est un budget raisonnable pour les boucles itératives
  locales. Au-delà, l'utilisateur attend trop longtemps une réponse
  Claude qui devrait être quasi instantanée.
- **10 KB d'output** suffit pour la plupart des sorties shell utiles.
  Les logs longs sont rares et toujours résumables par le worker.

## Implémentation

- `src/optimai/config.py` charge ces limites depuis `.env` au startup
- `src/optimai/dispatcher.py` applique les limites dans la boucle :
  - Compteur d'itérations incrémenté à chaque tour
  - `asyncio.wait_for()` sur le `dispatcher.run()` global
  - Output shell tronqué dans `shell.py` avant retour au worker
- Le rapport final indique toujours combien d'itérations ont été
  utilisées et si une limite a été atteinte (transparence pour le
  Cortex)

## Trade-offs

- ✅ Garantit que le Cortex récupère la main dans un délai borné
- ✅ Protège contre les boucles infinies du worker
- ✅ Limite la consommation mémoire / CPU
- ❌ Certaines tâches légitimes mais longues seront tronquées —
  mitigation : le rapport partiel est utile, le Cortex peut relancer
  avec une formulation plus précise
- ❌ Valeurs par défaut potentiellement à ajuster après benchmarks
  réels — facile à modifier dans `.env`
