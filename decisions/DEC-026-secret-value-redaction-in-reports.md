# DEC-026 : Non-divulgation des valeurs de secrets en sortie (reports & logs)

**Date** : 2026-05-25
**Statut** : ✅ Accepted

## Contexte

La collecte Phase 3 (DEC-025) a fait émerger, sur **deux** projets indépendants,
des tâches qui doivent manipuler la **valeur** d'un secret — pas seulement une
référence d'env :

- **tbs-04** (caviardage à l'archivage) : remplacer chaque valeur de token bot
  par un placeholder → le `old` de l'édit *est* la valeur du token.
- **bassmati-02** (garde DEC-015) : prouver que la valeur d'`ADMIN_PREFIX`
  n'apparaît jamais dans `robots.txt`/`sitemap.xml`/HTML → il faut chercher
  cette valeur précise.

Ces deux cas reviennent au même besoin sous le futur **Pattern E (Scan/Audit)**
et sous **Pattern B (Patch)** : *prouver l'absence* ou *supprimer* une valeur
sensible. Or « prouver l'absence d'une valeur précise » exige de **connaître**
cette valeur pour la chercher — on ne peut pas l'éviter en entrée.

### Ce qui n'est PAS le problème

L'invariant DEC-008 §3 (« les valeurs du `.env` ne transitent jamais dans les
prompts worker ») n'est **pas** en cause : il porte sur les secrets chargés par
le Dispatcher depuis `.env`. Ici la valeur est introduite **volontairement par
le Cortex** comme motif de recherche, via `context` — un champ déjà décrit
comme *non scanné par la blacklist, pouvant citer des tokens* (PATTERNS.md). Le
worker peut donc légitimement recevoir cette valeur en **entrée**.

### Ce qui EST le problème — la sortie

Une fois la valeur cherchée, elle risque de **réapparaître en clair** dans ce
qui sort du worker et **survit** à l'appel :

1. **Remontée au Cortex** : le report repart vers un modèle distant (coût token
   + la valeur ré-entre dans un contexte LLM).
2. **Persistance disque** : la trace est écrite dans les logs (`logs/`).

Trois vecteurs de fuite, tous visibles dans les schémas actuels :

- `matches[].text` (Scan) — l'occurrence trouvée contient la valeur.
- `commands_executed[].cmd` (A/D/E) — la commande `grep "<valeur>" …` **contient
  le motif** : border `text` sans border `cmd` laisserait fuir la valeur.
- `notes` / `summary` (D) / `evidence` (A) — champs libres rédigés par le worker.

## Décision

**Invariant de sortie ajouté à DEC-008.** Une valeur de secret fournie par le
Cortex comme motif de recherche ou cible de remplacement **ne doit jamais
réapparaître en clair dans un champ de report remonté au Cortex, ni dans une
trace persistée sur disque.** Asymétrie entrée/sortie assumée, parallèle à
l'asymétrie lecture/écriture de la sandbox (DEC-008 §2) : la valeur peut entrer
(pour être cherchée), elle ne peut pas sortir.

**Argument de coût nul.** Les deux usages réels n'ont **pas besoin** de la
valeur en sortie :
- *Prouver l'absence* → le **compte** suffit (`0` = pass) ; sur fail, la
  **localisation** (`file:line`) suffit pour corriger.
- *Caviarder* → le **compte de remplacements** + `file:line` suffisent.

La garde ne retire donc aucune capacité fonctionnelle.

### Mécanisme (orientation — détails fins au brief CLI / PoC)

1. **Marquage explicite des motifs sensibles.** Le Cortex distingue les motifs
   *sensibles* (valeurs de secrets) des motifs *non sensibles* (références de
   doc obsolète, balises SEO). Forme exacte à trancher au brief — piste : un
   champ dédié `secret_patterns: list[str]` distinct des motifs normaux, plutôt
   qu'un flag global, pour qu'un même appel puisse mêler les deux registres.
