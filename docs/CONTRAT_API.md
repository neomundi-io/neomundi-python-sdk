# Contrat API relevé — `POST /v1/govern`

**Source de vérité** : `govern-v3/app/models/requests.py` et
`responses.py`, au commit **`68d6057cf620e430e6488da3cfcec9c471c75ed6`**.
Version de mesure : **`3.3.0`**.

> **Aucune spécification OpenAPI figée n'existe côté serveur.**
> `/openapi.json` est désactivé en production
> (`docs_enabled = not is_production or DEBUG`, `app/config.py:768-770`),
> et aucun fichier n'est versionné dans le dépôt. Ce document est le
> relevé manuel qui tient lieu de contrat, et c'est pourquoi il nomme un
> commit : sans spécification figée, le commit est le seul point de
> référence vérifiable.

> **Compatibilité du contrat REST `POST /v1/govern` avec la version de
> mesure `3.3.1` vérifiée par tests locaux et rejeu d'une capture de
> production. Appel direct du SDK contre la production non effectué.**
>
> **Vérifié aussi sous la version de mesure `3.3.1`** — 2026-10-22, et
> c'est la version que sert la production. Entre `68d6057` et le commit
> déployé `aeff13c`, **aucun fichier de `app/models/` ne change**, et
> `app/api/v1/governance.py` non plus : ce relevé décrit donc les deux
> versions à l'identique. Le seul fichier applicatif qui diffère est
> `app/api/v1/streaming.py` — le chemin SSE, hors du périmètre de ce
> SDK — plus la chaîne `MEASUREMENT_VERSION` dans `app/config.py`. Le
> verrou doré du backend sur sa surface de mesure
> (`govern-v3/tests/golden/measurement_surface_lock.json`, dépôt
> backend, 1 266 lignes) diffère
> d'**une seule ligne** : la version.
>
> **Ne pas en conclure que les deux versions sont comparables.** Lire
> `audit.measurement_version` sur chaque réponse et le consigner :
> identité de contrat et comparabilité de série sont deux choses
> distinctes. Voir `../KNOWN_LIMITATIONS.md` §6.

---

## 1. Requête

### En-têtes

| En-tête | Valeur |
|---|---|
`X-API-Key` | `ct_live_…` \| `ct_test_…` \| `ct_trial_…` (`app/auth/api_key.py:83-88`) |
`Content-Type` | `application/json` |

### Corps — `GovernRequest`

| Champ | Type | Défaut serveur | Note |
|---|---|---|---|
`source_type` | `str` | `"llm"` | `llm` \| `iot` \| `financial` — détermine les plafonds de normalisation |
`raw_metrics` | objet | **requis** | voir ci-dessous |
`mode` | `str` | `"OBS"` | seule valeur acceptée |
`llm_response` | `str?` | — | ≤ 50 000 car. **Déclenche les contrôles sémantiques serveur.** |
`llm_prompt` | `str?` | — | ≤ 10 000 car. |
`rag_context` | `list[str]?` | — | ≤ 50 entrées, chemin historique |
`documents` | `list[{title,text}]?` | — | ≤ 10 entrées, TIER_02+ |
`metadata` | `dict` | `{}` | opaque, pour le traçage |

### `raw_metrics`

| Champ | Type | Contrainte | Défaut | Unité |
|---|---|---|---|---|
`token_count` | `int` | ≥ 0 | **requis** | tokens |
`latency_ms` | `float` | ≥ 0 | **requis** | millisecondes |
`cost` | `float` | ≥ 0 | `0.0` | **unité de l'appelant, aucune devise** |
`semantic_risk` | `float` | `[0,1]` | `0.0` | — |
`prompt_length` | `int` | ≥ 0 | `0` | **CARACTÈRES** |
`response_length` | `int` | ≥ 0 | `0` | **CARACTÈRES** |
`model_name` | `str` | 1–255 car. | `"unknown"` | — |

### Trois pièges d'unité, déclarés par le backend

1. **`cost` n'a pas de devise.** La valeur est divisée par un plafond par
   type de source pour produire un ratio sans dimension. L'exigence est la
   **cohérence** : la même unité pour toutes les requêtes d'une
   intégration, sinon `cost_proxy` ne compare rien.
2. **`prompt_length` est en caractères et lu comme `tokens_in`** par la
   route, ce qui fait de `volumetric_density` un ratio tokens/caractères —
   déclaré par `density.volumetric_density_basis`.
