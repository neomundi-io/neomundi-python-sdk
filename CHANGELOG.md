# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Versionnement sémantique.

---

## [2.1.0] — 2026-11-15 — INSTALL → TRACE → MEASURE → VERIFY

**Publiée sur PyPI.** `pip install --upgrade neomundi` apporte désormais
`trace()` et `verify()`, que la `2.0.0` ne portait pas. Le numéro a été choisi
par le responsable ; le verrou de publication a été **re-pointé** sur le tag
`sdk-v2.1.0` — tag exact, phrase de confirmation, environnement GitHub `pypi`
et Trusted Publishing OIDC restent en place, **aucune protection n'a été
retirée**.

Aucune signature existante n'a changé : la `2.0.0` reste installable et
`govern()`, `stream()`, `GovernResult` et `StreamResult` sont compatibles.

### Ajouté

- `client.trace()` et `TraceRecord` (`neomundi.trace`) : chronomètre local
  autour de l'appel applicatif, identifiant de corrélation, soumission
  explicite. **Aucune route de traçage n'existe sur l'API** — refermer une
  trace émet `POST /v1/govern`. `token_count` reste exigé de l'appelant ;
  sans lui, rien n'est envoyé. `TraceRecord` ne porte ni prompt ni réponse,
  seulement leurs longueurs.
- `TraceRecord.from_stream()` : le seul chemin où l'enregistrement est
  confirmé par le serveur.
- `client.verify()` et `client.verify_audit_certificate()`
  (`neomundi.verification`) : les deux routes de vérification **publiques et
  non facturées**, avec un `valid` **tri-état** — `None` signifie « rien n'a
  été vérifié », jamais « invalide ».
- `verify_evidence_archive()` : adaptateur vers le vérificateur Evidence
  **indépendant** (`pip install neomundi-evidence-verify`). Les cinq codes de
  sortie sont republiés sans traduction ; un vérificateur absent lève au lieu
  de rendre un verdict ; aucune clé n'est transmise au sous-processus.
- deux gardes de compatibilité sur `GovernResult` : l'ordre des champs de
  contrat et la présence d'une valeur par défaut hors du noyau.
  ⚠ Elles **consignent** que les cinq champs de provenance fusionnés par les
  PR #18/#19 ont déplacé `raw`, `unknown_fields` et `parse_warnings` de
  l'index 28 à l'index 33 : une construction positionnelle à 29 arguments ou
  plus lirait un champ pour un autre. Aucun code du SDK ne construit
  `GovernResult` autrement que par mots-clés ; le déplacement est consigné,
  pas défait.
- `StreamResult.log_persisted`, `.log_write`, `.contract_version`,
  `.token_count_source`, `.token_count_scope`, `.token_count_unit`.
  `log_persisted` vaut `True` quand la clé est **absente** : le serveur ne
  l'émet que sur le chemin non nominal.
- `API_CONTRACT["wire_contracts"]` : les empreintes des deux schémas de fil
  **téléchargés depuis la production**, mesurées à chaque exécution de la
  suite — là où `scripts/check_live_wire_schemas.py` établit la même parité
  en ligne, sur commande explicite.
- `tests/fixtures/contracts/` : les deux schémas déployés, à l'octet. Un test
  échoue si un champ que le contrat déployé déclare **requis** redevient
  inconnu du SDK.
- `API_CONTRACT["rgc_verify_route"]` et `["audit_verify_route"]`.
- `examples/05_parcours_complet.py` : le parcours entier, hors ligne.
- `docs/AUDIT_INSTALL_TRACE_MEASURE_VERIFY.md` : l'audit, avec ses sources et
  ses **NON ÉTABLI**.

### Modifié

- README EN et FR entièrement restructurés sur les quatre étapes, avec pour
  chacune **réel / partiel / à construire**. Les faits établis par les PR #17
  à #19 — publication PyPI, licence Apache-2.0 du SDK, API hébergée
  propriétaire et facturée, parité des schémas — sont conservés.

### Inchangé, volontairement

- `token_count` et `latency_ms` restent requis : le contrat déployé les exige
  et la réponse déployée republie `token_count_source: "caller_declared"`.
- `verified_measurement_versions` reste `("3.3.0", "3.3.1")`. La production
  sert `3.5.0` ; l'y ajouter déclarerait une compatibilité non vérifiée.
- les verrous du flux de publication : seul le numéro de version et de tag a
  été re-pointé, de `2.0.0` vers `2.1.0`.

### Non fait

- aucune route backend ajoutée, aucun déploiement, aucune publication PyPI ;
- aucun lien attesté observation → archive Evidence : il n'existe pas encore,
  et ce SDK ne le fabrique pas.

