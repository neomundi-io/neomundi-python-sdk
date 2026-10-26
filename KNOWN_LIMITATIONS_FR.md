# Limites connues — SDK Python NeoMundi 2.0.0

[Français](KNOWN_LIMITATIONS_FR.md) · [English](KNOWN_LIMITATIONS.md) · [Accueil](README_FR.md)

**Évaluation pilote. Développement V2 terminé ; qualification réelle du SDK V2 en attente.**

Mise à jour documentaire : 26 octobre 2026. Les observations backend
ci-dessous restent rattachées à leur date.
Référence auditée : commit `68d6057cf620e430e6488da3cfcec9c471c75ed6`,
version de mesure `3.3.0`. Surface REST également vérifiée sous
`3.3.1` (commit `aeff13c`) ; voir §6.

Ce document décrit ce qui fonctionne, la méthode de vérification et les
défauts backend relevés. « Observé » signifie relevé sur une instance
avec des conditions précisées. « Dérivé du code » désigne une conclusion
tirée de la source au commit cité. Ces preuves ne sont pas interchangeables.

La V2 ajoute `stream()` / `govern_stream()`, un résultat SSE distinct
et des erreurs d’interruption typées. Elle ne répare pas les limites
scientifiques du backend. Voir [l’audit V2](docs/AUDIT_SDK_V2.md).

## 1. État du SDK

| Élément | État |
|---|---|
| Version | `2.0.0` |
| Maturité | Évaluation pilote ; non qualifié ici pour un usage de production |
| Périmètre | REST `POST /v1/govern` et SSE synchrone `POST /v1/govern/stream` |
| Dépendance directe à l’exécution | `httpx` |
| Python | ≥ 3.9 ; validation locale V2 sous 3.12, CI réussie sous 3.9, 3.11, 3.12 et 3.13 |
| Distribution | Pas sur PyPI ; installation depuis le dépôt public ou un paquet identifié |
| Licence | Choix non arbitré ; voir [LICENSE_NOTICE.md](LICENSE_NOTICE.md) |

### Portée des tests

La suite **V2** compte **282 tests réussis et 12 ignorés** sans les captures
historiques non versionnées. Les vérifications exécutées figurent dans
[VERIFICATION_V2.md](docs/VERIFICATION_V2.md).

Les nombres suivants décrivent les suites historiques antérieures,
pas la suite actuelle :

| Périmètre historique | Résultat | Ce qu’il établit |
|---|---|---|
| Suite de référence sans captures privées | 225 réussis, 12 ignorés | Comportement du client face au contrat dérivé du code et à la capture `3.3.1` assainie de `tests/fixtures/production_331/` |
| Suite locale avec captures | 347 réussis | Même vérification, plus correspondance avec les réponses d’une instance réellement exécutée |

Les 12 tests ignorés nécessitent les captures `3.3.0` :
ce sont des données d’exécution exclues du dépôt
(`tests/fixtures/captured/` est dans `.gitignore`), pas des contrôles
désactivés. Ils sont ignorés partout où ces données manquent, notamment en CI.

La capture `3.3.1` est une exception volontaire : elle ne contient ni
prompt, ni réponse textuelle, ni identité d’évaluateur. Elle a pu être
assainie et versionnée. Les remplacements sont détaillés dans
`_fixture_redacted`.

### Compatibilité d’un déploiement

Les modèles du SDK proviennent des modèles de requête et de réponse
du backend à un commit précis. Aucune spécification OpenAPI figée
n’est disponible côté serveur ; `/openapi.json` est désactivé dans les
constructions de production inspectées.

La compatibilité a été vérifiée contre une instance locale issue de cette
référence, puis contre la surface REST `3.3.1` par comparaison des sources
et rejeu d’une réponse réelle (§6). Cela ne constitue pas un appel direct
du SDK à un déploiement hébergé. Une version hors liste ou des champs ajoutés
depuis peuvent se comporter différemment.

```python
import neomundi
result = client.govern(...)

served = result.audit.measurement_version

if served not in neomundi.API_CONTRACT["verified_measurement_versions"]:
    # Unverified contract: fields may have changed meaning. Stop here.
    ...
elif served != neomundi.API_CONTRACT["measurement_version"]:
    # Parsing is safe, but the series is not comparable with one produced
    # under a different measurement version. Record `served` alongside
    # every observation.
    ...
```

Le premier contrôle demande si le client peut lire la réponse.
Le second porte sur la comparabilité scientifique d’une série.
`3.3.1` satisfait le premier pour REST ; cela n’autorise pas à mélanger
automatiquement ses observations avec une série `3.3.0`.