3. **`response_length` entre dans un calcul** : au-delà de 2 000, il
   participe à la classification « long-form safe », qui peut transformer
   un `FLAG` en `ALLOW`.

### Comportement du SDK

Les paramètres laissés à `None` **ne sont pas envoyés**. Le serveur
applique alors ses propres valeurs par défaut. Le SDK n'en invente aucune.

```python
client.govern(token_count=10, latency_ms=20.0)
# corps émis : {"source_type":"llm","mode":"OBS",
#               "raw_metrics":{"token_count":10,"latency_ms":20.0}}
```

---

## 2. Réponse — `GovernResponse`

### Champs racine

| Champ | Type | Nullable | Note |
|---|---|---|---|
`request_id` | `str` | non | UUID v4, **nouveau à chaque appel**. Non secret. |
`timestamp` | `datetime` | non | **sans fuseau** — exposé en brut par le SDK |
`system_id` | `str` | non | `"controltower-api"` |
`mode` | `str` | non | `"OBS"` |
`g_score` | `float?` | **oui** | alias de `quality.g_score` |
`g_final` | `float?` | **oui** | alias de `esi.g_final` |
`v_score` | `float?` | **oui** | `1 − factual_hallucination_score` |
`delta_g` | `float?` | **oui** | écart avec la requête précédente **du même compte** |
`checks_emitted` | `int?` | oui | analyses ayant produit un résultat exploitable |
`trajectory_points` | `int?` | oui | **toujours `null` en REST** — « sans objet », pas « zéro » |
`measured_signals` | `list[str]?` | oui | signaux ayant une provenance |
`unmeasured_signals` | `dict[str,str]?` | oui | signal → cause |
`measurement` | objet? | oui | complétude de la mesure |
`processing_time_ms` | `float?` | oui | — |
`latency_ms` | `float?` | oui | écho de l'entrée |
`model` | `str?` | oui | écho de `raw_metrics.model_name` |
`evaluators` | `dict[str,dict]?` | oui | provenance par signal |
`provider` | `str?` | oui | **toujours `null` en REST** |

### Blocs

| Bloc | Présence dans le contrat | Traitement SDK |
|---|---|---|
`governance` | **REQUIS** | absence → `InvalidResponseError` |
`metrics` | **REQUIS** | idem — 5 champs, tous nullables |
`baseline` | **REQUIS** | idem — 6 champs, tous nullables |
`audit` | **REQUIS** | idem — 3 champs non nullables |
`quality` | optionnel | `None` si absent |
`runtime` | optionnel | `None` pour TRIAL / TIER_01 |
`density` | optionnel | TIER_02+ |
`esi` | optionnel | TIER_02+ ; ses 9 champs sont requis-mais-nullables |
`rag_grounding` | optionnel | selon les juges d'ancrage |

Les quatre blocs requis sont typés non-`Optional` dans `GovernResult` :
leur absence est une **violation de contrat**, pas une donnée manquante.
Les confondre est exactement ce que ce SDK existe pour éviter.

### `governance`

| Champ | Type | Valeurs |
|---|---|---|
`decision` | `str` | `ALLOW` \| `FLAG` |
`decision_basis` | `str?` | `measured_thresholds` \| `incomplete_measurement` \| `no_check_attempted` \| `null` |
`confidence` | `float` | `[0,1]` — égal à `measurement.coverage` |
`reasons` | `list[str]` | **l'ordre fait partie du contrat** : sur `incomplete_measurement`, la raison d'incomplétude est en position 0 |

`decision_basis` **n'est pas une sévérité**. `null` signifie « la ligne lue
ne porte pas ce champ » — jamais un `measured_thresholds` rassurant.

### `measurement`

| Champ | Type | Note |
|---|---|---|
`status` | `str` | `complete` \| `partial` \| `not_attempted` |
`checks_attempted` | `int` | contrôles **lancés** ; un contrôle désactivé n'est pas compté |
`checks_succeeded` | `int` | — |
`coverage` | `float` | `= confidence`. **Vaut `1.0` quand rien n'a été tenté** — à lire avec `status` |
`confidence_basis` | `str` | `measurement_coverage` \| `no_server_check` |
`degraded_g_inputs` | `list[str]` | termes de `G` alimentés par une convention |
`failed_checks` | `dict[str,str]` | contrôle → cause |
`missing_required_signals` | `list[str]?` | **`None` ≠ `[]`** : `None` = la ligne ne le dit pas |
`aggregates_publishable` | `bool?` | `False` = absence déclarée. **`None` jamais remplacé par `True`** |

