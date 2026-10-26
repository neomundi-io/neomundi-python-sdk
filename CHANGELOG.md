# Journal des modifications

Format : [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).
Versionnement sémantique.

---

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