## 2. Fonctionnalités vérifiées

### Exécution sur une instance locale

Campagne historique : dix appels REST sur une instance construite au commit
de référence, palier `TIER_02`, trois évaluateurs actifs :
Llama Guard 3 1B, nomic-embed-text et Llama 3.2 3B sur Ollama local.

| Contrôle | Résultat |
|---|---|
| Construction et lecture de `POST /v1/govern` | 10/10 réponses analysées |
| Écarts de type `parse_warnings` | 0 sur les réponses capturées |
| Champs racine non modélisés `unknown_fields` | 0 |
| Version de mesure | `3.3.0`, conforme à la référence |
| Restitution brute par `to_dict()` | Identique pour chaque capture |
| Alias racine `g_score` / `g_final` et blocs | Concordants |
| Couverture recalculable depuis les compteurs | Vérifiée |
| Bases de décision exercées | `measured_thresholds`, `incomplete_measurement`, `no_check_attempted` |
| Trois évaluateurs injoignables | Agrégats `null`, `FLAG`, base `incomplete_measurement`, couverture 0/3 ; causes nommées |
| Couverture partielle | 2/3 avec cohérence manquante et 0/3 |
| Recherche de secrets | Aucun champ à expurger dans ces captures |

Les causes du parcours totalement dégradé étaient
`moderation_service_unavailable`, `coherence_service_unavailable`
et `hallucination_judge_unavailable`.

### Rejeu d’une réponse de production 3.3.1

Une réponse réellement produite le **21 octobre 2026** sous
`measurement_version = 3.3.1` a été rejouée via un transport simulé le
**22 octobre**. Copie assainie :
`tests/fixtures/production_331/rest_complete_allow.json` ;
tests : `tests/test_measurement_version_331.py`.

| Contrôle sur cette réponse | Résultat |
|---|---|
| `parse_warnings` | 0 |
| `unknown_fields` | 0 |
| Restitution brute | Exacte |
| Alias `g_score`, `g_final` et blocs | Concordants |
| Couverture 3/3 → 1.0 | Recalculable |
| Quatre blocs requis | Présents |
| Douze champs de provenance par signal | Exposés, y compris les `null` |
| `trajectory_points`, `provider` en REST | Toujours `None` |
| `quality.stability_score + metrics.stability_score` | 1.0 : les échelles inverses coexistent |
| `baseline.delta_E` | `reference − observed`, conformément au calcul mais pas à sa description |
| Décision / base | `ALLOW` / `measured_thresholds` |

**C’est un rejeu, pas un appel réel du SDK.** `httpx.MockTransport`
a fourni la réponse : cela vérifie que le client sait lire ce que
la production a émis, pas que l’ensemble du parcours réseau fonctionne.

Sur cette réponse, les trois empreintes
`prompt_template_hash`, `inference_config_hash`, `config_fingerprint`
n’étaient renseignées que pour les deux signaux du juge factuel.
`stability_score`, `coherence_score` et `semantic_risk` étaient
`measured` avec les trois empreintes à `null`. La réponse ne permet
donc pas de prouver une configuration identique entre deux observations
sur ces trois signaux. Le SDK expose ces absences ; un test les conserve.

### Tests sans instance active

La répartition suivante appartient à la suite historique ; les tests REST
restent présents et les tests SSE V2 s’y ajoutent.

| Capacité | Vérification |
|---|---|
| `X-API-Key` et validation locale du format | `test_client.py` |
| Neuf familles : 401, 402, 413, 422, 429, 5xx, timeout, réseau, réponse invalide | `test_errors.py`, 39 tests historiques |
| Aucun réessai par défaut ; timeout jamais rejoué même avec politique explicite | `test_retry.py`, 26 tests historiques |
| `null` préservé, `None` distinct de zéro et de `[]` | `test_models.py` |
| Champs inconnus conservés dans `raw` et signalés | `test_models.py` |
| Absence de valeur numérique par défaut, contrôlée par analyse AST | `test_contract_drift.py` |
| Aucun import backend, dépendance non déclarée ou seuil embarqué | `test_contract_drift.py` |
| Absence de clé dans les sorties REST, corps et URL ; contrôle du dépôt | `test_no_secret_leak.py`, 11 tests historiques |
| Trois exemples REST hors ligne | `test_examples.py` ; l’exemple SSE est ajouté en V2 |

Le contrôle d’absence de clé dans le corps concerne **REST** :
SSE doit transmettre la clé fournisseur dans son corps JSON, comme décrit
dans le [guide SSE](docs/STREAMING_FR.md).

### Ce qui reste non vérifié