### `quality`

| Champ | Type | Avertissement |
|---|---|---|
`g_score` | `float?` | `null` si un signal requis manque |
`stability_score` | `float?` | `G/0.60`, **1 = stable**. Plage effective `[0.60 ; 1.00]` |
`confidence` | `float` | taux de couverture, **pas** une confiance statistique |
`coherence_score` | `float?` | peut valoir `1.0` si le contrôle n'a **jamais été lancé** |
`semantic_risk` | `float?` | **binaire** : `0.0` ou `0.85` |
`factual_hallucination_score` | `float?` | note d'un LLM-juge, `temperature 0.1` |
`semantic_instability_score` | `float?` | **ambiguïté du PROMPT**, pas instabilité de la réponse |
`information_density` | `float?` | densité de texte. **N'entre dans aucun agrégat** |
`suspect_phrases` | `list?` | peut contenir des extraits **auto-extraits** — voir `LIMITES.md` §11 |

### `metrics` — bloc de compatibilité historique

| Champ | Type | Avertissement |
|---|---|---|
`energy_score` | `float?` | `1 − G/0.60` — **0 = pas de risque** |
`e_token` | `float?` | — |
`cost_proxy` | `float?` | — |
`latency_proxy` | `float?` | — |
`stability_score` | `float?` | **ÉCHELLE INVERSÉE** vs `quality.stability_score` : ici **0 = stable** |

### `baseline`

| Champ | Type | Avertissement |
|---|---|---|
`reference_energy` | `float?` | constante `0.05` dans la configuration par défaut |
`observed_energy` | `float?` | — |
`delta_E` | `float?` | **SIGNE AMBIGU** : description ≠ implémentation. Voir `LIMITES.md` §10 |
`calibration_status` | `str?` | `calibrating` \| `calibrated` \| `null` |
`esi_q` | `float?` | **en mémoire par processus serveur**, perdu au redémarrage. ≠ `esi.q_value` |
`esi_bootstrap` | `bool?` | — |

### `esi`

9 champs numériques **requis-mais-nullables** (`g_final`, `s_component`,
`p_component`, `q_component`, `c_component`, `s_value`, `p_value`,
`q_value`, `c_value`) + `betas: dict[str,float]`.

`p_value` et `q_value` sont **la même expression** `N/(N+3H)` et sont
**saturés à ≈1** dès que la réponse dépasse quelques dizaines de tokens.
Les β peuvent être personnalisés par compte : **deux comptes aux β
différents produisent des `g_final` non comparables**.

### `density`

| Champ | Type | Note |
|---|---|---|
`volumetric_density` | `float?` | tokens / **caractères** |
`volumetric_density_basis` | `str?` | `response_tokens_per_prompt_character` |
`informational_energy` | `float?` | `E = N + 3H` |
`informational_density` | `float?` | `Di = (N+3H)/N`. Alimente `P = 1/Di` |
`risk_coefficient` | `int?` | `3`, déclaré choix architectural non réglable |
`factual_input_measured` | `bool?` | **`False` → un `Di` de 1.0 n'est pas une preuve de pureté** |
`unmeasured_reason` | `str?` | — |

### `audit`

| Champ | Type | Note |
|---|---|---|
`measurement_version` | `str` | **le seul numéro qui ait un sens scientifique**. Peut valoir `"unknown"` |
`normalizer_version` | `str` | — |
`trace_id` | `str` | `trace-{request_id[:8]}` — **non unique par construction** |

### `evaluators` — provenance par signal

Une entrée par signal publié, avec :

| Clé | Note |
|---|---|
`evaluator` | module qui produit le signal |
`model_used` | modèle qui a **répondu**. **`null` sauf si le signal est mesuré** |
`status` | `measured` \| `not_measured` \| `not_attempted` |
`reason` | cause, `null` s'il n'y a rien à expliquer |
`model_configured` | modèle **visé** — toujours renseigné |
`served_by` | `primary` \| `fallback` |
`attempts` | appels HTTP émis ; **`0` avec `model_configured` = configuré jamais appelé** |
`latency_ms` | — |
`evaluator_runtime` | **hôte seul** — jamais l'URL, jamais un jeton |
`prompt_template_hash` | empreinte du prompt de jugement |
`inference_config_hash` | empreinte des réglages d'inférence |
`config_fingerprint` | empreinte globale, **exclut la clé API** |

