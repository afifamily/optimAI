# DEC-012 : Port Osaurus 1337 par défaut, écoute sur 127.0.0.1 uniquement

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

Lors de la planification initiale (Desktop session #1), `.env.example` a été
écrit avec `OSAURUS_URL=http://127.0.0.1:8080/v1` — une convention historique
qui circulait au lancement d'Osaurus en 2025.

La documentation Osaurus 2026 (docs.osaurus.ai) confirme désormais que le
**port par défaut est 1337**, surchargeable via la variable d'environnement
`OSU_PORT`. L'endpoint OpenAI-compatible canonique est donc
`http://127.0.0.1:1337/v1`.

Cohérence avec préférences Hassan : « Ne jamais deviner les commandes,
chemins ou configurations » — il faut s'aligner sur la doc officielle.

## Décision

**Port 1337 par défaut**, **écoute sur la loopback `127.0.0.1` uniquement**.

`.env.example` mis à jour en conséquence :
```ini
OSAURUS_URL=http://127.0.0.1:1337/v1
OSAURUS_PORT=1337
```

## Rationale

1. **Aligné sur le défaut Osaurus** — pas de port custom à mémoriser ou
   documenter spécialement.
2. **Pas de conflit connu** — 1337 n'est pas un port standard, peu de
   collision avec d'autres services locaux.
3. **127.0.0.1 uniquement** — Osaurus écoute par défaut sur la loopback,
   inaccessible depuis le LAN ou Internet. C'est le comportement attendu
   pour notre usage (Cortex ↔ Dispatcher ↔ Hands en local sur la même
   machine).

## Sécurité — Règle absolue : pas de `--expose`

Osaurus propose un mode `osaurus serve --expose` qui binde sur `0.0.0.0`
(LAN accessible). **Cette option est INTERDITE pour optimAI.** Raisons :

- Le worker Osaurus exécute des outils (tool-calling) avec des
  conséquences réelles (commandes shell via le Dispatcher). Exposer
  l'API au LAN = exposer la machine au LAN.
- Aucune authentification par défaut sur l'API loopback. `--expose`
  active la possibilité d'access keys (`osk-v1`) mais ce n'est pas
  obligatoire ni vérifié automatiquement.
- Le scope de Phase 1 est mono-machine. Aucun cas d'usage ne justifie
  l'exposition réseau.

Cette règle sera enforced dans la doc du projet (CLAUDE.md, README).

## Quand changer le port (cas légitimes)

Le port ne doit être modifié dans `.env` que dans ces cas :

| Cas | Action |
|-----|--------|
| Conflit local avec un autre service écoutant sur 1337 | `OSAURUS_PORT=<autre>` + mettre à jour `OSAURUS_URL` |
| Test multi-instance (deux Osaurus simultanés, ex. dev + bench) | Une instance reste sur 1337, l'autre prend un port libre |
| Décision sécurité organisationnelle externe | Documenter dans une nouvelle DEC dédiée |

**Pas de changement « par confort » ou « par habitude »**. Le défaut tient.

## Si exposition LAN devient un jour nécessaire (Phase 4+)

Hors périmètre actuel. Si un cas d'usage futur l'exige (ex. accéder à
Osaurus depuis le MacBook pendant que le Mac Studio sert) :

1. Créer une DEC dédiée
2. Activer l'authentification par access keys `osk-v1`
3. Restreindre à l'interface LAN locale (pas Wi-Fi public)
4. Documenter la configuration tailored dans `TROUBLESHOOTING.md`

## Implémentation

- `.env.example` mis à jour par CLI dans la session CLI #2 (CLI_PROMPT_002)
- `CLAUDE.md` mis à jour pour refléter le port effectif
- `config/blacklist.txt` étendu pour bloquer toute commande shell
  contenant `--expose` ou `osaurus serve --expose` (sécurité défense en
  profondeur)

## Trade-offs

- ✅ Aligné sur le défaut officiel Osaurus, zéro config exotique
- ✅ Sécurité par construction (loopback only)
- ✅ Règle `--expose` interdite explicitée et enforced via blacklist
- ❌ 1337 peut surprendre (port non standard pour HTTP) — acceptable,
  documenté dans CLAUDE.md