2. **Redaction en sortie, avant persistance ET avant retour Cortex.** optimAI
   remplace toute occurrence d'un motif sensible par un placeholder stable
   (p.ex. `<secret:1>`) dans **tous** les champs sortants : `matches[].text`,
   `commands_executed[].cmd`, `notes`, `summary`, `evidence`. La redaction est
   appliquée par le Dispatcher (déterministe, Cortex-trusted), **pas** déléguée
   au worker — cohérent avec DEC-024 (l'acte sensible reste déterministe, le
   worker ne s'autocensure pas).
3. **Verdict basé sur compte + localisation.** Pour les motifs sensibles, le
   report renvoie `{file, line}` et le **compte**, jamais le `text` brut. Pour
   les motifs non sensibles, `text` reste en clair (utile, non sensible).
4. **Patch/caviardage (B)** : le report ne renvoie que le compte de
   remplacements + `file:line` ; le diff ne montre jamais la valeur côté `old`.

### Alternative écartée

*Interdire la valeur en entrée* (vérifier structurellement, p.ex. « absence de
ligne `Disallow:` exposante » sans connaître la valeur). Rejetée comme principe
général : on ne peut pas prouver l'absence d'une valeur **précise** sans la
chercher. La vérification structurelle reste une **variante** valable pour les
cas où elle s'applique (à choisir par le Cortex appel par appel), mais ne couvre
pas le besoin général tbs-04/bassmati-02.

## Implémentation

- `src/optimai/` : la redaction est une étape du Dispatcher sur le report
  *avant* sérialisation (retour MCP) **et** *avant* écriture log. Un seul point
  de passage pour couvrir les deux sorties.
- Schéma : champ d'entrée pour les motifs sensibles (forme au brief) ; les
  reports n'ont pas besoin de nouveau champ (la redaction agit sur les champs
  existants).
- Tests : un secret marqué ne doit apparaître **dans aucun** champ du report ni
  dans le fichier log — vérif sur les trois vecteurs (`text`, `cmd`, champs
  libres). Garde architecturale candidate, dans l'esprit des gardes
  `no_*_imports` (Phase 2).
- À implémenter **avec** le Pattern E (même brief CLI ou brief jumeau) : E est
  le premier consommateur ; sans cette garde, E ne doit pas traiter de motif
  sensible.

## Évolution prévue

- **✅ Acceptée par Hassan (Desktop #13, 2026-05-25)** : principe entrée
  autorisée / sortie interdite validé ; redaction côté Dispatcher (déterministe,
  pas le worker) validée ; couplage E + DEC-026 dans le même brief CLI validé.
  Décision de principe, pas de preuve expérimentale à attendre.
- La forme exacte du marquage des motifs sensibles (`secret_patterns` vs autre)
  est figée au brief CLI du Pattern E.
- Si un cas futur exige de remonter une valeur sensible au Cortex (non
  identifié à ce jour), il rouvrira cette DEC explicitement.

## Trade-offs

- ✅ L'invariant « le secret ne fuit pas » est étendu à la sortie, là où le vrai
  risque Phase 3 se trouve — sans bloquer les usages réels (coût fonctionnel nul).
- ✅ Redaction déterministe côté Dispatcher (Cortex-trusted), cohérente avec
  DEC-024 ; le worker n'a aucune responsabilité de censure.
- ✅ Un seul point de passage (report avant sérialisation/log) couvre les deux
  sorties (Cortex + disque) et les trois vecteurs.
- ❌ La redaction par appariement de chaîne peut manquer une valeur **transformée**
  (encodée base64, découpée) — risque résiduel théorique, même esprit que la
  note DEC-008 sur l'obfuscation : on protège contre la réapparition littérale,
  pas contre une transformation adverse (le worker n'a pas d'intention adverse).
- ❌ Léger surcoût : le Cortex doit marquer ses motifs sensibles (vs tout passer
  en vrac). Acceptable — c'est un acte conscient, cohérent avec la rigueur
  sécurité du projet.