Les trois empreintes sont le **seul moyen** de vérifier que deux
observations ont été produites sous la même configuration d'évaluateur —
`measurement_version` ne couvrant pas l'identité des instruments.

Pour la modération et la cohérence, les neuf champs d'exécution sont
`null` : leurs détecteurs ne les fournissent pas encore (reliquat déclaré
du backend).

---

## 3. Erreurs

### Forme standard — 4 clés

```json
{"error": "...", "detail": "...", "request_id": "...", "timestamp": "..."}
```

### Les deux exceptions

| Statut | Forme | Raison |
|---|---|---|
**413** | **2 clés** : `error`, `detail` | le middleware qui pose `request_id` et `timestamp` n'a pas encore tourné. Peut aussi venir de nginx. |
**422** | `detail` est une **liste** d'objets `{field, message, type}` | validation Pydantic |

### Codes et classes

| Code | Classe SDK | Note |
|---|---|---|
401 | `AuthenticationError` | clé invalide, révoquée ou suspendue |
402 | `PaymentRequiredError` | **3 causes indistinguables** : quota d'essai, solde, budget de clé |
413 | `PayloadTooLargeError` | > 1 048 576 octets |
422 | `ValidationError` | `field_errors` expose la liste normalisée |
429 | `RateLimitError` | `retry_after`, `rate_limit`, `rate_limit_remaining`, `rate_limit_reset` |
5xx | `ServerError` | un 5xx **reçu** prouve que la requête n'a pas abouti |
autre | `APIError` | pour qu'un nouveau code ne se perde pas dans une classe trompeuse |

### En-têtes exploités

| En-tête | Usage SDK |
|---|---|
`X-Request-ID` | posé sur **toute** réponse ; sert de repli quand le corps ne porte pas `request_id` (cas du 413) |
`Retry-After` | exposé sur `RateLimitError.retry_after`, **jamais appliqué automatiquement** |
`X-RateLimit-Limit` / `-Remaining` / `-Reset` | exposés |

---

## 4. Idempotence — pourquoi le SDK ne réessaie pas

`POST /v1/govern` **n'est pas idempotent**. Relevé dans le backend :

| Effet d'une répétition | Emplacement |
|---|---|
une **nouvelle observation** est créée | `runtime_engine.py:162` — `uuid.uuid4()` par appel |
le **quota ou le portefeuille est débité** | `governance.py:172` — débit avant le travail |
une **ligne de métrologie** est écrite | `governance.py:586-626` — table `usage_events` |
la **référence `delta_g` du compte est écrasée** | `governance.py:2088` — clé Redis par compte |

**Aucun en-tête d'idempotence n'existe** sur cette route : la recherche de
`Idempotency-Key` dans `govern-v3/` ne renvoie aucune occurrence.

C'est la raison pour laquelle `max_retries` vaut `0` par défaut, et
pourquoi **un timeout n'est jamais réessayé** même avec une politique
active.

---

## 5. Divergences relevées entre la description et l'implémentation

| # | Champ | Description serveur | Implémentation | Traitement SDK |
|---|---|---|---|---|
D-1 | `baseline.delta_E` | `observed − reference` | `reference − observed` | valeur brute, avertissement en docstring. **Découvert pendant cette mission.** |
D-2 | `raw_metrics.prompt_length` | « en caractères » | lu comme `tokens_in` | nom et unité conservés, ambiguïté documentée |
D-3 | `metrics.stability_score` | même nom que `quality.stability_score` | échelle inversée | deux attributs distincts, aucun raccourci |

Ces trois points sont des **arbitrages produit**, pas des bugs du SDK.
Aucun n'empêche de transporter correctement la mesure.

---

## 6. Ce que ce relevé ne garantit pas

Il décrit **ce que le code du backend déclare** au commit nommé. Il ne
garantit pas que le serveur déployé émet exactement cela : la
correspondance entre ce commit et la production n'est établie que pour un
seul des composants de la plateforme.

**Lever cette limite** demande de capturer des charges réelles depuis une
instance de test et de rejouer la suite du SDK contre elles. C'est la
première action recommandée avant tout pilote.