- Appels authentifiés du SDK V2 contre un déploiement hébergé ; qualification réelle en attente.
- Authentification, statuts d’erreur, délais, limitation de débit et quotas réels : les familles d’erreur sont testées sur transport simulé.
- Concurrence et charge soutenue.
- Versions de mesure hors `verified_measurement_versions`.
- Parcours `3.3.1` avec mesure incomplète : la capture disponible est complète ; la non-publication des agrégats a été revérifiée par identité du code, pas par cette capture.
- Variance du juge factuel à entrée constante, voir SL-005.

## 3. Limites connues du backend

Ces limites proviennent d’observations ou de la lecture du code au commit
de référence. Le SDK les rend visibles sans les contourner.

Les trois ont été relues contre `aeff13c` / `3.3.1` le
**22 octobre 2026**, par comparaison des sources et rejeu de la réponse
de production. Un changement de version ne clôture pas un défaut :
BL-001 et BL-003 portent sur des fichiers identiques ; BL-002 comporte
une correction de classe précise, pas une clôture globale.
Les conclusions suivantes sont datées et ne constituent pas un nouvel audit de production.

### BL-001 — Incohérence entre compte TRIAL et état de clé

| Élément | Constat |
|---|---|
| État | Ouvert — observé |
| Version | `68d6057` / `3.3.0` ; relecture `aeff13c` / `3.3.1` du 22 octobre : inchangé |
| Périmètre | Comptes avec `tier = TRIAL` et `status = ACTIVE` |
| Gravité pilote | Élevée : bloque l’utilisation d’une clé d’essai |
| Impact client | Le SDK restitue fidèlement les réponses serveur |

`app/auth/api_key.py` est identique octet par octet entre les deux commits.
Le débit de quota conserve `AND status = 'TRIAL'`, alors que la suspension
des clés n’a pas de garde équivalente. Cette conclusion sous `3.3.1`
vient du code ; le parcours compte n’a pas été rejoué avec une nouvelle clé d’essai.

**Observation historique.** Sur une instance locale, un nouveau compte d’essai
a suivi le parcours documenté : inscription, validation e-mail et approbation
administrateur. Sa clé fonctionnait sur un endpoint authentifié non facturé.
Le premier `POST /v1/govern` a répondu **402**, quota présenté comme
épuisé, puis tous les appels suivants **401**.

| État immédiatement après | Valeur |
|---|---|
| `accounts.status` | `ACTIVE` |
| `accounts.tier` | `TRIAL` |
| `accounts.trial_requests_remaining` | 500 |
| `accounts.trial_requests_total` | 500 |
| `api_keys.status` | `SUSPENDED` |

Le quota n’avait pas été consommé, pourtant la clé était suspendue.

**Conditions.** Un compte, une instance locale, le parcours documenté.
Aucune généralisation aux déploiements hébergés, aux autres méthodes de
provisionnement ou aux comptes dont l’état n’est pas `ACTIVE`.
L’état des comptes hébergés n’était pas vérifié.

**Cause confirmée dans le code :**

```sql
UPDATE accounts
SET trial_requests_remaining = trial_requests_remaining - 1
WHERE id = :account_id
  AND status = 'TRIAL'                 -- the condition in question
  AND trial_requests_remaining > 0
RETURNING trial_requests_remaining
```

Une migration de la référence déplace la détection d’essai de `status`
vers `tier`. Le portail écrit donc `status='ACTIVE'`, `tier='TRIAL'`.
L’UPDATE ne trouve aucune ligne ; le résultat vide est interprété comme
un quota épuisé. La branche de suspension suspend ensuite les clés sans
garde équivalente, alors que le compte n’est pas suspendu.

**Conduite à tenir.** Aucun contournement client. Demander au contact
NeoMundi un compte accepté par le parcours de quota serveur : par exemple
un palier payant avec portefeuille approvisionné ou un état de compte
ajusté par l’opérateur. Ne pas contourner la restriction soi-même.

Suivi interne : plan backend, BL-001.

### BL-002 — Décision SSE sensible au découpage réseau

| Élément | Constat |
|---|---|
| État | Partiellement corrigé en `3.3.1` ; classe nommée « corrigée — vérification en attente », résidu ouvert |
| Version | Observé à `68d6057` / `3.3.0` ; correction partielle à `aeff13c` / `3.3.1` |
| Périmètre | `POST /v1/govern/stream` uniquement ; REST non affecté par ce défaut |
| Gravité pilote | Élevée pour le streaming |
| Impact SDK | La V2 transporte la trajectoire sans la corriger |

Les contrôles d’intégrité et de terminaison du [guide SSE](docs/STREAMING_FR.md)
ne valident ni la trajectoire ni ses métriques.

