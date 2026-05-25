# DEC-025 : Méthodologie de collecte de patterns (Phase 3)

**Date** : 2026-05-25
**Statut** : ✅ Accepted

## Contexte

La Phase 3 (ROADMAP) enrichit le Dispatcher en faisant émerger de nouveaux
patterns à partir des usages réels des autres projets (TBS, Bassmati, QNAP).
Il faut un **instrument de collecte** reproductible plutôt qu'une exploration
ad hoc, sinon le résultat dépend de l'humeur de chaque session.

Deux contraintes structurantes :

1. **Scope `conversation_search` par espace-projet.** Une instance Claude ne
   voit que l'historique de *son* espace-projet. Une seule instance ne peut
   donc pas collecter cross-projet. → **une instance de collecte par projet**,
   pilotée par un prompt générique paramétré par `<PROJET>`.
2. **Risque de sur-génération.** Une instance lâchée sur « trouve des
   patterns » sur-produit (tout ressemble à un pattern). Même piège que le
   worker sur-investiguant en CLI #3 tant que le périmètre n'était pas cadré.
   → l'instrument doit être *serré* (critères stricts, format imposé, exemples
   réels exigés, anti-critères explicites).

## Décision

Méthodologie en cinq points, matérialisée par l'instrument
`.drafts/claude/phase3/COLLECT_PROMPT.md` :

1. **Instrument générique paramétré** par `<PROJET>`, lu directement par
   l'instance de collecte via Filesystem MCP (pas de copier-coller fragile).
2. **Banc d'essai sur un seul projet d'abord — TBS** (le fondateur, le plus
   de matériel). On rode l'instrument et on valide que le format de sortie est
   exploitable avant de le lancer sur Bassmati puis QNAP.
3. **Accès au référentiel optimAI.** L'instance de collecte lit le repo
   optimAI (`docs/PATTERNS.md`, `docs/ARCHITECTURE.md`, DEC-006/021/024/008)
   avant de chercher, pour **comparer** chaque candidat à l'existant (A/D/B/C)
   au lieu de deviner. C'est le principal réducteur de faux positifs.
4. **Critères / anti-critères / `security_prereqs`** stricts (voir
   l'instrument). Point de conception clé : `sudo`, secrets et exécution
   distante ne sont **pas** des motifs de rejet mais des **prérequis à
   signaler** (champ `security_prereqs`, en anglais).
5. **Schéma de sortie imposé** (un bloc par candidat) + un rapport par projet
   `.drafts/claude/phase3/CANDIDATES_<projet>.md`, puis agrégation/dédoublonnage
   Desktop dans `docs/PATTERN_CANDIDATES.md`. Un candidat qui ressort sur
   plusieurs projets est prioritaire (généralité prouvée).

### Corollaire sécurité (raffinement de DEC-008)

Établi cette session sur lecture de DEC-008 + `config/blacklist.txt` :

- **Le réseau sortant bénin n'est pas bloqué** (gestion de deps, `git
  fetch/pull/clone`, builds). Ce que la blacklist filtre est précis :
  télécharge-puis-exécute (`curl|sh`), `git push`/écriture remote, exposition
  LAN d'un serveur (`--host 0.0.0.0`). L'isolation réseau complète est
  Phase 4 / Docker / optionnelle — inexistante en Phase 1-3.
- **`sudo`** est refusé en Phase 1, mais DEC-008 prévoit une *whitelist `sudo`
  configurable par projet en Phase 3+* (ex. `sudo xcode-select`). Un candidat
  réclamant `sudo` est donc **le signal recherché**, pas un déchet → consigné
  `sudo:<cmd>`.
- **Secrets** : une tâche utilisant `$TOKEN` est faisable tant que le worker
  manipule la *référence* d'env, jamais la valeur (invariant DEC-008 §3) →
  consigné `secret:<ref>`.

### Limite connue — exécution distante `ssh-remote` (QNAP)

La sécurité DEC-008 suppose une exécution **locale** : sandbox = `workdir`
local (§2), secrets résolus dans l'env du subprocess local (§3). Or QNAP
s'opère via `ssh qnap '...'` — exécution sur un hôte **distant**, hors de cette
sandbox. L'accès QNAP est configuré **passwordless** : ce n'est donc **pas** un
cas « secret » et il ne faut pas le mis-classer ainsi. La mécanique réelle
(extension de la sandbox au remote) est **reportée au moment où on abordera
QNAP** ; en attendant, l'instrument se contente de marquer `ssh-remote` sans
chercher à le résoudre (et seul QNAP est concerné — le pilote TBS ne le
rencontre pas).

## Implémentation

- `.drafts/claude/phase3/COLLECT_PROMPT.md` — l'instrument (émis Desktop #13).
- `.drafts/claude/phase3/CANDIDATES_<projet>.md` — un rapport par collecte.
- `docs/PATTERN_CANDIDATES.md` — agrégation/dédoublonnage Desktop (à créer à
  l'étape d'agrégation).
- Patterns retenus (E, F, …) → briefs CLI, branchés par le moule DEC-021
  (un fichier sous `patterns/` + `@register` + hooks optionnels, sans toucher
  `dispatcher.py` ni `server.py`).

## Évolution prévue

- **✅ Acceptée sur banc d'essai TBS (2026-05-25)** : `CANDIDATES_tbs.md`
  produit, 14 familles balayées → 5 retenus / 6 rejetés, schéma respecté,
  filtrage dur et juste (rejets `git push` / DB ad hoc / édition docs bien
  motivés), `security_prereqs` correctement exploité. L'instrument a fait
  émerger un nouveau pattern (E / Scan) **et** un arbitrage de conception
  (tbs-04, manipulation valeur vs référence de secret) — signal recherché.
  Aucune correction de l'instrument requise avant généralisation
  Bassmati/QNAP. Rythme Proposed→Accepted-sur-preuve, comme DEC-021.
- `ssh-remote` : DEC dédiée au moment QNAP (extension sandbox au remote).
- Whitelist `sudo` par projet : à concevoir si la collecte la justifie
  (DEC-008 Phase 3+).

## Trade-offs

- ✅ Instrument reproductible et auditable (vs exploration ad hoc).
- ✅ Banc d'essai TBS d'abord → on ne rode pas un mauvais prompt sur 3 projets.
- ✅ Référentiel optimAI accessible à la collecte → candidats comparés à
  l'existant, moins de faux positifs.
- ✅ `security_prereqs` sépare « hors périmètre » de « prérequis à débloquer »
  → la collecte fait remonter les vrais besoins (whitelist sudo) au lieu de les
  jeter.
- ❌ Trois collectes manuelles à lancer par Hassan (une par espace-projet) —
  inhérent au scope `conversation_search`, non automatisable depuis une seule
  instance.
- ❌ Qualité dépendante de la richesse de l'historique de chaque projet — un
  projet peu utilisé produira peu de candidats (acceptable, c'est un signal en
  soi).
