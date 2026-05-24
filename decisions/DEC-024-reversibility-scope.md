# DEC-024 : Périmètre de réversibilité — atomicité intra-appel (Phase 2), réversibilité de lot reportée

**Date** : 2026-05-23 (amendé 2026-05-24, Desktop #12 — sémantique du statut d'échec)
**Statut** : ✅ Accepted (Desktop #12)
**Déclencheur** : Conception Phase 2 (Patterns B/Patch & C/Create). Le
HANDOVER #11 pointe la question non tranchée — « où vit le snapshot/rollback :
pattern, moteur, ou git côté workdir ? » — à cadrer **avant** d'écrire du code.
**Lié à** : [DEC-002](DEC-002-custom-minimal-python.md) (minimal, pas de
sur-ingénierie), [DEC-008](DEC-008-security-guardrails.md) (échec explicite,
§4 « pas de fallback risqué »), [DEC-009](DEC-009-meta-architecture-desktop-cli.md)
(opérations privilégiées = Hassan, dont git), [DEC-021](DEC-021-dispatcher-engine-pattern-registry.md)
(moteur agnostique du pattern), [DEC-022](DEC-022-per-command-timeout-policy.md)
(abort sur mutation), [DEC-006](DEC-006-patterns-priority-A-D.md) (B/C = Phase 2)

## Contexte

B (Patch) et C (Create) sont les premiers patterns **mutants ET réversibles**.
A (Diagnose) est read-only ; D (Execute) mute mais sans exigence de
réversibilité (il *signale* un état incohérent via `abort`, il ne le *défait*
pas). B/C ajoutent un besoin neuf : prévisualiser (diff) et **annuler** une
modification.

« Réversibilité » recouvre en réalité **deux portées distinctes**, à séparer
avant tout choix d'emplacement :

1. **Atomicité intra-appel** — un seul appel `optimai_patch`/`optimai_create`
   peut toucher plusieurs fichiers/hunks ; si une partie échoue (édit qui ne
   matche pas, validation syntaxique KO, exception), on restaure *l'état
   d'avant cet appel*. Transactionnel, borné à l'appel.
2. **Réversibilité de lot inter-appels** — le Cortex enchaîne patch1 → patch2
   → patch3, juge le résultat global, et veut revenir *avant le lot*. Point de
   restauration empilé sur plusieurs appels.

La contrainte structurante : **chaque appel d'outil MCP est stateless**. Entre
deux appels, le serveur ne retient rien (le dispatcher se relance, le pattern
se réinstancie). La portée (1) est réalisable dans le cycle de vie d'un appel ;
la portée (2) ne l'est **pas** sans introduire un état persistant inter-appels
(store de snapshots + outil `rollback`) ou déléguer la mémoire à git côté
workdir.

## Alternatives évaluées

Portée (2) — réversibilité de lot — *où* la mémoire du lot vivrait :

| Option | Mémoire du lot | Coût | Verdict |
|--------|----------------|------|---------|
| **Intra-pattern étendu** (store de snapshots persistant + outil `rollback`) | fichiers hors cycle de vie de l'appel, ids gérés par optimAI | réimplémente, en moins fiable, ce que git fait déjà ; état + gestion de cycle de vie (empilement, péremption, GC) → sur-ingénierie (DEC-002) | Écartée |
| **Dans le moteur** (snapshot auto par appel) | moteur | casse l'agnosticité (DEC-021) ; sans frontière de lot déclarée, donne 1 snapshot *par appel*, pas *par lot* | Écartée |
| **Git côté workdir, orchestré hors optimAI** (`git stash`/checkpoint posé par CLI/Hassan avant le lot) | git du repo cible | impose une **pause** au Cortex Desktop avant chaque lot → casse le flux autonome | Viable mais coûteuse |
| **Git côté workdir, autorité donnée à optimAI** (outils `checkpoint`/`resolve`, branche `optimai/*`) | git, frontière déclarée par le Cortex | donne à optimAI l'**autorité d'écriture git** sur les repos réels de Hassan (aujourd'hui : read-only, ou mutant sandboxé) | **Inévitable à terme, prématurée maintenant** |

## Décision

**Phase 2 implémente uniquement la portée (1) — atomicité intra-appel.** La
portée (2) — réversibilité de lot, donc autorité git locale dans optimAI — est
**reconnue inévitable mais reportée post-Phase 3**.

### Ce qu'on fait en Phase 2

- Atomicité intra-appel **dans le pattern**, via un **helper de snapshot
  partagé** : copie temporaire éphémère des fichiers touchés, posée avant
  mutation, restaurée sur échec, nettoyée sur succès. **Pas de git** — on ne
  touche jamais l'état git du repo cible.
- optimAI **reste stateless** et **sans autorité git** — strictement la posture
  actuelle (read-only en A, mutant sandboxé en D).
- **Diff preview** = diff unifié calculé en pur Python (`difflib`) et remonté
  dans le report. Pas besoin de git.

### Corollaire de sûreté — l'acte mutant de B/C est déterministe et Cortex-sourced

L'atomicité (1) n'est garantissable que si l'acte mutant est **borné et
déterministe**. On en tire la sémantique de B/C (analogue à l'option (1)
d'Execute, DEC-006 / brief CLI #5) :

- Le **Cortex fournit le contenu exact** de la mutation dans le spec — B :
  édits recherche-remplacement (`old`/`new` par fichier) ; C : chemin + contenu
  complet des fichiers à créer.
- L'**application est mécanique et déterministe** (code Python, **pas** le
  worker), wrappée par le helper d'atomicité.
- Le **worker pilote la validation et le verdict**, pas la mutation :
  validation syntaxique via shell (`swiftc -parse`, `python -m py_compile`,
  `gofmt`/`go vet`…), interprétation d'un échec, formulation du report.

Ce **n'est pas** l'option (2) « entièrement scriptée » écartée pour Execute :
le raisonnement worker reste central (validation + verdict). On déplace
seulement l'acte mutant *risqué* hors de la main du worker LLM vers du code
exact — renforcement de sûreté approprié à des patterns réversibles opérant sur
des fichiers réels (Swift de TBS, etc.), où un `sed` improvisé par le worker
pourrait corrompre un fichier.

#### Le worker-driven n'est pas rejeté, il est différé (conditionnel)

La mutation déterministe + Cortex-sourced est le bon choix **maintenant**, pas
pour toujours. Confier la mutation elle-même au worker (worker-driven : le
modèle propose et applique les édits/créations) reste **envisageable à terme**,
sous l'une ou l'autre de ces conditions futures (verdict Hassan, Desktop #12) :

- **Quand l'option (2) — réversibilité de lot — sera implémentée** (post-Phase 3,
  esquisse ci-dessous) : un filet de rollback de lot solide rend une mutation
  worker-driven nettement moins risquée, puisqu'un lot raté redevient annulable
  en bloc.
- **Si on adopte un worker plus sûr** : un modèle dont la fiabilité sur l'édition
  de fichiers réels est suffisamment démontrée pour qu'un `sed`/édit improvisé
  ne soit plus un risque de corruption.

À reconsidérer explicitement à ce moment-là ; jusque-là, déterministe +
Cortex-sourced reste la posture.

### Pourquoi reporter la portée (2) (verdict Hassan, Desktop #12)

Trois raisons cumulatives :

1. **Balance gains/coûts défavorable aujourd'hui** : le gain (flux Desktop sans
   pause) ne vaut pas le coût (donner à optimAI l'autorité d'écriture git sur
   les repos réels, alors qu'il s'en tient à du read-only / mutant sandboxé).
2. **Attendre la maturité Phase 3** : la collecte de patterns E/F/… (Phase 3,
   depuis TBS/Bassmati/QNAP) élargira la variété des situations. Concevoir la
   réversibilité de lot *après* cet enrichissement lui donnera une vision large,
   plutôt que de la tailler sur les seuls B/C.
3. **Éviter la dette de compatibilité antérieure** : figer une mécanique git
   maintenant obligerait chaque pattern ajouté ensuite à composer avec un design
   arrêté trop tôt. Reporter évite cette dette.

## Esquisse conservée (reprise post-Phase 3 — ne pas reperdre le raisonnement)

Forme ébauchée Desktop #12 de la portée (2), si/quand on l'implémente :

- Frontière de lot **déclarée explicitement par le Cortex** (la statelessness
  empêche le moteur de la détecter seul) : `optimai_checkpoint(workdir)` → crée
  et bascule sur `optimai/checkpoint-<id>`, renvoie l'id ; les `optimai_patch`
  du lot committent sur `HEAD` ; `optimai_checkpoint_resolve(workdir,
  action=merge|discard)` clôt le lot.
- **Statelessness préservée** : l'état du lot vit dans **git lui-même** (la
  branche temp *est* le point de restauration), pas en mémoire d'optimAI.
  Chaque appel lit l'état git courant au lieu de mémoriser. Le « centralisé au
  niveau moteur » devient un **module partagé** (`checkpoint.py`) appelé
  explicitement, pas une session en mémoire.
- **Diff de lot gratuit** : `git diff <origine>..<branche-temp>` = le diff du
  lot entier (complète le diff intra-appel de la portée (1)).
- **Garde-fous** : précondition working tree propre (sinon refus, échec
  explicite) ; namespace réservé `optimai/*` (jamais `main`/`develop` en
  direct) ; **jamais de push** (DEC-009 intacte) ; asymétrie de résolution dans
  l'esprit DEC-022 — `discard`/rollback **autonome** (ne supprime que la branche
  optimAI), `merge` dans la vraie branche **gated** (Cortex explicite /
  validation Hassan).