#### Correction 3.3.1 et résidu

Entre les commits cités, un seul fichier applicatif de traitement change :
`app/api/v1/streaming.py`, plus la version dans `app/config.py`.
Les règles R1/R2/R3 lisent désormais uniquement les points de trajectoire
dont cohérence **et** risque ont réellement été mesurés, ainsi que le point final.

La trajectoire publiée (`series`, `profile`, `total_variation`,
`min_stability`, `max_stability`) ne change pas ; les séries déjà stockées
ne sont donc pas réinterprétées.

Résultats de la suite de régression backend, pour un même texte et des
verdicts fixes, avec seul le découpage variant :

| Fragments | Décision avant | Décision après |
|---:|---|---|
| 1 | `ALLOW` | `ALLOW` |
| 10 | `ALLOW` | `ALLOW` |
| 20 | `FLAG` | `ALLOW` |
| 50 | `FLAG` | `ALLOW` |
| 300 | `FLAG` | `ALLOW` |

**Résidus à cette référence :**

- ΔG reste sensible au découpage : `series`, `profile` et `total_variation` varient avec la fragmentation. Un test backend exige que cette différence reste visible.
- Un découpage trop grossier peut ne donner aucune trajectoire mesurée : avec les intervalles par défaut, la première fenêtre contenant les deux signaux arrive au fragment 120. Avant, aucune règle ne peut se déclencher.
- La course asynchrone entre évaluateurs subsiste. Écarter les fenêtres incomplètes ne rend pas l’arrivée des signaux déterministe.
- Quatre seuils restent codés en dur ; deux sont présents dans le modèle d’environnement de production sans être lus par le code.

Ne comparez pas `delta_g.profile` ou `delta_g.total_variation` entre
fournisseurs, clients ou versions. Pour des comparaisons reproductibles,
privilégiez REST en vérifiant aussi les conditions du §6.

**Portée de la preuve.** Ces conclusions viennent de la source backend
et de sa suite de régression à `aeff13c`, relues le 22 octobre.
La correction n’avait pas été vérifiée sur un flux de production dans
cette campagne. Un succès de transport ultérieur ne suffirait pas à
valider son invariance au découpage : la classe reste « corrigée —
vérification en attente » et l’entrée entière reste ouverte.

#### Observations initiales

Quatre flux locaux contenaient une réponse correcte, avec
`factual_hallucination_score = 0.0` et une stabilité finale de 0.86 à 0.94 :

| Fragments de contenu | Profil ΔG | Variation totale | Décision |
|---:|---|---:|---|
| 1 | `FLAT` | 0.0 | `ALLOW` |
| 1 | `FLAT` | 0.0 | `ALLOW` |
| 10 | `FLAT` | 0.0 | `ALLOW` |
| 300 | `DROP` | 0.158 | `FLAG` |

La qualité finale mesurée était équivalente ; la décision différait.

Les fenêtres intermédiaires se déclenchaient tous les N fragments réseau,
pas tous les N tokens. Chacune utilisait les signaux disponibles à cet
instant ; le juge factuel ne s’exécutant qu’en fin de flux, les fenêtres
intermédiaires utilisaient pour lui une valeur neutre.

Extrait de la trajectoire à 300 fragments :

```
fragment  20 → stability 1.0000   delta 0.0000
fragment  40 → stability 1.0000   delta 0.0000
fragment  60 → stability 0.8896   delta −0.1104   ← coherence reports here
fragment  80 → stability 0.8896   delta  0.0000
fragment 100 → stability 0.8867   delta −0.0029
```

La « chute » correspond à **l’arrivée de la mesure de cohérence**, pas
à une dégradation pendant la génération. Une règle de profil la lit
comme instabilité et fait évoluer la décision. Un flux assez court pour
ne produire aucune fenêtre intermédiaire a une trajectoire à un point,
classée `FLAT`, sans cette escalade.

Sur un flux signalé, `reasons` contenait simultanément
`"all metrics within bounds"` et
`"possible hallucination or drift in progress"`,
alors que le juge n’avait mesuré aucune hallucination.
`decision_basis` indiquait `measured_thresholds`, bien que cette
évolution provienne de la règle de profil ΔG.

**Conduite à tenir :** ne comparez pas trajectoires ou décisions de streaming
entre fournisseurs, bibliothèques ou versions dont la fragmentation diffère.
Traitez les événements intermédiaires `governance_check` et
`stability_check` comme provisoires : `provisional: true` est significatif.
Privilégiez REST quand la reproductibilité est requise.

Suivi interne : plan backend, BL-002.

