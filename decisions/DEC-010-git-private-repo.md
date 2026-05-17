# DEC-010 : Git activé, repo privé GitHub

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Le projet optimAI n'est pas encore versionné. Toutes les conventions
transverses (TBS, Bassmati, QNAP) utilisent Git avec un repo privé
GitHub, et Hassan préfère systématiquement le versioning Git propre
(préférences utilisateur).

## Décision

- **Git** initialisé dès le bootstrap technique (CLI_PROMPT_001).
- **Repo privé** sur GitHub, sous le compte `afifamily` (cohérent
  avec TBS et Bassmati).
- **Branche principale** : `main`.
- **Convention commits** alignée avec Bassmati :

```
feat: Add new feature
fix: Bug fix
docs: Documentation
refactor: Code refactoring
test: Tests
security: Security improvement
chore: Maintenance, bootstrap, deps
```

## Implémentation

- `git init` exécuté par CLI lors du bootstrap
- `.gitignore` adapté (Python + macOS + iCloud + secrets) — voir
  brief CLI_PROMPT_001
- Création du repo GitHub privé `afifamily/optimAI` par Hassan (action
  privilégiée — DEC-009)
- Premier commit : `chore: v0.1.0 bootstrap — architecture, decisions, docs`
- Repo URL ajouté dans `README.md` une fois créé

## Fichiers et dossiers gitignorés

- `.env` (secrets)
- `.drafts/` (drafts personnels, briefs CLI)
- `.DS_Store`
- `__pycache__/`, `*.pyc`, `.pytest_cache/`
- `.venv/`, `venv/`
- `*.egg-info/`, `build/`, `dist/`
- `.mypy_cache/`, `.ruff_cache/`
- Logs locaux, output benchmarks

## Trade-offs

- ✅ Versioning propre, conformité avec les autres projets
- ✅ Repo privé = pas de fuite accidentelle de logique métier
- ❌ Aucun
