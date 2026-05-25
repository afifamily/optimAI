# PATTERN_CANDIDATES — optimAI Phase 3 · agrégation cross-projet

> Consolidation Desktop #13 (2026-05-25) des trois collectes DEC-025 :
> `CANDIDATES_tbs.md`, `CANDIDATES_bassmati.md`, `CANDIDATES_qnap.md`
> (`.drafts/claude/phase3/`). 15 candidats bruts → dédoublonnés par mécanique.
> Objet : figer ce qu'on construit, ce qu'on délègue tel quel, et ce qui est
> bloqué derrière une décision d'architecture — avant d'écrire les briefs CLI.

## Synthèse en une phrase

La généralisation confirme **un seul nouveau pattern à construire (E — Scan/Audit**,
prouvé sur les 3 projets), valide **D et A** sur de nouveaux usages locaux sans dev,
et fait émerger **`ssh-remote` comme une dimension d'exécution transverse** (et non un
pattern) qui *gate* la majorité de la valeur opérationnelle QNAP/prod.

---

## Le signal de généralité (lecture cross-projet)

| Mécanique | TBS | Bassmati | QNAP | Verdict |
|---|---|---|---|---|
| **Scan/Audit** (grep motifs → verdict, read-only) | tbs-01 (secrets, doc) | bassmati-02 (SEO, leak DEC-015, **+HTTP**) | qnap-05 (cohérence doc, **local**) | **Pattern E — à construire.** Généralité prouvée 3/3. |
| **Build-test-verdict** (D-vert / A-échec) | tbs-03 (`swiftb`) | bassmati-01 (`go`) | qnap-01 (remote-health) | **Couvert D+A.** Généralité 3/3. |
| **Pack ordonné mutant** (`abort`) | tbs-02 (migrations SQL) | bassmati-04 (backup-prod) | qnap-02 (services Docker) | **Couvert D.** Généralité 3/3 — mais 2/3 gated `ssh-remote`. |
| **Diagnose** (read-only → cause/fix) | (cas XCTest fondateur) | bassmati-03 (toolchain) | qnap-04 (état NAS) | **Couvert A.** Validé sur nouveaux usages. |
| **Lancer un script + lire le récap** (D, 1 commande) | tbs-05 (strip-comments) | bassmati-05 (build-review) | — | **Couvert D.** Gain faible mais propre. |

Deux familles ressortent sur **les trois** projets (Scan, Build-test) ; une troisième
(pack ordonné) aussi, mais coupée en deux par `ssh-remote`. C'est le critère de priorité
de DEC-025 : la récurrence cross-projet prouve la généralité.

---

## File A — délégable aujourd'hui (local, pas de blocage)

### A unique chantier de dev : Pattern E — Scan/Audit  ★ priorité n°1

- **Quoi** : étant donné une liste de motifs (requis-présents et/ou interdits-absents)
  fournie par le Cortex et une ou plusieurs cibles, le worker récupère chaque cible,
  grep, et renvoie `matches: [{target, line, text}]` + un `verdict` pass/fail. Read-only.
- **Preuves** : tbs-01, bassmati-02, qnap-05 (3 projets, 3 registres).
- **Profil de risque** : minimal — read-only, politique timeout `recover` (comme A).
- **Sources à supporter** : arborescence FS **et** réponses HTTP (`curl <url>`) —
  l'extension HTTP vient de bassmati-02 (audit SEO + garde DEC-015). Même mécanique.
- **Pourquoi un nouveau pattern et pas D/A** : read-only comme A, mais A « interdit le
  scan de gros arbres » (PATTERNS.md §A) et son report est root_cause/fix, pas une liste
  d'occurrences. Le mapper sur D donnerait la mauvaise sémantique de timeout (`abort`).
- **Mise en œuvre** : moule DEC-021 — `patterns/scan.py` + `@register` + report dédié,
  sans toucher `dispatcher.py` ni `server.py`. Ce serait le **5ᵉ test du contrat DEC-021**.
- **⚠ Arbitrage sécurité à trancher AVANT le brief** (point chaud, voir plus bas) :
  tbs-04 et bassmati-02 impliquent que le worker manipule la **valeur** d'un secret
  (motif interdit à chercher), en tension avec DEC-008 §3.

### Délégables tel quel via D/A (zéro dev, gain immédiat)

- **Build-test-verdict** (tbs-03, bassmati-01) — pack D `[build, test]`, `abort`, bascule
  A sur échec. Extension *optionnelle* : hook par-pattern remontant `tests_passed/failed`
  (DEC-021), pas une refonte moteur. À ne pas créer comme pattern.