### BL-003 — delta_g publié malgré un agrégat retenu

| Élément | Constat |
|---|---|
| État | Ouvert — observé ; interprétation du contrat en cours d’examen |
| Version | `68d6057` / `3.3.0` ; relecture `aeff13c` / `3.3.1` du 22 octobre : inchangé |
| Périmètre | REST, lorsqu’un signal requis n’a pas été mesuré |
| Gravité pilote | Moyenne : risque de mauvaise lecture d’un champ |
| Impact SDK | Valeur brute exposée, réserve documentée |

La route `app/api/v1/governance.py` et les modèles sont identiques entre
les deux commits. La persistance du comportement sous `3.3.1` est établie
par le code, sans nouvelle observation du cas incomplet. La capture
`3.3.1` disponible étant complète, elle n’exhibe pas ce cas.

**Observation.** Lorsque des signaux requis manquaient, `g_score`,
`quality.stability_score` et `g_final` étaient correctement `null`,
avec `FLAG` et `incomplete_measurement`, mais `delta_g` restait numérique.
Deux des dix captures REST montraient ce comportement, ainsi que la capture
totalement dégradée : `g_score: null`, `delta_g: −0.56199`.

**Lecture du contrat.** `delta_g` est documenté comme la variation de G
depuis la requête précédente du compte. La règle de non-publication nomme
explicitement les trois agrégats ci-dessus, pas `delta_g`. La présence
du champ peut donc respecter le texte du contrat tout en restant dangereuse
à interpréter.

La valeur utilise précisément le G interne non publié de la requête
courante ; la référence enregistrée pour la suivante utilise le même G.
Une série de `delta_g` traversant une requête dégradée n’est donc pas
interprétable, indépendamment de l’intention du contrat.

```python
if result.measurement_incomplete:
    # Aggregates are withheld. Do not read delta_g as a quality signal
    # for this observation, and do not chain it with neighbouring
    # observations.
    result.missing_required_signals     # which signals were not measured
    result.measurement.coverage         # how much of the measurement happened
    result.governance.decision_basis    # 'incomplete_measurement'
```

Plus généralement, **`delta_g` n’est pas une mesure de dérive**.
Il compare une requête à la précédente du même compte dans une fenêtre
d’une heure, même si leurs questions et tâches sont sans rapport.
Il peut décrire le changement de tâche plutôt qu’un changement du système.

Suivi interne : plan backend, BL-003.

## 4. Limites propres au SDK

La V2 apporte le transport SSE ; les limites scientifiques restent présentes.

| ID | Limite | Motif |
|---|---|---|
| SL-001 | Qualification réelle du SSE V2 contre un déploiement et un fournisseur | Transport implémenté et testé hors ligne ; pas de nouvel appel SSE hébergé du SDK. BL-002 reste distincte. |
| SL-002 | Pas de SDK TypeScript / JavaScript | Hors périmètre ; une spécification OpenAPI figée manque côté serveur |
| SL-003 | Pas de traitement longitudinal : séries, tendances, dérives | La comparabilité dépend de versions, couverture, évaluateurs, poids β et route. C’est une appréciation méthodologique, pas une fonction de transport. |
| SL-004 | Pas d’interprétation automatique des scores | Pas de `is_safe()`, niveau de qualité ou seuil embarqué ; seuils serveur non publiquement calibrés. Absence contrôlée par AST. |
| SL-005 | Pas de correction des défauts backend ; variance du juge non mesurée | BL-001 à BL-003 restent visibles. Le juge factuel utilise une température non nulle : la dispersion à entrée constante n’est pas caractérisée. |

Également absents : client asynchrone, autres routes REST (rejeu, exports,
RGC), cache, pagination et vérification de certificat PDF.
Sans caractérisation de variance, une différence de scores ne peut pas
être déclarée significative sur la seule base de deux observations.

## 5. Conseils d’intégration

### 5.1 Lire d’abord la couverture

```python
result = client.govern(..., llm_response=text, llm_prompt=prompt)

if result.measurement_incomplete:
    print("incomplete:", result.missing_required_signals)
    # The FLAG you are about to see is NOT a statement about the content.

m = result.measurement
m.status            # 'complete' | 'partial' | 'not_attempted'
m.checks_attempted  # checks actually launched
m.checks_succeeded  # of those, how many produced a usable result
m.coverage          # the ratio — and the value of `confidence`
```

**`coverage == 1.0` ne signifie pas nécessairement « tout mesuré ».**
La couverture vaut aussi 1.0 lorsque rien n’a été tenté. Lire l’état :

```python
if m.status == "not_attempted":
    # No server-side check ran. coverage 1.0 means "nothing was expected",
    # not "everything was measured".
    ...
```

