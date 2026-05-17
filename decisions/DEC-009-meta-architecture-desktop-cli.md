# DEC-009 : Méta-architecture — Desktop = Cortex, CLI = Hands intelligente

**Date** : 2026-05-17
**Statut** : ✅ Accepted

## Contexte

DEC-013 Bassmati ("Desktop-first, CLI minimal") établit la convention
transverse TBS / Bassmati / QNAP : Claude Desktop est le guide principal,
Claude CLI est réservé aux bugs itératifs nécessitant des tests
automatisés, Hassan exécute les commandes shell et gère Git.

Pour optimAI, plusieurs contraintes nouvelles s'ajoutent :

- Les **limitations de Claude Desktop avec les repos en iCloud** (sync,
  latences, parfois écritures instables sur les fichiers longs) rendent
  certaines opérations peu fiables.
- Le périmètre optimAI inclut du **code Python à écrire et tester**,
  pas juste de la documentation. Le mode "Hassan exécute tout"
  ferait perdre l'intérêt du projet.
- L'architecture optimAI elle-même (Cortex / Hands) suggère une
  **méta-archi parallèle** pour notre propre workflow : Desktop joue
  le rôle de Cortex, CLI joue le rôle de Hands intelligente (capable
  de penser, choisir, agir).

## Décision

**Pour le projet optimAI, étendre DEC-013 Bassmati** comme suit :

### Répartition des rôles

| Acteur | Rôle | Périmètre |
|--------|------|-----------|
| **Claude Desktop** | Cortex / chef d'orchestre / master | Architecture, décisions, planification, documentation, briefs CLI. Écrit les fichiers courts via MCP Filesystem. |
| **Claude CLI** | Hands intelligente / exécutant principal | Bootstrap technique, implémentation Python, tests, debugging itératif. Garde sa faculté de penser, choisir, agir. |
| **Hassan** | Validateur / opérateur sensible | Validation des décisions, exécution des opérations privilégiées (sudo, GitHub, install Osaurus, secrets). |
| **MCP Filesystem** | Pont lecture/écriture | Lectures sans limite. Écritures Desktop limitées aux fichiers courts (< 200 lignes). Au-delà, basculer sur CLI. |

### Convention de transition Desktop → CLI

Quand Desktop a besoin que CLI prenne le relais, il produit un **brief
CLI** dans `.drafts/claude/CLI/CLI_PROMPT_NNN_*.md` avec :
- Contexte et objectif de la session CLI
- Prérequis (état attendu du repo avant)
- Liste précise des actions à exécuter
- Critère de validation (comment vérifier que c'est OK)
- Référence aux DEC pertinentes

CLI lit ce brief en début de session et exécute. Il garde sa
faculté de questionner / ajuster si quelque chose ne tient pas la
route, mais le brief est sa feuille de route principale.

### Fallback Desktop → CLI en cas de problème MCP

Si une écriture Desktop via MCP Filesystem échoue (timeout iCloud,
fichier verrouillé, contenu trop long), Desktop bascule
immédiatement en mode "préparation de brief CLI" sans insister.

## Rationale

- L'architecture parallèle (Cortex/Hands au niveau projet ET au
  niveau workflow Desktop/CLI) crée une cohérence conceptuelle utile.
- DEC-013 Bassmati supposait que tout le code finissait par être
  écrit par Hassan ou Desktop. Pour optimAI, on a besoin d'un
  exécutant intelligent qui n'est ni l'un ni l'autre — CLI est
  parfait dans ce rôle.
- CLI garde son autonomie de jugement (pas un simple exécuteur de
  scripts) — c'est ce qui le distingue de "Hassan exécute".
- Hassan reste seul à toucher aux opérations privilégiées (sudo,
  GitHub auth, secrets) — cohérent avec DEC-008 et ses préférences
  sécurité.

## Implémentation

- Les briefs CLI suivent la convention Bassmati (`.drafts/claude/CLI/`)
- `CLAUDE.md` projet documente la répartition pour les sessions
  futures Desktop ET CLI
- Première application : `CLI_PROMPT_001_bootstrap.md` qui guide CLI
  pour le bootstrap technique du projet

## Trade-offs

- ✅ Workflow clair, chacun dans son rôle de force
- ✅ Économie de tokens Desktop (les actions itératives lourdes vont
  à CLI)
- ✅ Sécurité : Hassan reste maître des opérations sensibles
- ❌ Trois acteurs à coordonner (vs deux dans DEC-013 Bassmati) —
  mitigation : briefs CLI explicites
- ❌ Coût tokens CLI à surveiller — mais CLI travaille sur l'exécution
  ciblée d'un brief, pas sur de longues explorations
