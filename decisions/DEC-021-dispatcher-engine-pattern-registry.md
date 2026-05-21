# DEC-021 : Architecture Dispatcher — moteur unique + registre de patterns (Strategy)

**Date** : 2026-05-20
**Statut** : 📝 Proposed (architecture actée Desktop #7 ; passe ✅ Accepted
quand un 2ᵉ pattern — Execute, CLI #5 — se branche sans retoucher
`patterns/base.py`, confirmant que le contrat est bien taillé)
**Déclencheur** : Arbitrage Desktop #7 sur la promotion du PoC Pattern A
en `patterns/diagnose.py` + anticipation Hassan de la croissance du
nombre de patterns (Phase 3 : collecte de patterns depuis TBS/Bassmati/QNAP)
**Lié à** : [DEC-002](DEC-002-custom-minimal-python.md) (minimal, pas de
framework), [DEC-006](DEC-006-patterns-priority-A-D.md) (A & D prioritaires),
[DEC-007](DEC-007-loop-limits.md) (limites appliquées par le moteur),
[DEC-008](DEC-008-security-guardrails.md) (blacklist/sandbox dans le moteur)
**Fusionne** : l'ancienne candidate DEC-021 « contrat Cortex↔Hands : domain
knowledge via `spec.context` » (apprentissage CLI #3 §5.5) — même question
sous-jacente : « qu'est-ce qu'un pattern et que doit-il fournir ? »

## Contexte

Le PoC Pattern A (CLI #3, `scripts/poc_diagnose_xctest.py`) mélange dans
un seul script la **boucle d'orchestration** (worker → shell → worker,
bornée DEC-007) et le **rendu console**. Le promouvoir en module impose
de trancher *où vit la boucle*, et la réponse gouverne toute la
croissance future du Dispatcher.

Deux axes de croissance, à ne pas confondre :

1. **Le nombre de patterns grandit** — A, D, puis B/C (Phase 2), puis
   E/F/… issus de la collecte Phase 3 sur TBS/Bassmati/QNAP (prévu dès
   Desktop #1). C'est l'axe dominant.
2. **Le moteur de boucle se complexifie** — retry, observabilité,
   sandboxing Docker (Phase 4).

Le piège que cette DEC écarte explicitement : répondre à l'axe 1 en
**fragmentant le dispatcher** en `dispatcher_diagnose.py`,
`dispatcher_execute.py`, … Cela dupliquerait la mécanique de boucle
(itérer, borner, réinjecter, appliquer la blacklist) à chaque pattern —
exactement le défaut de l'option « boucle dans chaque pattern » écartée
pendant l'arbitrage. L'axe 1 n'appelle pas plusieurs dispatchers : il
appelle **un registre de patterns**.

## Alternatives évaluées

| Option | Boucle | Ajout d'un pattern | DRY | Verdict |
|--------|--------|--------------------|-----|---------|
| **(a)** Boucle dans chaque `patterns/*.py` ; dispatcher = simple routeur | dupliquée par pattern | nouveau fichier qui re-code la boucle | ❌ | Écartée — duplication ~80% entre Diagnose et Execute |
| **(a')** Un `dispatcher_<pattern>.py` par pattern | dupliquée par fichier | nouveau dispatcher | ❌ | Écartée — même défaut, juste renommé |
| **(b)** Moteur de boucle unique + stratégies minces enregistrées | unique, partagée | nouveau fichier `patterns/x.py` + `@register`, dispatcher inchangé | ✅ | **Retenu** |

## Décision

**Strategy pattern + registre.** Un **moteur de boucle unique** dans
`dispatcher.py`, et **N stratégies minces** dans `patterns/`, chacune
enregistrée dans un registre. Le moteur ne grossit pas avec le nombre de
patterns (il n'évolue que sur l'axe 2).

### Layout

```
src/optimai/
  dispatcher.py        # LE moteur unique : boucle worker↔shell, limites
                       #   DEC-007 (asyncio.wait_for global + compteur
                       #   d'itérations), blacklist DEC-008, réinjection
                       #   des résultats. Pur : retourne un report, zéro print.
                       #   N'évolue que sur l'axe 2 (retry, Docker…).
  patterns/
    base.py            # Protocol `Pattern` (le contrat) + registre @register
    diagnose.py        # stratégie A   (CLI #4)
    execute.py         # stratégie D   (CLI #5)
    # patch.py, create.py …  (Phase 2)
    # + E/F issus de Phase 3 : un fichier = un pattern, dispatcher.py intact
```

### Le contrat `Pattern` (cœur de l'extensibilité)

Mince — un protocole, pas une classe de base lourde. Forme indicative
(à finaliser CLI #4 sur Diagnose, à confirmer CLI #5 sur Execute) :

```python
class Pattern(Protocol):
    name: str                                  # "diagnose", "execute", …
    spec_model: type[BaseModel]                # DiagnoseSpec, ExecuteSpec, …

    def system_prompt(self, spec) -> str: ...      # cadrage + protocole
    def parse(self, worker_text: str) -> Step: ... # action | conclusion
    def build_report(self, trace, stop_reason, iterations) -> BaseModel: ...
```

Enregistrement par décorateur, pour que l'axe 1 soit sans couture :

```python
@register("diagnose")
class DiagnosePattern: ...
```

Conséquences :
- Ajouter un pattern = créer `patterns/foo.py` + `@register("foo")`.
  **Zéro ligne touchée dans `dispatcher.py`.**
- Le serveur MCP (ROADMAP étape 8) **itère sur le registre** pour exposer
  les tools (`optimai_diagnose`, `optimai_execute`, …) — pas de liste en
  dur à maintenir en parallèle.

### Contrat Cortex↔Hands (ex-candidate DEC-021, fusionnée)

Le `system_prompt(spec)` d'un pattern porte **uniquement le cadrage de
périmètre + le protocole générique** (format de réponse attendu, outils
autorisés, interdiction de scanner le FS hors workdir). La **connaissance
domaine** (ex. « pour un souci XCTest, vérifier `xcode-select -p`,
`xcrun`, la toolchain active ») est fournie **par le Cortex via
`spec.context`**, jamais codée en dur dans le worker ou le pattern.

Apprentissage fondateur (CLI #3 §5.5) : une v1 de system prompt trop
ouverte laissait le worker partir en `find` dans tout `$HOME` sans
converger ; la version cadrée (périmètre + domaine injecté par le Cortex)
converge en 2 itérations. C'est la répartition « Cortex = quoi chercher,
Hands = comment l'exécuter » qui rend les patterns génériques et réutilisables.

## Garde-fous contre la sur-ingénierie (DEC-002)

- On **pose la structure** (`base.py` + registre + **un seul** pattern
  branché) mais on ne **généralise pas dans le vide** : un seul pattern
  réel (Diagnose) en CLI #4.
- Le contrat `Pattern` sera **confirmé empiriquement** quand Execute s'y
  branche en CLI #5. S'il faut modifier `base.py` pour accueillir Execute,
  c'est le signal que l'abstraction était mal taillée — appris sur 2 cas
  réels, pas sur 1 réel + 5 imaginaires.
- **Pas** de conception anticipée pour les patterns Phase 3 non encore
  identifiés : le registre les **accueillera**, mais on ne devine pas leur
  forme aujourd'hui (YAGNI).

## Implémentation

- **CLI #4** : `dispatcher.py` (moteur pur), `patterns/base.py` (Protocol
  + registre), `patterns/diagnose.py` (stratégie A branchée, system prompt
  factorisé : cadrage + protocole, domaine via `spec.context`). Tests
  pytest mockant worker + shell sur la **logique de boucle** (sans
  `mlx_lm.server` live). PoC conservé en smoke-test `@pytest.mark.live`.
- **CLI #5** : schemas `ExecuteSpec`/`ExecuteReport` + `patterns/execute.py`
  branché sur le moteur **sans toucher `base.py`** → validation du contrat
  → promotion de cette DEC en ✅ Accepted.
- **ROADMAP étape 8** : serveur MCP itère sur le registre.

## Critère de passage en ✅ Accepted (précisé Desktop #8, avant CLI #5)

Le critère initial — « Execute se branche sans toucher `patterns/base.py` »
— était un proxy littéral. Précisé à froid **avant** de voir le résultat
de CLI #5, pour éviter toute réinterprétation opportuniste du critère a
posteriori :

- ✅ **Extension rétrocompatible du contrat** — ajouter une *nouvelle*
  méthode au Protocol que le moteur consulte de façon **générique** (ex.
  un hook `on_command_timeout(...) -> "recover" | "abort"` que le moteur
  appelle sans rien savoir du pattern), chaque pattern déclarant sa
  politique. Le moteur reste agnostique, le registre absorbe. → DEC-021
  **tient** (principe Open/Closed : ouvert à l'extension, fermé à la
  modification cassante).
- ❌ **Refonte** — devoir modifier la *boucle* du moteur pour un besoin
  spécifique à Execute, faire fuiter un import Diagnose/Execute dans
  `dispatcher.py`, ou changer une signature *existante* du Protocol de
  façon cassante. → DEC-021 **a raté sa cible**, à reconnaître
  explicitement.

L'invariant réellement protégé n'a jamais été « zéro ligne dans
`base.py` » mais « **le moteur ne connaît aucun pattern, et le contrat
s'étend sans se refondre** ». L'addition probable de `on_command_timeout`
(DEC-022) est précisément le **premier test** de cette distinction : si
elle se fait par hook générique + déclaration par-pattern, DEC-021 passe ✅.

## Trade-offs

- ✅ Axe 1 (nombre de patterns) absorbé sans couture par le registre ;
  `dispatcher.py` stable
- ✅ Pas de duplication de la mécanique de boucle entre patterns
- ✅ Serveur MCP dérivé du registre — une seule source de vérité des tools
- ✅ Contrat Cortex↔Hands explicite → patterns génériques et réutilisables
- ❌ Une abstraction (`Pattern` + registre) à concevoir maintenant plutôt
  que plus tard — mitigé : taillée mince, validée sur 2 cas réels avant
  d'être déclarée stable
- ❌ Le contrat pourrait devoir bouger une fois en CLI #5 — assumé, c'est
  précisément le critère de passage en ✅ Accepted