Lorsque `checks_attempted > 0`, la couverture peut être recalculée :

```python
if m.checks_attempted:
    assert round(m.checks_succeeded / m.checks_attempted, 6) == m.coverage
```

### 5.2 Préserver les null

Ne substituez jamais un nombre à un `null`. Les sources du SDK sont
contrôlées pour éviter les valeurs numériques de remplacement.

```python
# For display — never raises.
result.format_score("g_score", nd=4)              # '0.4920' | 'non mesuré'
result.format_score("g_score", when_none="n/a")

# For a computation — raises an exception that names the cause.
from neomundi import AggregateWithheldError
try:
    value = result.require("g_score")
except AggregateWithheldError as exc:
    exc.missing_required_signals
    exc.decision_basis

# What not to do:
f"{result.g_score:.2f}"    # TypeError as soon as the aggregate is withheld
```

| Sens possible d’un null | Indice |
|---|---|
| Contrôle tenté, sans résultat mesuré | Signal présent dans `unmeasured_signals` avec une cause |
| Non disponible au palier | Signal absent des deux listes, état `complete` ; à lire dans le contexte du contrat |
| Non applicable à la route | `trajectory_points` et `provider` sont `None` sur REST |

### 5.3 Zéro mesuré et absence de mesure

Une valeur numérique seule ne prouve pas la validité d’un signal.
Les valeurs de secours des instruments peuvent être rassurantes
(risque 0.0, cohérence 1.0, factualité 0.0) : lire les états publiés.

```python
# A measured zero:
result.quality.semantic_risk            # 0.0  -> measured, nothing detected
result.is_measured("semantic_risk")     # True

# An absence:
result.quality.factual_hallucination_score   # None -> not measured
result.unmeasured_reason("factual_hallucination_score")
# 'hallucination_judge_unavailable'

# Four states, and the SDK does not collapse them:
result.measurement_state("coherence_score")
#   MeasurementState.MEASURED
#   MeasurementState.NOT_MEASURED            -> a cause is available
#   MeasurementState.NOT_ATTEMPTED_OR_GATED  -> not launched OR gated by tier
#   MeasurementState.UNKNOWN                 -> the response does not say
```

`NOT_ATTEMPTED_OR_GATED` conserve l’ambiguïté du serveur :
non lancé ou filtré par le palier. `measurement.status` et
`checks_attempted` aident à préciser, sans inventer une distinction absente.

Une capture sans aucun contrôle lancé portait
`quality.coherence_score = 1.0`, des champs factuels `null` et des agrégats
à leur maximum. Une cohérence de 1.0 n’est donc pas toujours une observation.

### 5.4 Conserver audit et versions

```python
result.request_id                      # the observation's identity
result.timestamp_raw                   # the server's instant, as sent
result.audit.measurement_version       # the only version with scientific meaning
result.audit.normalizer_version
result.measurement.coverage            # how much of the measurement happened
result.evaluators                      # per-signal instrument, model, cause

# The three fingerprints are the only way to verify that two observations
# were produced under the same evaluator configuration — `measurement_version`
# does not cover evaluator identity.
ev = result.evaluator_of("factual_hallucination_score")
ev["model_used"], ev["config_fingerprint"], ev["prompt_template_hash"]

result.esi.betas if result.esi else None   # the weights actually applied
result.to_dict()                           # the full raw payload
```

Une comparaison exige au minimum même version de mesure, même couverture,
mêmes modèles d’évaluateurs, mêmes poids β et même route. Le SDK expose
les éléments disponibles, mais ne valide pas la série à votre place.
Si les empreintes sont absentes, l’identité des configurations ne peut pas
être démontrée avec ces données.

### 5.5 FLAG ne prouve pas une hallucination

Un `FLAG` est indicatif. NeoMundi ne donne ni ne retire d’autorisation
d’exécution à votre application ; le format de contrat signé conserve
cette séparation.

| Base | Lecture du FLAG |
|---|---|
| `measured_thresholds` | Franchissement d’un seuil déclaré sur un signal mesuré ; voir la réserve SSE BL-002 |
| `incomplete_measurement` | Mesure non terminée ; ce FLAG ne porte pas sur le contenu |
| `no_check_attempted` | Aucun contrôle serveur lancé |
| `None` | Champ absent de l’observation ; ne pas supposer `measured_thresholds` |

Le juge factuel est un modèle de langage sans source externe dans ce parcours,
à température non nulle : son score est un verdict traçable, pas un fait
vérifié. En SSE, lire aussi `reasons` : BL-002 a montré une base
`measured_thresholds` sur une escalade issue du profil ΔG.