- **Cas-limites** : workdir non-git (`/tmp/...`) → pas de réversibilité de lot,
  `checkpoint` échoue clairement (acceptable, ces cas sont jetables) ;
  changement de branche entre appels → `patch` refuse s'il n'est pas sur la
  branche `optimai/*` attendue.
- **Variante en réserve** : `git worktree` (isole le lot dans un répertoire
  séparé, ne touche jamais le working tree principal) — plus sûr mais cwd
  déporté, complexité jugée prématurée pour cette étape.

Cette portée (2) fera l'objet d'une **DEC dédiée** le moment venu (post-Phase 3).

## Amendement (2026-05-24, Desktop #12) — sémantique du statut d'échec

### Déclencheur : bug trouvé au smoke live B-rollback

Le premier smoke live de B/C (Desktop #12, sur `/private/tmp` jetable) a validé
C-succès et B-succès, puis **révélé un bug structurel** sur B-rollback : un
patch cassant volontairement la syntaxe (suppression du `:` d'une signature)
→ le worker lance `py_compile`, le voit échouer (`exit:1`), nomme correctement
la cause… mais le rapport sort `status="complete"`. Conséquence : le moteur
nettoie le snapshot au lieu de restaurer (`if report.status == "error"`), et le
fichier reste **cassé sur disque**. L'atomicité intra-appel décidée plus haut
n'était donc pas réellement déclenchée sur échec de validation.

### Cause racine (dans le code, pas hypothèse)

`dispatcher._run_loop` code **`status="complete"` en dur** dès que le worker
émet une `report` finale (`step.kind == "final"`). `build_report` ne fait que
recopier ce statut. Donc, dans le contrat actuel, **ni le worker ni le pattern
n'ont de canal pour transformer une convergence en échec** : le seul fait
d'émettre une `report` force `complete`. C'est un défaut **du contrat**, pas de
Pattern B — C y est exposé à l'identique (un fichier créé non compilable
resterait aussi).

### Décision (verdict Hassan, Desktop #12) — « ceinture + bretelles »

Le statut d'échec d'un appel est déterminé par **deux mécanismes complémentaires** :

1. **Socle déterministe (le moteur, non contournable)** — c'est l'invariant de
   sûreté : si la **commande de validation** désignée par le pattern se termine
   avec un **exit ≠ 0**, le moteur force `status="error"` (donc rollback), quoi
   que rapporte le worker. La fiabilité du rollback **ne dépend plus du jugement
   du LLM** — exactement l'esprit de DEC-024 (l'acte de sûreté est déterministe,
   pas confié au worker).
   - Subtilité révélée par le code : le moteur **ne doit pas** se contenter de
     « dernier `exit ≠ 0` → error » aveuglément, car un pattern mutant autorise
     le worker à lancer **une commande de diagnostic read-only** (cf.
     `system_prompt` de Patch). Un exit≠0 sur un *diagnostic* ne doit pas
     déclencher de rollback. Le pattern doit donc **désigner sa commande de
     validation** (petit ajout de contrat, générique B+C).