- **Diagnose local** (bassmati-03 toolchain Go/Docker/GHCR) — usage de A.
- **Apply-migrations** (tbs-02) — pack D ordonné `docker exec psql < UPDATE_*.sql`, local.
- **Lancer-script** (tbs-05 strip-comments, bassmati-05 build-review) — pack D 1 commande,
  local, gain faible. ⚠ bassmati-05 : **exclure** le `python -m http.server` du pack
  (exposition réseau d'un serveur, DEC-008).
- **qnap-05 Doc-consistency-scan** — usage **local** de E (repo iCloud, dans la sandbox).
  Le seul candidat QNAP délégable sans attendre `ssh-remote`.

---

## File B — gated `ssh-remote` (bloqué derrière une décision d'archi)

**La découverte structurante de la phase.** `ssh-remote` n'est pas un pattern : c'est une
**dimension d'exécution distante** que les patterns A/D doivent acquérir. La sandbox
DEC-008 §2 épingle le `cwd` à un `workdir` **local** ; or ces candidats exécutent leur
effet **sur le NAS** via `ssh qnap '…'`. Tant que l'extension sandbox→hôte distant
n'existe pas, ils sont **conçus mais non délégables**.

Candidats concernés (tous correctement *retenus comme signaux*, pas jetés — DEC-025) :

| Candidat | Pattern | Face | Risque |
|---|---|---|---|
| qnap-01 remote-health | D-vert / A | **lecture** distante | faible (read-only) |
| qnap-04 remote-diagnose | A | **lecture** distante | faible (read-only) |
| qnap-03 network-recovery | D | **pont** local+remote | minimal (état volatil, rollback nul) |
| qnap-02 remote-service-pack | D | **écriture** distante | élevé (mutation services prod) |
| bassmati-04 backup-prod | D | **écriture** distante | moyen (snapshot+rsync) |

**Dossier d'instruction `ssh-remote` (legs de la collecte QNAP), pour la DEC dédiée :**
- Deux faces à couvrir : **lecture** distante (entrée à faible risque) et **écriture**
  distante (`abort` de D y prend tout son sens).
- **`sudo` distant** : NOPASSWD côté NAS → **pas un cas `secret`** (DEC-025) ; à intégrer
  à la whitelist sudo-par-projet (DEC-008 Phase 3+), mais portant sur des commandes
  lancées *après* `ssh` → couple les deux sujets.
- **Secrets distants** : `.env` de stack résolus dans l'env du subprocess **sur le NAS** ;
  l'invariant DEC-008 §3 (référence, pas valeur) doit être réaffirmé côté remote.
- **Échelle de risque suggérée pour la DEC** : pilote read-only (qnap-01) → pont (qnap-03)
  → mutation distante (qnap-02). Aligné sur l'esprit prudent de DEC-008/DEC-024.

---

## Point chaud sécurité — manipulation de VALEUR de secret (transverse E)

Surfacé par tbs-04 **et** bassmati-02 (donc pas un cas isolé) : certains scans/patches
doivent chercher la **valeur** d'un secret (token bot, `ADMIN_PREFIX`) pour *prouver son
absence* ou la *caviarder*. Le worker manipule alors une valeur, pas seulement une
référence d'env — en tension avec l'invariant DEC-008 §3.

- Atténuations déjà notées : la valeur transite par `context` (non scanné par la
  blacklist) ; sur un **pass** (cas attendu) rien de sensible ne remonte ; sur un
  **fail**, le `text` localise la fuite (c'est l'information voulue), à condition que le
  report **tronque/encadre** et n'écho jamais la valeur au-delà de l'occurrence.
- **À trancher en DEC avant d'implémenter E** (et a fortiori tbs-04 / la composante leak
  de bassmati-02) : faut-il une garde dédiée « le report n'écho jamais la valeur, seulement
  N occurrences / N remplacements » ? Variante *sans valeur* possible pour certains cas
  (vérifier structurellement l'absence d'une ligne exposante plutôt que la valeur).

---

## Rejets notables (cohérents sur les 3 projets)

Mêmes motifs partout, signe que les anti-critères tiennent : `git push` / push image GHCR
(écriture remote, DEC-008/009) ; rédaction de doc (jugement Cortex à chaque tour) ;
requêtes DB ad hoc (exploratoire) ; setup one-shot ; tâches déjà automatisées (backup
hebdo QNAP, détection reboot) ; opérations Web UI privilégiées (firmware) ; outils absents
de la cible (`smartctl` ARM). Un signal de conception capté : le **batch image Bassmati**
(~30 min) dépasse le budget DEC-007 → un éventuel « batch runner longue-durée » demanderait
un régime de budget distinct (note, pas un retain Phase 3).

---

## Recommandation de séquencement (à valider par Hassan)

1. **DEC sécurité « report-ne-révèle-pas-la-valeur »** (point chaud transverse) — débloque
   E proprement. Courte, cible l'invariant DEC-008 §3.
2. **Construire le Pattern E** (`patterns/scan.py`, moule DEC-021) → brief CLI. 5ᵉ test du
   contrat. Sources FS + HTTP.
3. **Documenter les usages D/A déjà délégables** (build-test, diagnose, migrations,
   lancer-script, doc-scan local) — pas de dev, juste des specs-types réutilisables.
4. **DEC `ssh-remote`** (extension sandbox→hôte distant) — gros morceau, dossier
   d'instruction QNAP déjà prêt ci-dessus. Débloque la File B. Pilote read-only qnap-01.

> Files A (1-3) et B (4) sont indépendantes : on peut livrer toute la valeur locale
> (E + usages D/A) sans attendre la décision `ssh-remote`, qui est le chantier d'archi
> majeur de la suite.