### 5.6 Signaler un écart

```python
result.parse_warnings   # a field could not be read at the expected type
result.unknown_fields   # a root field this SDK version does not model
```

| Constat | Action |
|---|---|
| `parse_warnings` non vide | Examiner et signaler l’écart au contrat ; ne pas élargir silencieusement les conversions |
| `unknown_fields` non vide | Signaler l’évolution du backend et examiner l’extension du SDK |
| `InvalidResponseError` sur 2xx | Signaler bloc requis absent ou corps non JSON ; expurger le corps avant partage |
| Version hors `verified_measurement_versions` | Signaler avant de s’appuyer sur la lecture |
| Version vérifiée mais différente de la référence | Conserver sa valeur ; ne pas mélanger automatiquement les séries |

Joindre l’identifiant, la version de mesure, les avertissements exacts,
l’environnement et la version du SDK. Ne joindre aucune clé et expurger
tout contenu non partageable.

Utiliser le contact technique NeoMundi pour les éléments confidentiels.
Les issues du dépôt public peuvent recevoir des reproductions assainies
sans clés ni données privées.

## 6. Compatibilité des versions

La compatibilité REST `3.3.1` est établie par tests locaux et rejeu,
pas par un appel direct de ce SDK à la production.

| Référence | Valeur |
|---|---|
| Commit backend audité | `68d6057cf620e430e6488da3cfcec9c471c75ed6` |
| Version de mesure de référence | `3.3.0` |
| Versions dont la surface REST est vérifiée | `3.3.0`, `3.3.1` |
| Normaliseur | `1.0.0`, inchangé entre ces références |
| Contrat | Modèles de requête et réponse à ce commit |
| OpenAPI figée | Aucune à cette référence |

Extrait des références REST de `API_CONTRACT` ; la V2 contient aussi
les références SSE :

```python
import neomundi
neomundi.API_CONTRACT
# {'backend_commit': '68d6057cf620e430e6488da3cfcec9c471c75ed6',
#  'measurement_version': '3.3.0',
#  'verified_measurement_versions': ('3.3.0', '3.3.1'),
#  'normalizer_version': '1.0.0',
#  'route': 'POST /v1/govern',
#  'contract_source': 'govern-v3/app/models/responses.py, requests.py',
#  'openapi_frozen': False}
```

### Quatre versions à distinguer

| Version | Valeur historique observée | Où la lire |
|---|---|---|
| Application | `3.0.0` | `GET /v1/health`, champ `version` |
| Mesure | `3.3.1` | `result.audit.measurement_version` dans une réponse |
| Normaliseur | `1.0.0` | `result.audit.normalizer_version` |
| Schéma de contrat RGC | `0.1.0` | Contrat signé ; route non couverte par ce SDK |

`GET /v1/health` ne publie pas la version de mesure. Le 22 octobre,
la production répondait 200, version 3.0.0 et environnement production,
sans `measurement_version`. Les routes `/openapi.json`, `/docs`,
`/v1/version`, `/version` avaient répondu 404 le 21 octobre.
Dans cette surface inspectée, connaître la version de mesure exige donc
une observation consommant un quota, pas une lecture gratuite de health.

### Pourquoi 3.3.1 est dans la liste vérifiée

Deux preuves datées du 22 octobre, aucune issue d’un appel hébergé du SDK :

**1. Comparaison des sources `68d6057` → `aeff13c`.**
Sept fichiers diffèrent ; deux sont applicatifs : streaming et chaîne de
version dans la configuration. Les cinq autres sont documentation et tests.

- Aucun changement dans `app/models/`.
- Aucun changement dans la route REST `app/api/v1/governance.py`.
- Aucun changement dans `app/auth/`, `app/core/`, `app/rgc/`, `app/main.py`.
- Le fichier de référence backend de 1 266 lignes ne change que sur la chaîne de version : signaux, couverture, filtrage et provenance sont identiques.

Selon le backend, la différence pour une même entrée ne porte que sur
l’observation streaming laissée à `ALLOW` par les signaux mesurés mais
classée `DROP` ou `OSCILLATING` à partir de points non mesurés.
Le reste — REST, décisions SSE issues des signaux mesurés, agrégats,
couverture, champs filtrés — est annoncé identique. C’est une déclaration
du backend sur ses calculs, pas une permission de mélanger les séries.

**2. Rejeu d’une réponse réelle `3.3.1`.**
Réponse de production du 21 octobre : zéro avertissement de lecture,
zéro champ racine inconnu, restitution exacte, alias cohérents et couverture
recalculable ; détails au §2.

