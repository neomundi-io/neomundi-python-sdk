> **Document historique — SDK 0.1, 17 octobre 2026.** Ce plan est conservé pour sa traçabilité ; il ne décrit pas le périmètre actuel. Pour le SDK 2 REST/SSE, lire [l’accueil](README_FR.md) et [les vérifications V2](docs/VERIFICATION_V2.md).

# PLAN D'IMPLÉMENTATION — SDK Python NeoMundi v0.1

**Mission 02 — Phase A**
Date : 2026-10-17
Backend de référence : commit `68d6057cf620e430e6488da3cfcec9c471c75ed6`
Version de mesure du backend : `3.3.0` · Version du normaliseur : `1.0.0`
Dépôt API : **lecture seule, non modifié**

---

## 0. Vérifications faites avant d'écrire ce plan

Conformément à la consigne (« ne suppose pas que les documents d'audit sont infaillibles »), les contrats ont été relus **dans le code**, et non repris de l'audit.

| Vérifié | Fichier | Résultat |
|---|---|---|
Modèle de réponse complet, champ par champ | `govern-v3/app/models/responses.py` (1 182 l.) | 9 blocs + 17 champs racine ; relevé exhaustif en §3 |
Modèle de requête | `govern-v3/app/models/requests.py` | `GovernRequest` + `RawMetrics` + `DocumentInput` |
Route `POST /v1/govern` | `govern-v3/app/api/v1/governance.py:104-726` | codes d'erreur déclarés, ordre des traitements, filtre de palier appliqué en dernier |
Authentification | `govern-v3/app/auth/api_key.py:586-631` | en-tête `X-API-Key`, 3 préfixes, 401 / 429 + en-têtes |
Forme des erreurs | `govern-v3/app/main.py:189-200, 340-395` | `ErrorResponse` à 4 clés ; **413 à 2 clés** |
Politique des champs supplémentaires | `responses.py` — aucun `model_config.extra` | défaut Pydantic v2 = `ignore` côté serveur |
OpenAPI | `govern-v3/app/config.py:768-770` | `docs_enabled = not is_production or DEBUG` → **absent en production, aucun fichier figé dans le dépôt** |
Consommateur de référence | `govern-v3/rgc_consumer_demo/` | gabarit retenu : indépendance, mode hors-ligne, hors-périmètre explicite |
Client e2e existant | `govern-v3/tests/e2e_smoke.py` *(dépôt backend)* | confirme l'usage réel de l'en-tête et de la forme du corps |
Environnement local | — | Python 3.12.10, `httpx` 0.28.1, `pytest` 9.1.1 présents ; **`respx` absent** |

### 0.1 Une divergence NON recensée par l'audit, découverte ici

**`baseline.delta_E` : le signe documenté est l'inverse du signe calculé.**

| | |
|---|---|
Description du champ | « `observed_energy - reference_energy` » — `responses.py:504-511` |
Implémentation | `delta_e = effective_ref - norm.energy_proxy` — `governance.py:1552` |

C'est-à-dire `reference − observed`, soit **l'opposé** de ce que la description annonce. Un SDK qui exposerait « l'écart à la référence » en se fiant à la description inverserait le signe.

**Décision pour le SDK** : `delta_E` est exposé **tel quel, sans aucune interprétation**, et le champ porte un avertissement dans sa docstring. Le SDK ne recalcule rien et ne corrige pas le backend (règle absolue §3 de la mission). Ajouté aux ambiguïtés ouvertes (§11, A-07).

---

## 1. Architecture du SDK

### 1.1 Principe directeur

> **Le SDK transporte et expose. Il n'interprète pas.**

Trois conséquences, qui gouvernent chaque décision ci-dessous :

1. **Aucun seuil** n'est embarqué. Pas de `is_safe()`, pas de `is_good()`, pas de `quality_level()`. Les seuils sont des choix de configuration serveur (`governance.py` les lit de `settings`), ils ne sont pas calibrés publiquement (audit 03 §6, risque 3), et un seuil côté client serait une invention.
2. **Aucune valeur par défaut numérique.** `null` reste `None`. Jamais `or 0.0`, jamais `get(x, 0)`. C'est le piège que le backend a mis six chantiers à fermer ; le réintroduire côté client annulerait ce travail.
3. **Aucune conversion ambiguë.** Quand la sémantique d'un champ est douteuse (`delta_E`, les deux `stability_score`, les compteurs en « tokens »), le SDK expose la valeur brute **sous son chemin complet** et documente l'ambiguïté.

### 1.2 Arborescence

```
neomundi-python-sdk/
├── pyproject.toml              packaging, dépendances, config pytest
├── README.md                   doc développeur (Phase D)
├── CHANGELOG.md
├── LICENSE_NOTICE.md
├── PLAN_IMPLEMENTATION.md      ce document
├── RAPPORT_VALIDATION.md       Phase F
├── src/neomundi/
│   ├── __init__.py             surface publique + __version__ + API_CONTRACT
│   ├── client.py               NeoMundiClient (sync) + transport HTTP
│   ├── models.py               dataclasses typées + parsing non coercitif
│   ├── errors.py               hiérarchie d'exceptions
│   ├── _retry.py               politique de retry (désactivée par défaut)
│   └── py.typed                marqueur PEP 561
├── tests/
│   ├── conftest.py             fabrique de transports simulés
│   ├── fixtures/               charges JSON (origine documentée)
│   ├── test_client.py
│   ├── test_models.py
│   ├── test_errors.py
│   ├── test_retry.py
│   ├── test_no_secret_leak.py
│   └── test_contract_drift.py
├── examples/
│   ├── 01_premiere_mesure.py           serveur simulé
│   ├── 02_mesure_partielle.py          serveur simulé
│   ├── 03_gestion_erreurs.py           serveur simulé
│   └── 90_cle_reelle.py.disabled       nécessite une vraie clé — NON exécutable
└── docs/
    ├── CONTRAT_API.md          le contrat relevé dans le code, champ par champ
    └── LIMITES.md              limites méthodologiques héritées
```

### 1.3 Pourquoi cette structure

- **`src/` layout** : empêche les tests de passer accidentellement contre le code source non installé. Standard pour un paquet destiné à la publication.
- **`_retry.py` préfixé** : module privé, non exporté. La politique de retry n'est pas une API publique à la v0.1.
- **`fixtures/` séparé** : chaque charge porte son origine (relevée du code, ou synthétique), exigence de la Phase C §7.
- **`90_cle_reelle.py.disabled`** : extension volontairement non exécutable, pour qu'aucun lancement accidentel ne contacte un vrai serveur.

### 1.4 Modèle d'exécution

**Synchrone uniquement à la v0.1.** `httpx.Client` + `httpx.Transport`. Un client asynchrone est une surface API supplémentaire à maintenir ; il n'est pas nécessaire pour `POST /v1/govern`, qui est un aller-retour unique. L'ajout d'un `AsyncNeoMundiClient` est prévu comme évolution (§1.5) sans sur-ingénierie dès maintenant.

**Gestion des ressources** : `NeoMundiClient` est un gestionnaire de contexte (`__enter__` / `__exit__`), expose `close()`, et ferme le `httpx.Client` qu'il a créé. S'il reçoit un client httpx fourni par l'appelant (injection pour les tests), **il ne le ferme pas** — il ne possède pas ce qu'il n'a pas créé.

### 1.5 Points d'extension prévus, non implémentés

Trois seulement, choisis parce qu'ils évitent une rupture d'API plus tard :

| Extension | Préparation minimale |
|---|---|
Client asynchrone | la logique de construction de requête et de parsing est **séparée** du transport (`_build_request()`, `_parse_response()` sont des fonctions pures) |
Streaming SSE | `client.py` n'impose rien sur la forme des réponses ; `models.py` n'a aucune dépendance au transport |
Autres routes (`GET /v1/govern/{id}`) | `_request()` est générique sur la méthode et le chemin |

Aucune abstraction supplémentaire. Pas d'interface, pas de registre, pas de *plugin system*.

---

## 2. Périmètre exact de la v0.1

### 2.1 Dans le périmètre

| Capacité | Détail |
|---|---|
`POST /v1/govern` | construction de la requête, envoi, parsing de la réponse |
Authentification | en-tête `X-API-Key`, validation du **format** côté client (3 préfixes) |
Modèles typés | `GovernResult` + 9 blocs, tous champs `Optional` là où le serveur peut répondre `null` |
Erreurs typées | 9 classes, détails serveur préservés |
Timeouts | connexion / lecture / écriture / pool, configurables |
`Retry-After` | exposé sur `RateLimitError`, **jamais appliqué automatiquement** |
Accesseurs de traçabilité | `is_measured()`, `unmeasured_reason()`, `evaluator_of()`, `aggregates_publishable` |
Charge brute | `result.raw` conserve le JSON intégral, y compris les champs inconnus |
Fermeture des ressources | gestionnaire de contexte + `close()` |
Version de contrat | `neomundi.API_CONTRACT` déclare le commit et la version de mesure visés |

### 2.2 Hors périmètre (Mission §10), et pourquoi

| Exclu | Raison |
|---|---|
Streaming SSE | **mission séparée**, après clarification de l'invariance au découpage. L'audit 03 R-01 établit que la **décision** dépend du découpage du flux : un SDK ne peut pas corriger cela, il ne peut que le propager. Livrer un client SSE maintenant serait livrer un résultat non reproductible. |
Clients JS / TS | nécessite l'OpenAPI figé (§11 B-01) |
Fonctions RGC avancées | `rgc_consumer_demo` existe déjà et est testé ; le porter est du packaging, pas du développement |
Tableaux de bord | hors périmètre d'une bibliothèque |
Séries longitudinales | exigeraient d'embarquer les conditions de comparabilité (audit 02 §9) — **le SDK ne doit pas décider** qu'une série est valide |
Règles métier, seuils | invention interdite |
Orchestration d'agents | hors périmètre |
Modifications backend | règle absolue |

---

## 3. Contrats backend utilisés

### 3.1 Requête — `POST /v1/govern`

Relevé de `models/requests.py`.

```
GovernRequest
├── source_type    str   = "llm"        (llm | iot | financial)
├── raw_metrics    RawMetrics           REQUIS
│   ├── token_count      int    ≥0      REQUIS
│   ├── latency_ms       float  ≥0      REQUIS
│   ├── cost             float  ≥0      = 0.0    unité du caller, SANS devise
│   ├── semantic_risk    float  [0,1]   = 0.0
│   ├── prompt_length    int    ≥0      = 0      en CARACTÈRES
│   ├── response_length  int    ≥0      = 0      en CARACTÈRES
│   └── model_name       str            = "unknown"
├── mode           str   = "OBS"        seule valeur
├── llm_response   str?  ≤50000         déclenche les contrôles serveur
├── llm_prompt     str?  ≤10000
├── rag_context    list[str]? ≤50       héritage
├── documents      list[DocumentInput]? ≤10   TIER_02+
└── metadata       dict  = {}
```

**Trois pièges d'unité, déclarés par le backend et propagés tels quels :**
- `prompt_length` est documenté **en caractères** et lu comme `tokens_in` par la route → `volumetric_density` est un ratio tokens/caractères, ce que le champ `volumetric_density_basis` déclare ;
- `cost` est **sans devise** : seul le ratio contre un plafond compte. Le SDK ne convertit rien et le dit dans la docstring ;
- `response_length` **entre dans un calcul** (`> 2000` → `is_long_form_safe`).

**Décision SDK** : la signature de `govern()` reprend ces noms **à l'identique** et documente l'unité de chacun. Aucun renommage — introduire un troisième vocabulaire (après celui du serveur et celui du glossaire) serait la pire option.

### 3.2 Réponse — relevé exhaustif

**Racine** (`responses.py:838-1084`) — 17 champs + 9 blocs :

| Champ | Type | Nullable |
|---|---|---|
`request_id` | `str` | non (requis) |
`timestamp` | `datetime` | non |
`system_id` | `str` | non |
`mode` | `str` | non |
`g_score` | `float?` | **oui** |
`g_final` | `float?` | **oui** |
`v_score` | `float?` | **oui** |
`delta_g` | `float?` | **oui** |
`checks_emitted` | `int?` | oui |
`trajectory_points` | `int?` | oui (toujours `null` en REST) |
`measured_signals` | `list[str]?` | oui |
`measurement` | `MeasurementBlock?` | oui |
`unmeasured_signals` | `dict[str,str]?` | oui |
`processing_time_ms` | `float?` | oui |
`latency_ms` | `float?` | oui |
`model` | `str?` | oui |
`evaluators` | `dict[str, dict[str, str\|int\|float\|None]]?` | oui |
`provider` | `str?` | oui (toujours `null` en REST) |

**Blocs** — et la distinction *requis* / *optionnel* compte pour le parsing :

| Bloc | Présence | Note |
|---|---|---|
`governance` | **REQUIS** | `decision`, `decision_basis?`, `confidence`, `reasons[]` |
`metrics` | **REQUIS** | 5 champs, **tous nullables** |
`baseline` | **REQUIS** | 6 champs, tous nullables |
`audit` | **REQUIS** | `measurement_version`, `normalizer_version`, `trace_id` — **non nullables** |
`quality` | optionnel | absent pour un palier sans bloc qualité |
`runtime` | optionnel | `null` pour TRIAL / TIER_01 |
`density` | optionnel | TIER_02+ |
`esi` | optionnel | TIER_02+ ; ses 9 champs sont **requis-mais-nullables** |
`rag_grounding` | optionnel | selon les juges d'ancrage |

**Décision SDK** : les quatre blocs requis sont typés non-`Optional` dans `GovernResult` et leur absence lève `InvalidResponseError` — c'est une violation de contrat, pas une donnée manquante. Les cinq optionnels sont `Optional[...]` et valent `None` quand absents.

### 3.3 Codes d'erreur réellement émis

Relevé de `governance.py:120-146` et `main.py`.

| Code | Corps | Origine |
|---|---|---|
401 | 4 clés | clé invalide / format invalide / révoquée |
402 | 4 clés | **3 causes indistinguables** : quota TRIAL épuisé, solde insuffisant, plafond de budget de clé |
413 | **2 clés** (`error`, `detail`) — ni `request_id` ni `timestamp` | middleware de taille **ou** nginx |
422 | 4 clés, `detail` est une **liste** d'objets `{field, message, type}` | validation Pydantic |
429 | 4 clés + en-têtes `Retry-After`, `X-RateLimit-*` | limite par minute |
500 | 4 clés | erreur non gérée |
503 | 4 clés | service indisponible |

**Décision SDK** : le parsing d'erreur **ne suppose jamais** 4 clés. Il lit ce qui est présent et conserve le corps brut dans `exc.body`.

### 3.4 Politique des champs supplémentaires

`responses.py` ne déclare **aucun** `model_config.extra` → le serveur ignore les champs d'entrée inconnus et sérialise exactement ses champs déclarés.

**Décision SDK** : forward-compatibilité **explicite**. Tout champ non reconnu est conservé dans `result.raw` (charge intégrale) et dans `result.unknown_fields` (clés racine inconnues seulement). Le SDK **ne lève jamais** sur un champ inconnu : un backend qui ajoute un champ ne doit pas casser les intégrations.

---

## 4. Dépendances Python

### 4.1 Choix retenus

| Dépendance | Portée | Version | Justification |
|---|---|---|---|
`httpx` | **runtime, seule** | `>=0.24,<1.0` | déjà la bibliothèque HTTP du backend ; `MockTransport` intégré permet des tests sans dépendance supplémentaire ; timeouts granulaires |
`pytest` | dev | `>=8.0` | — |

**Python requis : `>=3.9`.** `dataclasses` et `typing.Optional` suffisent ; aucune syntaxe 3.10+ (`X | Y` en annotation runtime) n'est utilisée.

### 4.2 Deux dépendances délibérément écartées

**`pydantic` — écarté.** Motifs :

1. **La coercition masquerait une dérive du backend.** Pydantic convertirait `"0.5"` en `0.5`. Si le serveur se mettait à renvoyer des chaînes, le SDK le dissimulerait. Le backend lui-même a jugé ce risque assez sérieux pour écrire `_has_numeric()` (`hallucination_detector.py:712-735`), qui **refuse** un booléen et accepte une chaîne numérique de façon explicite. Le SDK adopte la même rigueur : il **vérifie sans convertir**.
2. **Validation stricte contre forward-compatibilité.** Pydantic rejette ou ignore ; il faudrait `extra="allow"` partout, ce qui donne des objets au contenu imprévisible.
3. **Coût d'installation** : pydantic v2 embarque une extension compilée. Pour une bibliothèque cliente dont le rôle est de transporter un JSON, c'est disproportionné.

**Retenu à la place** : `dataclasses` de la bibliothèque standard + fonctions de parsing explicites, non coercitives, qui conservent la valeur brute si elle n'est pas du type attendu.

**`respx` — écarté.** Le backend l'utilise pour ses tests, mais `httpx.MockTransport` (intégré à httpx) couvre le besoin. Une dépendance de test en moins, et **le paquet est absent de l'environnement local** : s'en passer rend la suite exécutable immédiatement, sans installation réseau. C'est exactement l'argument que le backend s'est appliqué à lui-même quand il a ajouté `respx` à `requirements.txt` : « une suite de garde qui ne peut pas être lancée n'est pas une garde ».

---

## 5. Modèles de données

### 5.1 Correspondance

Un `@dataclass(frozen=True)` par bloc, aux noms de champs **identiques** à ceux du serveur :

```
GovernResult        ← racine (17 champs + 9 blocs + raw + unknown_fields)
├── Governance      ← governance    (requis)
├── Metrics         ← metrics       (requis)
├── Baseline        ← baseline      (requis)
├── Audit           ← audit         (requis)
├── Quality         ← quality       (optionnel)   + list[SuspectPhrase]?
├── Runtime         ← runtime       (optionnel)
├── Measurement     ← measurement   (optionnel)
├── Density         ← density       (optionnel)
├── Esi             ← esi           (optionnel)
└── RagGrounding    ← rag_grounding (optionnel)   + Citation, UngroundedSnippet
```

`frozen=True` : un résultat de mesure est une observation. Il ne se modifie pas.

### 5.2 Règles de parsing

| Entrée JSON | Sortie SDK |
|---|---|
clé absente | `None` (pour un champ nullable) · `InvalidResponseError` (pour un bloc requis) |
`null` | `None` |
`0.0` | `0.0` — **une mesure**, jamais confondue avec `None` |
nombre valide | `float` / `int` |
chaîne numérique `"0.5"` | **conservée en `str`** dans `raw`, le champ typé vaut `None`, et un avertissement est enregistré dans `result.parse_warnings` |
booléen là où un nombre est attendu | idem — `True` n'est **pas** `1.0` |
type inattendu | idem |
clé racine inconnue | conservée dans `raw` **et** listée dans `unknown_fields` |

**`parse_warnings`** est la pièce centrale de cette politique : le SDK ne dissimule pas une dérive de contrat et ne lève pas non plus pour un champ périphérique. Il expose ce qu'il n'a pas pu lire.

### 5.3 Les cinq distinctions que le SDK doit préserver

Exigence explicite de la mission (§6, « Typage »). Mise en œuvre :

| Distinction | Comment le SDK la rend lisible |
|---|---|
**Score nul** (`0.0`) | la valeur est `0.0` ; `is_measured("x")` → `True` |
**Signal non mesuré** | la valeur est `None` ; `is_measured("x")` → `False` ; `unmeasured_reason("x")` → la cause |
**Signal non applicable** | `trajectory_points` et `provider` sont `None` par construction en REST ; documenté champ par champ |
**Signal masqué par un palier** | la valeur est `None`, le signal **n'apparaît pas** dans `measured_signals` et **n'a pas de cause** dans `unmeasured_signals` → `measurement_state("x")` renvoie `GATED_OR_NOT_ATTEMPTED` |
**Champ absent** | `field_present("chemin")` interroge `raw`, pas l'objet typé |

**`measurement_state(signal)`** renvoie une énumération à quatre valeurs, dérivée **uniquement** de ce que le serveur publie :

| Valeur | Déduite de |
|---|---|
`MEASURED` | le signal est dans `measured_signals` |
`NOT_MEASURED` | le signal est dans `unmeasured_signals` (la cause est disponible) |
`NOT_ATTEMPTED_OR_GATED` | dans aucune des deux listes — **le SDK ne tranche pas** entre « jamais lancé » et « masqué par le palier », parce que **le serveur ne le distingue pas sur le fil** |
`UNKNOWN` | les deux listes sont absentes (ligne ancienne) |

La troisième valeur est délibérément ambiguë **parce que l'ambiguïté est dans le contrat**, et non dans le SDK. L'inventer serait une faute (audit 02 §6.1 : un `coherence_score: 1.0` jamais lancé n'apparaît dans aucune des deux listes).

### 5.4 Champs homonymes — chemin complet conservé

Aucun aplatissement. `result.quality.stability_score` et `result.metrics.stability_score` restent **deux attributs distincts**, et leurs docstrings portent l'avertissement :

```
quality.stability_score  : G / 0.60        → 1 = stable
metrics.stability_score  : 1 − G / 0.60    → 0 = stable   (ÉCHELLE INVERSÉE)
```

Idem pour `esi.q_value` vs `baseline.esi_q`, et `quality.information_density` vs `density.informational_density`.

**Aucun raccourci `result.stability` n'est fourni** : il faudrait choisir un des deux sens, donc trancher une ambiguïté du contrat. Les alias racine `g_score` / `g_final` / `v_score` sont exposés parce que le serveur les déclare lui-même comme « même valeur, jamais différente » (`responses.py:862-866`), et un test vérifie cette cohérence sur les fixtures.

---

## 6. Politique de gestion des erreurs

### 6.1 Hiérarchie

```
NeoMundiError                      (base, jamais levée directement)
├── ConfigurationError             clé/URL/timeout invalides — AVANT tout réseau
├── TransportError                 pas de réponse HTTP obtenue
│   ├── TimeoutError
│   └── NetworkError
├── InvalidResponseError           réponse obtenue, inexploitable (JSON ou contrat)
└── APIError                       le serveur a répondu un statut d'erreur
    ├── AuthenticationError        401
    ├── PaymentRequiredError       402
    ├── PayloadTooLargeError       413
    ├── ValidationError            422
    ├── RateLimitError             429   (+ retry_after)
    └── ServerError                500 / 503 / autres 5xx
```

### 6.2 Ce que chaque `APIError` porte

| Attribut | Source | Si absent |
|---|---|---|
`status_code` | statut HTTP | — |
`error_code` | clé `error` du corps | `None` |
`detail` | clé `detail` | `None` |
`request_id` | clé `request_id`, **sinon en-tête `X-Request-ID`** | `None` |
`server_timestamp` | clé `timestamp`, **en chaîne brute** | `None` |
`body` | **corps brut intégral** (dict, ou texte si non-JSON) | — |
`headers` | en-têtes de réponse | — |

**Deux points de robustesse exigés par le relevé §3.3 :**

- le `413` n'a que 2 clés. Le parsing n'exige rien et remplit ce qu'il trouve. `request_id` est alors récupéré de l'en-tête `X-Request-ID`, que le middleware pose sur **toute** réponse (`main.py:247`) — information réelle et utile que le corps ne porte pas ;
- le `422` a un `detail` qui est une **liste d'objets**. `ValidationError.field_errors` expose cette liste normalisée, et `detail` conserve la valeur brute.

### 6.3 `timestamp` serveur : chaîne, pas `datetime`

Le serveur produit `datetime.utcnow().isoformat()` — **sans fuseau**. Le convertir en `datetime` obligerait à supposer UTC. Le SDK conserve la chaîne dans `server_timestamp` et fournit `as_datetime()` qui renvoie `None` si l'analyse échoue. Même traitement pour `GovernResult.timestamp` : `timestamp_raw` (str) + `timestamp` (`datetime?`).

### 6.4 Aucune clé dans les messages

Aucun message d'exception, aucun `repr`, aucun journal ne contient la clé API. `NeoMundiClient.__repr__` masque la clé (`ct_live_***`). Vérifié par `test_no_secret_leak.py` (Phase C §14).

---

## 7. Stratégie de gestion des `null`

C'est la raison d'être du SDK (audit 07 B-03). Quatre règles.

### R1 — `None` n'est jamais remplacé

Aucun `or 0.0`, aucun `get(k, 0)`, aucune valeur par défaut numérique dans tout `src/`. Vérifié par un test de grep sur les sources (`test_contract_drift.py`).

### R2 — `None` et `0.0` sont deux états distincts

Un `0.0` est une mesure. Les accesseurs ne les confondent jamais :

```python
r.quality.factual_hallucination_score   # 0.0  → mesuré, rien trouvé
                                        # None → non mesuré / masqué
r.measurement_state("factual_hallucination_score")
r.unmeasured_reason("factual_hallucination_score")
```

### R3 — Un agrégat `null` est un **fait déclaré**, pas une lacune de sérialisation

```python
if r.aggregates_publishable is False:
    r.missing_required_signals   # ['hallucination_score']
    r.governance.decision        # 'FLAG'
    r.governance.decision_basis  # 'incomplete_measurement'
```

`aggregates_publishable` peut valoir `None` pour une ligne ancienne — **le SDK ne le remplace pas par `True`**, pour la raison exacte que `responses.py:225-240` donne : un `True` par défaut ferait prétendre à toute observation antérieure que ses agrégats étaient complets.

### R4 — Un garde-fou explicite contre l'erreur la plus probable de l'intégrateur

Le défaut typique est `f"{r.g_score:.2f}"` — c'est précisément ce que fait l'exemple officiel de `GUIDE_CLIENT.md`, et il lève `TypeError` dès qu'un agrégat est retenu (audit 04 §1.3).

Le SDK fournit :

```python
r.format_score("g_score", nd=2, when_none="non mesuré")  # -> "0.46" | "non mesuré"
r.require("g_score")   # -> float, ou lève AggregateWithheldError avec la cause
```

`require()` lève une exception **nommée et explicative** plutôt qu'un `TypeError` opaque. C'est la seule « aide » que le SDK se permet, et elle n'invente aucune valeur.

---

## 8. Politique de retry et de timeout

### 8.1 Retry — **désactivé par défaut**, et c'est une décision de fond

`POST /v1/govern` **n'est pas idempotent** :

| Effet d'une répétition | Preuve dans le code |
|---|---|
une **nouvelle observation** est créée | `request_id = str(uuid.uuid4())` à chaque appel — `runtime_engine.py:162` |
le **quota ou le portefeuille est débité** | `enforce_trial_quota(client)` avant le travail — `governance.py:172` |
une **ligne de métrologie** est écrite | `usage_events` — `governance.py:586-626` |
la **référence ΔG du compte est écrasée** | `govern:last_g:{client_id}` dans Redis — `governance.py:2088` |

Aucun en-tête d'idempotence n'existe sur cette route (vérifié : aucune occurrence de `Idempotency-Key` dans `govern-v3/`).

**Donc** : `max_retries=0` par défaut. Un retry automatique produirait une seconde mesure facturée, et faussificerait le `delta_g` de l'appel suivant.

### 8.2 Ce que fait le SDK à la place

| Situation | Comportement |
|---|---|
429 | lève `RateLimitError` avec `retry_after` lu de l'en-tête `Retry-After` et les trois `X-RateLimit-*`. **L'appelant décide.** |
timeout / erreur réseau | lève `TimeoutError` / `NetworkError`. **Aucun retry** : une requête dont la réponse est perdue a peut-être été exécutée et facturée côté serveur. |
5xx | lève `ServerError`. Aucun retry automatique. |

### 8.3 L'option explicite, pour qui l'assume

```python
NeoMundiClient(..., retry=RetryPolicy(max_attempts=3, on=(429,503)))
```

Trois garde-fous :
- `RetryPolicy` doit être **construite explicitement** — pas de `retry=True`, pas d'entier magique ;
- son docstring énonce les quatre effets de bord ci-dessus ;
- **un timeout n'est jamais réessayé**, même avec une politique active : c'est le seul cas où le SDK ne peut pas savoir si la requête a été exécutée. Un `503` renvoyé par le serveur, lui, prouve qu'elle n'a pas abouti.

### 8.4 Timeouts

`httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)` par défaut.

`read=60.0` est dérivé du backend, non choisi arbitrairement : `HALLUCINATION_TIMEOUT` vaut 30 s (plafonné à 60 s par `config.py:273`), les trois évaluateurs tournent **en parallèle** sur un Ollama CPU, et `/v1/govern` les attend tous. Un `read` plus court échouerait sur un backend nominalement lent. `timeout=<float>` reste accepté et s'applique aux quatre phases.

---

## 9. Stratégie de tests

### 9.1 Principe

**Aucun test ne touche le réseau.** Tous passent par `httpx.MockTransport`, injecté dans le `httpx.Client` du SDK. Aucune vraie clé : les fixtures utilisent `ct_test_0000000000000000000000000000`.

### 9.2 Origine des fixtures — documentée, exigence Phase C §7

| Fixture | Origine |
|---|---|
`full_measurement.json` | **construite depuis le code** : structure de `responses.py`, valeurs cohérentes avec les formules de `score_engine.py` et `g_final.py` (vérifiées à la main — audit 02 §12) |
`partial_measurement.json` | **construite depuis le code** : cas « juge non mesuré » tel que `governance.py:1360-1364` le produit (agrégats `null`, `FLAG`, `incomplete_measurement`) |
`gated_tier01.json` | **construite depuis le code** : sortie de `_apply_tier_filter` pour `tier_01` (`governance.py:1978-2050`) |
`no_check_attempted.json` | **construite depuis le code** : cas sans `llm_response` |
`unknown_field.json` | **synthétique** — champ inventé, pour la forward-compatibilité |
`drifted_types.json` | **synthétique** — chaînes à la place de nombres, pour `parse_warnings` |
`errors/*.json` | **relevées de `ErrorResponse` et du middleware** ; le `413` reproduit la forme à 2 clés de `main.py:194-199` |

Chaque fichier porte un champ `"_fixture_origin"` qui dit lequel des deux il est. Un test vérifie que ce champ est présent partout.

### 9.3 Couverture des 15 points exigés

| # | Exigence | Test |
|---|---|---|
1 | Création du client | `test_client.py` |
2 | Authentification | `test_client.py` — l'en-tête `X-API-Key` est envoyé, le format est validé avant tout réseau |
3 | Requête REST valide | `test_client.py` — corps, chemin, méthode |
4 | Réponse entièrement mesurée | `test_models.py` |
5 | Réponse partiellement mesurée | `test_models.py` |
6 | Valeurs `null` | `test_models.py` — `None` préservé, jamais `0.0` |
7 | Signal non mesuré | `test_models.py` — `measurement_state`, `unmeasured_reason` |
8 | 401/402/413/422/429/500/503 | `test_errors.py` |
9 | Timeout | `test_errors.py` — transport qui lève `httpx.ReadTimeout` |
10 | Erreur réseau | `test_errors.py` — `httpx.ConnectError` |
11 | JSON invalide | `test_errors.py` — `InvalidResponseError` |
12 | Champs inconnus | `test_models.py` — conservés dans `raw` et `unknown_fields` |
13 | Fermeture des ressources | `test_client.py` — contexte, `close()`, non-fermeture d'un client injecté |
14 | Aucune clé journalisée | `test_no_secret_leak.py` — `repr`, messages d'exception, `caplog` |
15 | Aucun retry non autorisé | `test_retry.py` — compteur d'appels du transport |

### 9.4 Tests supplémentaires, non exigés mais utiles

| Test | Ce qu'il garde |
|---|---|
`test_contract_drift.py::test_no_numeric_default_in_sources` | grep sur `src/` : aucun `or 0.0`, aucun `get(..., 0)` — **la règle R1 est vérifiée mécaniquement** |
`test_contract_drift.py::test_declared_contract_matches_fixtures` | les champs des fixtures sont un sous-ensemble de ceux que les dataclasses déclarent |
`test_models.py::test_root_aliases_agree_with_blocks` | `g_score` == `quality.g_score`, `g_final` == `esi.g_final` — ce que le serveur promet |
`test_models.py::test_zero_and_none_are_distinguishable` | l'invariant central du produit |

### 9.5 Ce que les tests NE prouvent pas

À écrire dans le rapport : **un succès sur transport simulé ne valide pas le fonctionnement en production.** Les fixtures sont construites depuis la lecture du code, non capturées depuis un serveur. Un écart entre ce que `responses.py` déclare et ce que le serveur déployé émet resterait invisible.

---

## 10. Critères d'acceptation

| # | Critère | Mesure |
|---|---|---|
A1 | aucun import du backend | grep sur `src/` : aucun `app.`, aucun `govern` |
A2 | API de référence non modifiée | `git status` vide dans le dépôt API de référence |
A3 | documents d'audit non modifiés | horodatages inchangés |
A4 | le paquet se construit | `python -m build` ou `pip wheel` réussit |
A5 | installation en venv isolé | `pip install dist/*.whl` dans un venv neuf |
A6 | dépendances déclarées | `pyproject.toml` |
A7 | `POST /v1/govern` représenté | chemin, méthode, en-tête, corps vérifiés par test |
A8 | modèles conformes au contrat | les 9 blocs + 17 champs racine présents |
A9 | erreurs typées | 9 classes, 7 codes couverts |
A10 | `null` préservé | `test_zero_and_none_are_distinguishable` |
A11 | aucun faux résultat sur signal manquant | `test_models.py` sur `partial_measurement` |
A12 | aucun retry dangereux | `test_retry.py` |
A13 | tous les tests passent | sortie `pytest` |
A14 | exemples exécutés | les 3 exemples tournent sur serveur simulé |
A15 | tests non exécutés identifiés | section dédiée du rapport |
A16 | aucun secret réel | clés de test au format `ct_test_000…` |
A17 | limites documentées | `README.md` + `docs/LIMITES.md` |
A18 | version de contrat déclarée | `neomundi.API_CONTRACT` |
A19 | commit backend documenté | ce plan + `API_CONTRACT` + `README` |
A20 | incompatibilités recensées | §11 |

**A4 et A5 dépendent de l'accès à PyPI** pour résoudre `httpx` dans un venv neuf. Si l'accès réseau n'est pas disponible, ces deux critères seront déclarés **NON VÉRIFIÉS** dans le rapport, avec la commande exacte à rejouer — jamais déclarés satisfaits par défaut.

---

## 11. Limitations connues du SDK v0.1

| # | Limitation | Conséquence |
|---|---|---|
L1 | une seule route : `POST /v1/govern` | pas de relecture, pas de dashboard, pas d'exports |
L2 | synchrone uniquement | pas de client async |
L3 | pas de SSE | mission séparée |
L4 | pas de retry automatique | l'appelant gère 429 et 503 |
L5 | pas de pagination, pas de cache | hors périmètre |
L6 | fixtures **construites depuis le code**, non capturées d'un serveur | un écart code ↔ déploiement resterait invisible |
L7 | aucune interprétation des scores | voulu — voir §1.1 |
L8 | les blocs requis manquants lèvent | choix assumé : c'est une violation de contrat |
L9 | `timestamp` serveur sans fuseau | exposé en chaîne + conversion facultative |
L10 | pas de validation du schéma de réponse contre un OpenAPI | **impossible** : aucun OpenAPI figé n'existe (§12 B-01) |

---

## 12. Risques hérités du backend

Reportés tels quels de l'audit, **relus dans le code**. Le SDK ne les corrige pas (règle absolue) ; il les **expose** ou les **documente**.

| # | Risque hérité | Réf. audit | Traitement SDK |
|---|---|---|---|
B-01 | **Aucun OpenAPI figé**, désactivé en production | 07 B-01 | les modèles sont dérivés de `responses.py` **à un commit nommé** ; `API_CONTRACT` déclare ce commit ; L10 l'assume |
R-03 | **plages effectives écrasées** : hallucination maximale → `g_final = 0.86` | 02 §3.4, 03 R-03 | `docs/LIMITES.md` publie le tableau des valeurs ; **aucun seuil embarqué** |
R-09 | **`stability_score` présent 2× avec échelles inversées** | 03 R-09 | chemins complets conservés, docstrings d'avertissement, **aucun raccourci** |
A-07 | **`delta_E` : signe documenté inverse du signe calculé** (découvert dans cette mission) | — | valeur brute, docstring d'avertissement, aucun recalcul |
R-04 | `delta_g` publié alors que `g_score` est `null` ; `0.0` écrit comme référence | 03 R-04 | `delta_g` exposé brut ; le README avertit qu'il peut être incohérent avec un agrégat retenu |
R-05 | **palier non filtré** sur `GET`/dashboard/SSE | 03 R-05 | hors périmètre (une seule route) ; documenté |
R-06 | `check_config` / `esi_betas` ignorés en SSE | 03 R-06 | hors périmètre ; documenté |
R-07 | **la version ne couvre pas l'instrument** | 03 R-07 | `result.evaluators` expose `config_fingerprint` ; le README explique **comment** vérifier la stabilité de l'instrument entre deux séries |
R-01 | **la décision dépend du découpage SSE** | 03 R-01 | **raison d'être de l'exclusion du SSE** à la v0.1 |
— | `402` couvre 3 causes indistinguables | 07 B-07 | `PaymentRequiredError` le dit dans son docstring ; `body` brut conservé |
— | `413` à 2 clés | 03 §3.3 | parsing qui n'exige rien |
— | compteurs « tokens » qui comptent des chunks | 06 §4.5 | sans objet en REST ; documenté pour le futur SSE |

---

## 13. Blocages réels — et ce qui ne l'est pas

### Pas un blocage pour une v0.1 interne

**L'absence d'OpenAPI figé.** `responses.py` et `requests.py` sont une spécification lisible, exhaustive et **commentée ligne à ligne**. Les modèles peuvent en être dérivés sans rien inventer. La seule condition est de **nommer le commit** auquel le contrat a été relevé — c'est ce que fait `API_CONTRACT`.

**Les champs ambigus.** Chacun a une issue qui n'invente rien : exposer la valeur brute sous son chemin complet et documenter l'ambiguïté. Aucun n'empêche de transporter correctement la mesure.

### Bloquant pour une **publication publique stable**

| # | Condition | Pourquoi |
|---|---|---|
P1 | **OpenAPI figé et vérifié en CI** | sans spécification figée, aucune garantie de non-dérive entre une version du SDK et une version du serveur |
P2 | **les 5 couples d'homonymes tranchés** | publier un SDK qui expose deux `stability_score` aux échelles inversées, c'est figer le piège pour tous les intégrateurs |
P3 | **le signe de `delta_E` tranché** (A-07) | description et implémentation doivent dire la même chose |
P4 | **table publique du `null`** | le SDK l'implémente ; sans énoncé public, l'intégrateur ne peut pas la vérifier |
P5 | **fixtures capturées depuis un serveur réel** | L6 : seules des charges capturées prouvent que le contrat relevé est celui qui est servi |
P6 | **invariance de la décision au découpage** (R-01) | préalable à tout client SSE, donc à la v0.2 |

### Fonctionnalité bloquée, et une seule

**Le streaming SSE.** Non pas par manque de contrat — il est bien documenté dans `streaming.py:17-36` — mais parce que la **décision** qu'il publie n'est pas invariante au découpage du flux (03 R-01, dette déclarée dans le dépôt). Un client SSE transporterait fidèlement un verdict non reproductible. **Bloqué jusqu'à clarification**, comme la mission le prévoit.

Tout le reste du périmètre v0.1 est développable sans inventer de contrat.

---

## 14. Décision de passage en Phase B

**Les contrats sont suffisants. Passage en Phase B autorisé par la Mission §5.**

Justification : la route, l'authentification, les codes d'erreur, les 17 champs racine et les 9 blocs ont été relevés **dans le code**, à un commit nommé. Aucune invention n'est nécessaire. Les ambiguïtés identifiées ont toutes une issue qui consiste à **exposer la valeur brute et à documenter** — jamais à décider à la place du backend.
