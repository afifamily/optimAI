# DEC-017 : Bascule Osaurus → mlx_lm.server comme serveur d'inférence

**Date** : 2026-05-19
**Statut** : ✅ Accepted
**Supersède** : [DEC-003](DEC-003-osaurus-over-ollama.md)
**Cause** : [DEC-016](DEC-016-osaurus-diagnostic-corrected.md)

## Contexte

DEC-016 a établi qu'Osaurus v0.18.28 n'applique pas les chat templates
aux modèles MLX déposés par l'utilisateur dans `~/MLXModels/`. Aucun
modèle Instruct externe ne peut être utilisé. C'est un blocage
fondamental qui invalide DEC-003 (Osaurus comme couche d'inférence).

Test de remplacement effectué en session CLI #2 (2026-05-19) avec
`mlx_lm.server` (Apple ML Explore officiel) :

- Install via `uv tool install mlx-lm` (cohérent avec stack uv DEC-002)
- Lancement : `mlx_lm.server --model "$HOME/MLXModels/mlx-community/Qwen2.5-Coder-32B-Instruct-4bit" --host 127.0.0.1 --port 1337`
- Test 1 (simple) : `prompt_tokens=39`, réponse "2+2 equals 4, and the
  capital of France is Paris.", `finish_reason: stop`
- Test 2 (code Python) : fonction Fibonacci avec memoization, code
  idiomatique, sous 10 lignes, `cached_tokens: 5` (KV cache fonctionnel
  entre requêtes)

→ **mlx_lm.server fonctionne immédiatement**, là où Osaurus échoue
silencieusement.

## Alternatives évaluées (post-incident Osaurus)

| Critère | Osaurus (DEC-003) | **mlx_lm.server (cette DEC)** | LM Studio | Ollama |
|---------|-------------------|------------------------------|-----------|--------|
| Backend MLX | Oui | **Oui (le moteur officiel)** | Oui | Non (llama.cpp) |
| API OpenAI-compat | Oui | **Oui** | Oui | Oui |
| Chat templates HF | ❌ Cassé sur modèles user | ✅ Fonctionne | ✅ | ✅ |
| Mainteneur | Indie | **Apple ML Explore** | Propriétaire | Indie |
| Documentation | Lacunaire | **Officielle, complète** | Lacunaire (closed) | Bonne |
| Pull modèles HF | Bug (dual storage) | Auto via huggingface | GUI | `ollama pull` |
| Stabilité | 3 séries de bugs en 24h | Stable, prod-grade | Stable mais GUI lourde | Stable |
| Démarrage | App GUI persistante | Process Python scriptable | App GUI lourde | Daemon |
| Install | `brew install --cask` | **`uv tool install mlx-lm`** | DMG | `brew install` |
| Footprint | App + service | Python venv tool | GUI lourde | Daemon |
| Tool-calling | "Natif" annoncé | Via prompt JSON structuré | Oui | Partiel |
| KV cache session | `session_id` (théorique) | Cache automatique (vu : `cached_tokens=5`) | Oui | Non |
| Cohérence stack | App Swift opaque | **Stack Python, transparent** | Closed | Externe |

## Décision

**Bascule définitive vers `mlx_lm.server` comme couche d'inférence
(Hands).**

Mode opératoire :

- **Installation** : `uv tool install mlx-lm` (outil isolé, hors venv
  projet, cohérent avec `huggingface-cli` déjà installé pareil)
- **Lancement manuel** dans un terminal dédié (pas d'autostart en
  Phase 1) :

```bash
mlx_lm.server \
  --model "$HOME/MLXModels/mlx-community/Qwen2.5-Coder-32B-Instruct-4bit" \
  --host 127.0.0.1 \
  --port 1337 \
  --log-level INFO
```

- **Arrêt** : Ctrl+C dans le terminal
- **Localisation modèles** : double storage temporaire pendant la
  transition (`~/MLXModels/` legacy Osaurus + `~/.cache/huggingface/hub/`
  qui est le cache officiel mlx-lm). DEC-019 traite le cleanup une fois
  la chaîne stabilisée

## Rationale

1. **Le serveur officiel applique correctement les chat templates** —
   c'est ce qui était attendu d'Osaurus mais n'était pas le cas.
2. **Maintenu par Apple ML Explore** — l'équipe qui développe MLX
   lui-même. Pas de risque que la chaîne se casse silencieusement à
   la prochaine update OS ou MLX.
3. **Documentation complète** — issues GitHub actives, exemples publics
   nombreux, comportement prévisible.
4. **Cohérent avec la stack optimAI** — Python 3.12 (DEC-011) + uv
   (DEC-002), tool isolé via `uv tool install`. Aucune nouvelle
   technologie introduite.
5. **API OpenAI-compatible** — le Dispatcher reste portable. Le code
   Python ne fait que changer d'URL si on bascule un jour vers un
   autre backend.
6. **Observabilité supérieure** — logs structurés en console (HTTP
   requests, prompt processing progress, cache state, fingerprint
   complet hardware/OS/MLX). Pas de Console.app, pas de fichier diag
   macOS opaque.
7. **Pas d'autostart en Phase 1** — lancement manuel par Hassan dans
   un terminal dédié quand il veut utiliser optimAI. Évite l'overhead
   RAM permanent (~17 GB occupés en continu). À ré-évaluer en Phase 4
   si l'usage devient quotidien (`launchd` agent envisageable).

## Trade-offs

- ✅ Solution officielle, stable, documentée
- ✅ Templates fonctionnels = modèles Instruct utilisables
- ✅ KV cache fonctionne entre requêtes (cf. `cached_tokens` observé)
- ✅ Observabilité console excellente
- ✅ Pas de dépendance à une app GUI tierce
- ❌ Lancement manuel à chaque session (pas un blocage Phase 1, sera
  ré-évalué Phase 4)
- ❌ Pas de menubar / quick status — mitigé par les logs console
- ❌ Modèles vivent dans `~/.cache/huggingface/hub/` (cache officiel
  HF), structure de dossiers moins lisible que `~/MLXModels/`. C'est
  la convention transformers/huggingface, on s'y aligne.

## Considérations sécurité

`mlx_lm.server` affiche au démarrage :
> `UserWarning: mlx_lm.server is not recommended for production as it
> only implements basic security checks.`

**C'est OK pour notre usage.** Le serveur écoute uniquement sur
`127.0.0.1` (loopback, DEC-012 préservée). Aucune authentification
HTTP, mais aucune exposition réseau. Pour Phase 1 mono-machine c'est
suffisant. DEC-008 (garde-fous Dispatcher) reste la couche de défense
côté optimAI.

DEC-012 reste valide intégralement : port 1337, loopback only,
**JAMAIS** `--host 0.0.0.0`. La blacklist `config/blacklist.txt` sera
patchée pour interdire `mlx_lm.server --host 0.0.0.0` en plus de la
règle Osaurus existante.

## Implémentation

| Fichier | Modification |
|---------|-------------|
| `decisions/DEC-003-osaurus-over-ollama.md` | Statut 🔁 Superseded by DEC-017, encadré en haut |
| `.env.example` | Section "Osaurus" → "MLX inference server", URL et port confirmés |
| `config/blacklist.txt` | Ajout règle anti-expose mlx_lm.server (CLI #3 PATCH #3) |
| `CLAUDE.md` (Desktop session #5) | Stack mise à jour, mode opératoire mlx_lm.server documenté |
| `ROADMAP.md` (Desktop session #5) | Phase 1 étape 3 reformulée, Phase 4 note autostart launchd |
| `.drafts/claude/CLI/CLI_PROMPT_002_osaurus_setup.md` | PATCH #3 : procédure mlx_lm.server |
| `.drafts/claude/CLI/HANDOVER_session_2026-05-19.md` | Handover complet pour reprise nouvelle session |

## Note pour Phase 4

Une fois la chaîne stabilisée et plusieurs sessions optimAI passées
sans incident :

1. Évaluer si un `launchd` LaunchAgent serait utile (lance
   `mlx_lm.server` au login, restart auto, logs centralisés)
2. Ré-tester Qwen3-Coder (DEC-013, abandonné par confusion Osaurus —
   c'était peut-être un bon modèle, on n'a jamais pu le savoir)
3. Benchmarker quantizations alternatives (DWQ-v2, 6bit, 8bit) avec
   `mlx_lm` qui les supporte tous
4. Évaluer le tool-calling natif OpenAI-style de `mlx_lm.server`
   (annoncé mais non testé en session CLI #2)