Le relevé d’uptime du 22 octobre plaçait le démarrage du processus au
`2026-10-20T21:16:45`, comme un relevé indépendant du 21.
Il indiquait donc le même processus à ces deux dates, pas une garantie
de continuité depuis lors ni un appel de bout en bout.

### Ce que la liste vérifiée ne garantit pas

- Pas de succès d’appel hébergé du SDK V2 ; authentification, erreurs, délais et quotas de production restent à qualifier.
- Pas de comparabilité automatique entre versions.
- Pas de validation de la surface SSE par les preuves REST. La V2 implémente SSE ; ses tests hors ligne et son contrat sont décrits séparément dans le [guide SSE](docs/STREAMING_FR.md).

### Contrôles avant une campagne pilote

1. Lire `GET /v1/health`, sans authentification ni quota de mesure : conserver version applicative et état des trois évaluateurs, sans en déduire la version de mesure. Un état factuel `degraded` peut coexister avec une mesure ponctuelle réussie ; ne présumez pas la cause d’un nouvel état dégradé.
2. Effectuer un `POST /v1/govern` autorisé et conserver sa version de mesure.
3. Vérifier sa présence dans `verified_measurement_versions`.
4. Vérifier `parse_warnings` et `unknown_fields`.
5. Conserver les empreintes d’évaluateurs et examiner leur stabilité pendant la campagne ; la capture `3.3.1` ne renseigne les trois empreintes que pour les deux signaux factuels.

### Règle de comparabilité

Le backend indique que `3.2.0` et `3.3.0` ne sont pas comparables,
pour une même entrée, dans les parcours streaming, si un signal requis
n’a pas été mesuré ou si le client est sur un palier d’entrée.
Une étude longitudinale doit rester d’un côté de cette frontière.

Pour `3.3.0` / `3.3.1`, la déclaration d’identité est plus étroite :
elle couvre REST comme expliqué plus haut.
Conservez la version de mesure sur chaque observation et séparez les séries
tant que leur comparabilité n’est pas établie. Une version non enregistrée
ne peut pas être reconstituée de façon fiable après coup.

## 7. Suivi des limites

Chaque entrée conserve un identifiant stable, jamais réutilisé ou renuméroté.
Une correction change son état, pas son identité.

| État | Sens |
|---|---|
| Ouvert — observé | Reproduit sur une instance, conditions précisées |
| Ouvert — dérivé du code | Établi par lecture des sources, pas encore reproduit |
| En cours d’examen | Contrat attendu à clarifier avant correction |
| Corrigé — vérification en attente | Correction appliquée, pas encore revérifiée sur instance |
| Corrigé — vérifié | Correction et nouvelle vérification, preuves référencées |
| Par conception | Limite de périmètre documentée, pas un défaut |

### Registre

| ID | Limite | État et version | Périmètre / suivi |
|---|---|---|---|
| BL-001 | Compte TRIAL et état de clé incohérents | Ouvert — observé ; relu inchangé sous `3.3.1` | Comptes TRIAL/ACTIVE locaux ; plan BL-001 |
| BL-002 | Décision SSE dépendant du découpage | Classe corrigée — vérification en attente sous `3.3.1` ; résidu ouvert | SSE uniquement ; plan BL-002 |
| BL-003 | delta_g publié malgré agrégat retenu | Ouvert — observé, contrat en examen ; inchangé sous `3.3.1` | REST incomplet ; plan BL-003 |
| SL-001 | Qualification réelle SSE V2 | En attente ; transport implémenté et testé hors ligne | SDK 2.0.0 ; BL-002 distincte |
| SL-002 | Pas de SDK TypeScript | Par conception, périmètre hérité de 0.1.0 | SDK |
| SL-003 | Pas de traitement longitudinal | Par conception, périmètre hérité de 0.1.0 | SDK |
| SL-004 | Pas d’interprétation automatique des scores | Par conception, périmètre hérité de 0.1.0 | SDK |
| SL-005 | Défauts backend non contournés, variance non mesurée | Par conception / ouvert ; hérité du SDK 0.1.0 et backend 3.3.0 | Méthodologie ; risques additionnels du plan |

Le plan interne backend associe chaque BL-* à ses reproductions, emplacements
source, corrections candidates, tests de régression et critères d’acceptation.
Il n’est pas publié ici ni distribué aux pilotes ; son existence indique
que ces points sont suivis.

Une limite ne passe à « corrigé — vérifié » qu’après une nouvelle exécution
probante et une référence aux preuves. Aucune entrée n’est supprimée ni
affaiblie silencieusement. Une limite absente du registre mérite également
d’être signalée (§5.6).