## [2.0.0] — 2026-10-26 — paquet préparé, non publié sur PyPI

- Ajout de `stream()` et `govern_stream()` pour le proxy SSE, avec contexte,
  événements typés, résultat final distinct et absence de réessai automatique.
- Assemblage sans duplication et vérification des longueurs / octets / SHA-256.
- Erreurs HTTP et erreurs de flux distinguées ; interruptions, null et inconnus
  conservés explicitement ; diagnostics de clés expurgés et réponses bornées.
- REST conservé ; coût, latence et timeout numériques non finis refusés localement.
- Documentation, migration, audit, exemple hors ligne et CI actualisés.
- Aucun changement du backend, de sa version de mesure, de licence ou de production.

## Historique — compatibilité du 2026-10-22

> **Compatibilité du contrat REST `POST /v1/govern` avec la version de
> mesure `3.3.1` vérifiée par tests locaux et rejeu d'une capture de
> production. Appel direct du SDK contre la production non effectué.**

Aucun changement de comportement du client : le code de transport et de
parsing est inchangé.

### Ajouté

- `API_CONTRACT["verified_measurement_versions"] = ("3.3.0", "3.3.1")`.
  Clé **additive** : `measurement_version` continue de nommer le commit
  de dérivation. Les deux répondent à deux questions distinctes — *ce
  client peut-il lire la réponse* d'une part, *ces deux nombres
  peuvent-ils appartenir à une même série* d'autre part.
- `tests/fixtures/production_331/rest_complete_allow.json` — réponse
  **réellement émise par la production** le 2026-10-21 sous `3.3.1`,
  **assainie** : identifiants et identité des évaluateurs remplacés,
  structure, types, nullité et valeurs de mesure conservés. La charge
  d'origine ne porte aucun texte de prompt ni de réponse ; les champs
  remplacés sont énumérés dans `_fixture_redacted`.
- `tests/test_measurement_version_331.py` — 19 tests sur cette charge.

### Vérifié

| Preuve | Nature | Résultat |
|---|---|---|
Comparaison des sources `68d6057` → `aeff13c` *(commit déployé)* | inspection de code | **rien sous `app/models/`**, rien dans la route REST. Un seul fichier applicatif diffère — le chemin SSE — plus la chaîne de version |
Rejeu de la réponse de production `3.3.1` | rejeu d'une capture de production | **0 `parse_warnings`, 0 champ racine inconnu**, aller-retour exact, alias concordants, couverture re-dérivable |
`GET /v1/health` de la production, 2026-10-22 | appel réel, non authentifié, hors quota | `200`, build `3.0.0`, `environment: production`, **aucune version de mesure publiée** |

**Non vérifié, et c'est la seule pièce qui manque :** aucun appel émis
par ce SDK n'a jamais atteint un déploiement hébergé. Le créditentiel
nécessaire n'était pas accessible à la session de vérification, et
`POST /v1/govern` crée une observation et débite un quota.

### Modifié

- **BL-002** — une classe de défauts est corrigée par `3.3.1` : la
  décision SSE ne lit plus que les points de trajectoire mesurés. Le
  résidu — `series`, `profile` et `total_variation` toujours fonction du
  découpage — reste ouvert, et un test du backend exige qu'il reste
  visible. **SL-001 n'est donc pas levée.**
- **BL-001** et **BL-003** — relues contre `aeff13c` : les fichiers
  concernés sont **identiques octet pour octet** entre les deux commits.
  Elles restent ouvertes, **par identité de source, non par présomption
  tirée du numéro de version**.
- `README.md`, `KNOWN_LIMITATIONS.md`, `PILOT_INTEGRATION_GUIDE.md`,
  `docs/CONTRAT_API.md`, `docs/LIMITES.md` — mis en accord avec ce qui
  précède, et distinction des quatre numéros de version *(build
  applicatif, version de mesure, normaliseur, schéma RGC)*.

---

## [0.1.0] — 2026-10-17

Première version. **Non publiée.** Prototype validé localement sur
transport simulé.

### Contrat de référence

| | |
|---|---|
commit backend | `68d6057cf620e430e6488da3cfcec9c471c75ed6` |
version de mesure | `3.3.0` |
version du normaliseur | `1.0.0` |
route couverte | `POST /v1/govern` |
OpenAPI figé | **non** — modèles dérivés de la lecture de `responses.py` / `requests.py` |

### Ajouté

- `NeoMundiClient` synchrone : `POST /v1/govern`, authentification
  `X-API-Key`, timeouts granulaires, gestionnaire de contexte.
