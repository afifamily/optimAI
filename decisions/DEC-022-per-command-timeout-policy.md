# DEC-022 : Politique de timeout par-commande — par-pattern (Diagnose recover / Execute abort)

**Date** : 2026-05-20
**Statut** : 📝 Proposed (politique actée Desktop #8 ; passe ✅ Accepted
quand CLI #5 l'implémente et qu'Execute abort correctement sur un timeout
par-commande, sans refonte du moteur)
**Déclencheur** : REPORT CLI #4 §3 (point CLI #5 n°3) + annotation DEC-007
(« timeout par-commande récupérable vs timeout global ») — arbitrage en
amont du brief CLI #5
**Lié à** : [DEC-007](DEC-007-loop-limits.md) (limites de boucle — cette
DEC en précise la sémantique par-commande), [DEC-008](DEC-008-security-guardrails.md)
(échec explicite, §4), [DEC-021](DEC-021-dispatcher-engine-pattern-registry.md)
(le hook est une extension rétrocompatible du contrat `Pattern`),
[DEC-006](DEC-006-patterns-priority-A-D.md) (Patterns A & D prioritaires)

## Contexte

Aujourd'hui (CLI #4), le moteur `dispatcher.py` traite un timeout
par-commande de façon **uniforme et codée en dur** : dans le handler
`CommandTimeout` de `_run_loop`, la commande tuée est consignée, un message
« TIMED OUT » est réinjecté au worker, et la boucle **continue**
(`continue`). C'est le comportement « recover » hérité du PoC. Le vrai
garde-fou de budget reste le timeout **global** (`asyncio.wait_for`,
DEC-007).

Ce « recover » est **correct pour Diagnose** (Pattern A) : les commandes
sont informationnelles (`xcode-select -p`, `swift --version`…), read-only.
Une commande lente isolée (ex. un `find` trop large) tuée puis remplacée
par une commande plus ciblée ne laisse **aucun effet de bord** — récupérer
est sans risque, et c'est même souhaitable (le worker se corrige).

Le problème naît avec **Execute** (Pattern D, CLI #5) : ses commandes
**mutent l'état** (build, install, déplacement de fichiers…). Une commande
mutante qui dépasse son budget et se fait tuer **peut avoir laissé un effet
de bord partiel** (fichier à moitié écrit, build dans un état intermédiaire,
package partiellement installé). Continuer la boucle « comme si de rien
n'était » et laisser le worker enchaîner sur un état inconnu est exactement
le genre de **fallback risqué** que le projet proscrit (préférence Hassan,
DEC-008 §4 « échouer explicitement plutôt qu'un fallback risqué »).

## Alternatives évaluées

| Option | Diagnose | Execute | Verdict |
|--------|----------|---------|---------|
| **Politique globale unique = recover** (état actuel) | ✅ correct | ❌ continue sur état inconnu | Écartée — unsafe pour Execute |
| **Politique globale unique = abort** | ❌ casse la correction du worker (un `find` lent grille la tâche) | ✅ sûr | Écartée — pénalise Diagnose |
| **Le worker décide** (renvoie recover/abort) | imprévisible | imprévisible | Écartée — confie une décision de sûreté au modèle non fiable |
| **Politique par-pattern** (le pattern déclare sa politique) | recover | abort | **Retenue** — chaque pattern porte le niveau de risque de ses commandes |

## Décision

**La politique de récupération sur timeout par-commande est une décision
par-pattern**, portée par la stratégie elle-même :

- **Diagnose** → `recover` : réinjecte « TIMED OUT », la boucle continue
  (comportement actuel, conservé). Justifié : commandes read-only.
- **Execute** → `abort` : la boucle s'arrête et produit un report d'erreur
  (`stop_reason="command_timeout"`, `status="error"`) qui consigne la
  commande fautive et signale l'état potentiellement incohérent. Le Cortex
  reçoit l'information explicite plutôt qu'une suite d'actions sur un état
  inconnu.

**Invariant de sûreté (le cœur de la décision)** : un pattern qui
**n'explicite pas** sa politique ne doit **jamais** hériter silencieusement
de `recover`. Le défaut sûr est `abort`. Un futur pattern mutant ajouté
sans réflexion sur le timeout obtient ainsi le comportement prudent, pas le
comportement commode.

## Mécanisme (latitude CLI #5, sous contrainte DEC-021)

L'implémentation exacte est laissée à CLI #5, **mais doit être une
extension rétrocompatible du contrat `Pattern`** au sens du critère précisé
en DEC-021 (hook générique consulté par le moteur, pas de refonte de la
boucle). Forme indicative :

```python
# Sur le Protocol Pattern (base.py) :
def on_command_timeout(self, cmd: str, step: Step) -> Literal["recover", "abort"]:
    ...
```

- Le moteur appelle ce hook dans son handler `CommandTimeout` **au lieu**
  du `continue` actuel : `recover` → réinjection + `continue` (logique
  actuelle) ; `abort` → `pattern.build_report(..., stop_reason="command_timeout", status="error")`.
- Le moteur reste **agnostique** : il consulte le hook, il ne connaît
  aucun pattern. C'est précisément le **premier test concret** du critère
  DEC-021 (extension rétrocompatible vs refonte).
- Détail du défaut sûr (`abort` si non spécifié) : à réaliser via la forme
  que CLI #5 jugera la plus propre (méthode requise + convention de
  template, ou défaut explicite côté moteur). L'essentiel est l'invariant
  ci-dessus, pas la plomberie.

## Trade-offs

- ✅ Diagnose garde sa capacité d'auto-correction (recover) ; Execute
  échoue explicitement sur état inconnu (abort) — chaque pattern porte le
  risque réel de ses commandes
- ✅ Défaut sûr (`abort`) : pas de récupération risquée silencieuse pour un
  futur pattern mutant
- ✅ Mécanisme = extension rétrocompatible → valide DEC-021 sur un cas réel
- ✅ Aligne sur DEC-008 §4 (échec explicite) et la préférence « pas de
  fallback risqué »
- ❌ Une méthode de plus sur le Protocol (mais générique, consultée par le
  moteur — c'est le motif voulu par DEC-021, pas une fuite)
- ⚠️ **Question ouverte reportée** : certaines commandes Execute sont
  idempotentes (`mkdir -p`, `git fetch`…) et pourraient sereinement
  recover. Un raffinement « hint d'idempotence par-commande » est
  **explicitement hors périmètre** ici (YAGNI) — abort par défaut pour
  Execute, à reconsidérer seulement si un cas réel le motive.

## Note pour CLI #5

Cette DEC ne demande **pas** de toucher Diagnose au-delà de lui faire
déclarer `recover` (son comportement actuel, rendu explicite). Le gros du
travail est : (1) la méthode sur le Protocol, (2) le branchement dans le
handler `CommandTimeout` du moteur, (3) Execute qui déclare `abort`,
(4) un `stop_reason="command_timeout"` ajouté au vocabulaire des reports,
(5) tests : Execute abort sur timeout par-commande, Diagnose recover
inchangé.