2. **Couche worker additive (la finesse)** — le worker peut **déclarer un échec
   sémantique** même quand la validation sort `exit:0` mais que sa *sortie*
   révèle un problème (test qui « passe » en sautant des cas, linter laxiste).
   Cela impose de **lever le `status="complete"` codé en dur** du moteur et de
   le déléguer, pour qu'un payload final négatif produise `status="error"`.

**Invariant non négociable** : le socle déterministe (1) prime. Le worker peut
*ajouter* un échec (exit 0 + sortie suspecte), il ne peut **jamais** transformer
un exit≠0 de validation en succès. (1) est la garde ; (2) est le détecteur de
finesse.

### Précision (2026-05-24, soir — collision trouvée par lecture de `create.py`)

En relisant `create.py` après le correctif CLI #8, une **collision** entre le
socle déterministe (1) et la dégradation propre des validateurs est apparue —
pas encore observée (la machine a `swiftc`), mais logiquement certaine et **non
déterministe** (dépend du comportement du worker) :

- La dégradation propre (DEC-024 ci-dessus, « un outil de validation absent
  n'invalide pas la création ») repose aujourd'hui **uniquement sur une consigne
  langage naturel du `system_prompt`** : `validation_command_for` renvoie
  toujours `swiftc -parse <f>` sans vérifier que `swiftc` existe ; c'est au
  worker de lire un « command not found » et de ne pas marquer l'échec.
- Or le Layer 1 a retiré au worker l'autorité sur le statut. Si le worker lance
  la validation et que l'outil est absent → `swiftc -parse` sort **exit 127** →
  `is_validation_command` = True → Layer 1 force `error` → **rollback d'un
  fichier pourtant valide**. Exactement le faux négatif que la dégradation
  devait empêcher. Et selon que le worker diagnostique (`which`) d'abord ou
  non, le bug se produit ou pas → **non déterministe**.

**Invariant ajouté** : *un outil de validation **absent** n'est pas un échec de
validation*. Un « command not found » (typiquement exit 127) sur la commande de
validation ne doit **jamais** déclencher de rollback d'un fichier par ailleurs
valide — c'est une **dégradation propre** (skip + note), pas une erreur. Et
cette décision doit être **déterministe (côté code)**, pas confiée au jugement
du worker — même logique que tout l'amendement : les décisions de sûreté sortent
de la main du LLM.

Le *comment* est laissé à CLI (verdict Hassan, Desktop #12) — pistes :
distinguer l'exit 127 des autres exit≠0 dans le Layer 1 ; ou vérifier la
présence de l'outil **avant** de produire la commande (`validation_command_for`
renvoie `None` si l'outil est absent → pas de validation, comme `language=
"none"` → pas de Layer 1, skip par construction quel que soit le worker). La
seconde a la préférence Desktop (élimine la non-déterminisme), mais CLI tranche
l'implémentation tant que l'invariant ci-dessus tient.

### Contrainte de rétrocompatibilité (DEC-021)

Lever le `complete` codé en dur touche le **chemin commun de tous les patterns**
(A/D compris). La correction doit : garder `complete` par défaut quand le
pattern n'exprime rien (A/D inchangés, leurs tests restent verts), et n'activer
la dérivation de statut que pour les patterns qui la déclarent. Le *comment*
exact (méthode optionnelle du `Protocol` ? statut dérivé dans `build_report` ?
champ sur le `Step` final ? désignation de la commande de validation) est laissé
à l'implémentation CLI, **sous réserve** de rester une extension via `getattr`
au sens DEC-021 — pas une refonte de la boucle ni une signature existante
modifiée. CLI est explicitement invité à proposer une **meilleure alternative**
s'il en voit une, tant que l'invariant ci-dessus tient.

### Leçon de test (capturée pour TROUBLESHOOTING / Desktop #13)

Les tests mockés CLI #7 passaient au vert parce qu'ils simulaient un worker
renvoyant proprement `status="error"` sur validation KO — situation que le
**vrai worker ne produit pas**. C'est la deuxième fois qu'un mock donne une
fausse confiance (cf. `pythonpath=src` masquant l'install). Le correctif doit
inclure un **test live** (`@pytest.mark.live`) reproduisant le cas réel : vrai
worker + validation échouée → `status="error"` → fichier restauré à l'octet près.

## Trade-offs

- ✅ B/C avancent vite : l'atomicité intra-appel est petite, locale au pattern,
  sans état ni git.
- ✅ optimAI garde sa posture de sûreté actuelle (stateless, sans autorité git
  sur les repos réels).
- ✅ Application mutante déterministe → réversibilité fiable, pas de corruption
  par le worker.
- ✅ Évite la dette de compat antérieure (DEC-002) en n'arrêtant pas la
  mécanique de lot avant la maturité Phase 3.
- ❌ Le flux Desktop autonome de bout en bout pour un *lot* de patches reste
  hors de portée jusqu'à la portée (2) : tant qu'elle n'existe pas, revenir
  avant un lot se fait à la main (git côté Hassan/CLI) ou pas du tout. Assumé.
- ⚠️ La portée (2) est **inévitable** — la reporter n'est pas la nier.
  L'esquisse ci-dessus est conservée pour ne pas repayer le coût de conception.