- Validation du **format** de la clé et des paramètres **avant** tout
  appel réseau — une requête invalide ne consomme ni appel ni quota.
- `GovernResult` et 10 blocs typés en `dataclasses` immuables, dérivés de
  `responses.py` : 17 champs racine + `governance`, `metrics`, `baseline`,
  `audit` (requis), `quality`, `runtime`, `measurement`, `density`, `esi`,
  `rag_grounding` (optionnels).
- Parsing **non coercitif** : une chaîne `"0.5"` n'est jamais convertie en
  `0.5`. Le champ typé vaut `None`, la valeur brute reste dans `raw`, et
  un `ParseWarning` est consigné. Un booléen n'est jamais lu comme un
  nombre.
- `MeasurementState` à quatre valeurs, dont `NOT_ATTEMPTED_OR_GATED`
  **délibérément ambigu** : le serveur ne distingue pas « jamais lancé »
  de « masqué par le palier » sur le fil, et le SDK ne l'invente pas.
- Accesseurs de traçabilité : `is_measured()`, `unmeasured_reason()`,
  `measurement_state()`, `evaluator_of()`, `aggregates_publishable`,
  `missing_required_signals`, `measurement_incomplete`.
- Lecture sûre : `require()` (lève en nommant la cause),
  `format_score()` (ne lève jamais), `get()`, `field_present()`.
- Conservation de la charge brute intégrale (`raw`), des clés racine
  inconnues (`unknown_fields`) et des écarts de type (`parse_warnings`) —
  un champ ajouté au backend ne casse pas une intégration.
- Hiérarchie de 14 exceptions, avec préservation du corps serveur brut,
  des en-têtes, et récupération de `request_id` depuis `X-Request-ID`
  quand le corps ne le porte pas (cas du 413).
- `RetryPolicy` explicite, **désactivée par défaut**.
- Marqueur PEP 561 (`py.typed`).
- 206 tests, aucun accès réseau. Trois exemples exécutables sur serveur
  simulé, exécutés par la suite.
- `docs/CONTRAT_API.md` (relevé du contrat champ par champ) et
  `docs/LIMITES.md` (limites méthodologiques héritées).

### Décisions de conception

- **Aucune valeur par défaut numérique.** Pas un seul `or 0.0`, pas un
  seul `get(k, 0)` dans `src/`. Vérifié mécaniquement par
  `test_contract_drift.py::test_aucune_valeur_par_defaut_numerique_dans_les_sources`,
  lui-même vérifié par un test qui prouve que le garde-fou a des dents.
- **Aucun seuil, aucun verdict dérivé.** Pas de `is_safe()`, pas de
  niveau de qualité. Vérifié par analyse AST des sources.
- **Aucun réessai automatique.** `POST /v1/govern` crée une observation,
  débite un quota, écrit une ligne de métrologie et écrase la référence
  `delta_g` du compte. Aucun en-tête d'idempotence n'existe sur cette
  route. Un timeout n'est **jamais** réessayé, même avec une politique
  active.
- **`pydantic` écarté.** Sa coercition (`"0.5"` → `0.5`) masquerait une
  dérive de contrat que ce SDK doit rendre visible. `httpx` est la seule
  dépendance de production.
- **`respx` écarté.** `httpx.MockTransport` suffit, ce qui garde la suite
  exécutable sans installation supplémentaire.
- **Aucun raccourci sur un champ homonyme.** `quality.stability_score` et
  `metrics.stability_score` restent deux attributs distincts : choisir un
  des deux sens serait trancher une ambiguïté du contrat.

### Divergence backend signalée

- **`baseline.delta_E`** : la description du champ annonce
  `observed_energy - reference_energy` ; l'implémentation calcule
  `reference − observed`, soit l'opposé. Découvert pendant cette mission,
  **non recensé par l'audit du 2026-10-17**. Le SDK expose la valeur
  brute et ne recalcule rien. **Arbitrage backend requis.**

### Hors périmètre de cette version

Streaming SSE, client asynchrone, clients JS/TS, fonctions RGC, relecture
d'observations, exports, séries longitudinales, règles métier.

Le **streaming SSE est bloqué**, non par manque de contrat, mais parce que
la décision qu'il publie n'est pas invariante au découpage du flux par le
fournisseur : un client SSE transporterait fidèlement un verdict non
reproductible.

### Non vérifié

- Aucun appel contre un serveur NeoMundi réel.
- Les fixtures sont **construites depuis la lecture du code**, non
  capturées depuis un serveur : un écart entre ce que `responses.py`
  déclare et ce que le serveur déployé émet resterait invisible.
- Aucune publication sur PyPI, aucun envoi GitHub.
