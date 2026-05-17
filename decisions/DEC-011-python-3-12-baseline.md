# DEC-011 : Python 3.12 baseline (`.python-version` épinglée)

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Lors du bootstrap technique (CLI_PROMPT_001, session CLI #1), `uv` a
résolu la contrainte `requires-python = ">=3.12"` du `pyproject.toml`
en téléchargeant CPython **3.14.5** (la dernière version disponible).

Sans `.python-version` épinglée :
- N'importe quel `uv sync` futur (MacBook, CI, autre machine) peut
  résoudre vers une version plus récente.
- L'environnement de Hassan en mai 2026 ne sera pas reproductible en
  novembre 2026.

CLI a interrompu le bootstrap pour valider la version cible avec
Hassan via Desktop.

## Alternatives évaluées

| Option | Maturité | Risque | Reproductibilité |
|--------|----------|--------|------------------|
| **3.12** (LTS de fait, sortie oct 2023) | ~31 mois en prod | Faible | ✅ Avec `.python-version` |
| 3.13 (free-threading expérimental, JIT) | ~19 mois | Moyen (libs récentes) | ✅ |
| 3.14 (résolu par défaut) | ~7 mois | Élevé (très récent) | ❌ Si non épinglée |

## Décision

**Python 3.12** comme baseline, **épinglée via `.python-version`** à
la racine du repo, versionnée Git.

```
.python-version
─────────────────
3.12
```

`uv` détecte ce fichier automatiquement et installe la dernière 3.12.x
au premier `uv sync`. À la date du bootstrap : Python 3.12.13.

## Rationale

1. **Reproductibilité d'abord** — Sans pin, le projet diverge dans le
   temps. C'est inacceptable pour un outil qui doit tourner identique
   sur ma machine et sur n'importe quelle session future.
2. **Maturité** — 3.12 a ~31 mois en production. fastmcp, httpx,
   pydantic v2, pytest, MLX : tous le testent en priorité.
3. **Pas de besoin 3.13+ identifié** — On n'utilise ni free-threading,
   ni JIT, ni les nouvelles features typing de 3.13. Aucun bénéfice
   concret à prendre le risque.
4. **Cohérence préférences utilisateur** — "Préfère solutions testées
   plutôt que théoriques", "Préfère la simplicité à la complexité".

## Implémentation

- `.python-version` créé avec contenu `3.12` (versionné, pas dans
  `.gitignore`)
- `uv sync` purgé puis re-exécuté → installe Python 3.12.13 dans
  `~/.local/share/uv/python/cpython-3.12.13-macos-aarch64-none/`
- `pyproject.toml` conserve `requires-python = ">=3.12"` comme borne
  minimale (sans imposer un plancher trop strict pour les futures
  collaborations éventuelles)

## Procédure de bump futur

Si un bump vers 3.13/3.14 est jugé pertinent plus tard (besoin
concret identifié) :

1. Créer une nouvelle DEC (DEC-NNN) référant celle-ci en supersession (🔁)
2. Vérifier la compat des deps via `uv lock --upgrade-python 3.13`
3. Modifier `.python-version` → `3.13`
4. `rm -rf .venv && uv sync`
5. Lancer `uv run pytest` complet
6. Commit dédié `chore: bump Python 3.12 → 3.13 (DEC-NNN)`

## Trade-offs

- ✅ Reproductibilité parfaite via `.python-version` + `uv.lock`
- ✅ Maturité maximale pour l'écosystème
- ❌ Pas de bénéfice 3.13/3.14 (free-threading, JIT) — acceptable, on
  bumpera quand un besoin réel apparaîtra
