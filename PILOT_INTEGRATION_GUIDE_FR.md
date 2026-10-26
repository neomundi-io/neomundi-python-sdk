# Guide d’intégration pilote

[Français](PILOT_INTEGRATION_GUIDE_FR.md) · [English](PILOT_INTEGRATION_GUIDE.md) · [Accueil](README_FR.md)

**SDK 2.0.0 — Évaluation pilote. Développement REST et SSE terminé ; validation réelle du SDK V2 en attente.**

Ce guide accompagne un développeur jusqu’à sa première mesure correctement
interprétée. Il décrit le parcours REST après exécution. Pour générer une
réponse et recevoir les contrôles en direct, consulter le [guide SSE](docs/STREAMING_FR.md) :
les requêtes et les résultats finaux diffèrent.

Le dépôt est public. L’accès à l’API exige une clé transmise séparément ;
la visibilité du code ne règle pas les droits de réutilisation, précisés dans
[LICENSE_NOTICE.md](LICENSE_NOTICE.md).

**Lire les [limites connues](KNOWN_LIMITATIONS_FR.md) avant de communiquer
un chiffre.** Les trois limites backend documentées restent datées :
BL-001 et BL-003 sont inchangées lors de la relecture de la version de mesure
`3.3.1` ; BL-002 est partiellement corrigée et concerne SSE. BL-001 peut
bloquer le premier appel avec un message trompeur ; voir §7.

> **État des preuves.** La compatibilité du contrat REST `POST /v1/govern`
> avec `3.3.1` a été vérifiée par des tests locaux et le rejeu d’une capture
> de production, pas par un appel direct du SDK à un déploiement hébergé.
> Le 22 octobre 2026, la comparaison des sources `3.3.0` / `3.3.1` et le
> rejeu n’ont montré aucun écart de lecture. La qualification réelle de la V2
> reste en attente : voir [les vérifications](docs/VERIFICATION_V2.md).
> Les campagnes historiques citées ci-dessous ne constituent pas de nouveaux tests V2.

## 1. Installer depuis le dépôt public

### Accès

Le clonage HTTPS du dépôt public ne nécessite pas de jeton GitHub.
L’authentification reste nécessaire pour l’API NeoMundi. Elle peut aussi
être nécessaire pour des opérations GitHub d’écriture.

**Le paquet n’est pas publié sur PyPI.** Ne supposez pas que
`pip install neomundi-sdk` installe cette livraison. Utilisez le dépôt
ou un paquet identifié par son empreinte.

### Préparer un environnement isolé

Sous Linux ou macOS :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install "git+https://github.com/neomundi-io/neomundi-python-sdk.git@<commit-sha>"
```

Sous PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install "git+https://github.com/neomundi-io/neomundi-python-sdk.git@<commit-sha>"
```

Remplacez `<commit-sha>` par le commit retenu pour votre pilote.
Une branche comme `main` évolue ; enregistrez le SHA exact installé
avec vos résultats. La publication d’une release est une étape distincte.

Pour travailler sur une copie locale :

```bash
git clone https://github.com/neomundi-io/neomundi-python-sdk.git
cd neomundi-python-sdk
git checkout <commit-sha>
python -m pip install -e .
```

Si vous utilisez SSH, votre clé publique doit être enregistrée auprès de
GitHub. Pour une opération nécessitant un jeton, utilisez votre gestionnaire
d’identifiants ou GitHub CLI (`gh auth login`, puis `gh auth setup-git`).
N’insérez jamais de jeton dans une URL enregistrée dans `requirements.txt`,
un Dockerfile ou l’historique du terminal.

### Prérequis

| Élément | Condition |
|---|---|
| Python | 3.9 ou plus récent ; CI V2 réussie sous 3.9, 3.11, 3.12 et 3.13 |
| Dépendance directe à l’exécution | `httpx` uniquement |

Pas de pydantic, de requests ou de système de plugins dans ce SDK.
Le choix de ne pas convertir silencieusement les types est expliqué
dans les [limites](KNOWN_LIMITATIONS_FR.md).

### Vérifier l’installation

```bash
python -c "import neomundi; print(neomundi.__version__); print(neomundi.API_CONTRACT)"
```

La version attendue est `2.0.0`. Le dictionnaire `API_CONTRACT` contient
notamment les références REST suivantes ; cet extrait n’est pas la sortie
complète de la V2, qui contient aussi les références SSE :

```
2.0.0
{'backend_commit': '68d6057cf620e430e6488da3cfcec9c471c75ed6',
 'measurement_version': '3.3.0',
 'verified_measurement_versions': ('3.3.0', '3.3.1'),
 'normalizer_version': '1.0.0',
 'route': 'POST /v1/govern',
 'contract_source': 'govern-v3/app/models/responses.py, requests.py',
 'openapi_frozen': False}
```

Conservez la sortie complète dans vos notes : elle identifie le contrat
utilisé par le client et les versions de mesure dont la surface REST a
été vérifiée (§6).

## 2. Configurer l’environnement

### Votre clé API

| Préfixe | Usage indiqué |
|---|---|
| `ct_test_` | Clé de test |
| `ct_trial_` | Quota d’essai |
| `ct_live_` | Production ; à écarter d’un pilote sauf cadre explicitement convenu |

Le client refuse les clés ne commençant par aucun de ces préfixes et lève
`ConfigurationError` avant tout appel réseau. Un préfixe ne remplace pas
le choix explicite de l’environnement via `base_url`.

Aucune clé réelle ne doit figurer dans votre dépôt. Les valeurs suivantes
sont des espaces réservés, pas des clés utilisables :

```bash
export NEOMUNDI_API_KEY="ct_test_..."      # valeur transmise séparément
export NEOMUNDI_BASE_URL="https://..."     # URL transmise séparément
```

Sous PowerShell :

```powershell
$env:NEOMUNDI_API_KEY = "ct_test_..."
$env:NEOMUNDI_BASE_URL = "https://..."
```

Avant un commit, vérifier que la clé n’est présente ni dans les sources,
ni dans un notebook, une fixture, une couche d’image conteneur ou un journal CI ;
que `.env` est ignoré par Git ; et que vous connaissez les personnes
qui en détiennent une copie.

Le SDK masque les clés dans ses représentations et teste l’absence de fuite
dans ses sorties. Cela ne protège pas contre votre propre code qui les affiche.

### Construire et fermer le client

```python
import os
from neomundi import NeoMundiClient

client = NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
)
```

Utilisez un contexte pour fermer le pool de connexions HTTP :

```python
with NeoMundiClient(api_key=..., base_url=...) as client:
    result = client.govern(...)
```

### Délais d’attente

Valeurs par défaut : `connect=10s`, `read=60s`, `write=10s`, `pool=10s`.
Une mesure complète sollicite trois évaluateurs ; sur une instance chargée,
le traitement peut durer plusieurs dizaines de secondes. Un délai de lecture
trop court peut déclencher `TimeoutError` avant réception du résultat.

```python
client = NeoMundiClient(api_key=..., base_url=..., timeout=120)
```

### Réessais

**`POST /v1/govern` n’est pas idempotent et ne dispose pas
d’`Idempotency-Key`.** Un appel accepté crée une observation, consomme
quota ou portefeuille, écrit un événement d’usage et remplace la référence
serveur de `delta_g`.

Le SDK ne rejoue donc **jamais un timeout**, même avec une politique de
réessai explicite. Après un timeout, vous ne savez pas si l’appel a déjà
été traité : le rejouer peut doubler l’observation et la consommation.

Exemple de politique explicite, à n’utiliser qu’après vérification du
comportement du service pour le statut retenu :

```python
from neomundi import RetryPolicy

# Réessai limité aux réponses 503 ; valider leur sens sur le service visé.
client = NeoMundiClient(..., retry=RetryPolicy(max_attempts=3, on=(503,)))
```

N’ajoutez pas de boucle de réessai automatique autour d’un timeout.
Pour rapprocher les appels et les réponses, conservez votre propre journal.
Le SSE ne se reconnecte et ne se rejoue jamais automatiquement.

## 3. Effectuer un premier appel REST

Les textes et nombres ci-dessous sont illustratifs. Pour une observation
réelle, utilisez la réponse produite par votre application et ses métriques
effectivement observées.

```python
import os
from neomundi import NeoMundiClient

PROMPT = "How many sides does an equilateral triangle have?"
ANSWER = "An equilateral triangle has three sides of equal length."

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    result = client.govern(
        # Required.
        token_count=18,
        latency_ms=410.0,
        # Strongly recommended: without the texts, the semantic
        # evaluators have nothing to measure.
        llm_prompt=PROMPT,
        llm_response=ANSWER,
        # Optional context.
        cost=0.0004,
        prompt_length=len(PROMPT),
        response_length=len(ANSWER),
        model_name="your-model-name",
    )

print(result.governance.decision)        # ALLOW / FLAG / BLOCK
print(result.governance.decision_basis)  # how that decision was reached
print(result.format_score("g_score"))    # never raises
```

### Un appel après exécution

Vous appelez d’abord votre modèle, puis transmettez les métriques et la
réponse obtenues. **Sur ce parcours REST**, NeoMundi n’appelle pas votre modèle.
Le parcours SSE a un autre fonctionnement.

Les paramètres reprennent exactement les noms du contrat serveur
(`GovernRequest` / `RawMetrics`), sans vocabulaire supplémentaire.

### Deux paramètres à connaître

| Paramètre | Comportement |
|---|---|
| `cost` | Le serveur ne lui attribue pas de devise : il le divise par un plafond par type de source pour obtenir un ratio sans dimension. Utilisez une unité cohérente dans toute l’intégration. |
| `semantic_risk` | Valeur déclarée par l’appelant, remplacée par la mesure serveur si `llm_response` est fourni et que la modération aboutit. La fournir ne la fige pas. |

Sans texte de réponse, aucun contrôle sémantique n’est effectué. L’appel
peut réussir avec `decision_basis = no_check_attempted` :
cela signifie « aucun contrôle tenté », pas « aucun problème détecté ».

## 4. Lire les résultats

### Trois modes d’accès

| Accès | Usage |
|---|---|
| `result.g_score` | Lecture simple ; `None` si l’agrégat n’est pas publié |
| `result.require("g_score")` | Calcul nécessitant la valeur ; `AggregateWithheldError` sinon |
| `result.format_score("g_score")` | Affichage ; chaîne lisible même si la valeur manque |

```python
from neomundi import AggregateWithheldError

try:
    score = result.require("g_score")
except AggregateWithheldError as exc:
    # The measurement was incomplete. This is information, not an error
    # in your code.
    log.info("aggregate withheld: %s", exc)
    score = None
```

### Champs principaux

| Champ | Signification |
|---|---|
| `result.governance.decision` | `ALLOW`, `FLAG` ou `BLOCK` renvoyé par le serveur |
| `result.governance.decision_basis` | Base déclarée de ce résultat |
| `result.g_score` | Agrégat de qualité G |
| `result.g_final` | Composite ESI |
| `result.aggregates_publishable` | `False` : agrégats retenus |
| `result.missing_required_signals` | Signaux requis empêchant leur publication |
| `result.measured_signals` / `result.unmeasured_signals` | État par signal |
| `result.audit.measurement_version` | Version de mesure ayant produit l’observation |

| `decision_basis` | Lecture |
|---|---|
| `measured_thresholds` | Seuils appliqués à des signaux mesurés |
| `incomplete_measurement` | Signal requis non mesuré ; agrégats retenus |
| `no_check_attempted` | Aucun contrôle sémantique lancé |

Enregistrez toujours la base avec la décision. Un `ALLOW` sans contrôle
n’a pas le même sens qu’un `ALLOW` issu de signaux mesurés.
Ces champs ne donnent aucune autorisation d’exécution à votre application.

### Cinq noms à ne pas confondre

Conservez les chemins complets : plusieurs blocs réutilisent des noms avec
des sens différents, parfois inversés.

| Nom | Différence |
|---|---|
| `stability_score` | `quality.stability_score` : 1 = stable ; `metrics.stability_score` : 0 = stable |
| Densité | Deux grandeurs dans deux blocs |
| `Q` | `esi.q_value` et `baseline.esi_q` ne sont pas la même quantité |
| `delta_E` | Définitions et signe à vérifier dans le contrat et les limites méthodologiques |
| Compteurs « tokens » | Certains comptent des fragments, pas des tokens |

N’aplatissez pas ces champs en une seule clé `stability_score`.

### Portée des scores

Les plages effectives historiques ne couvrent pas tout `[0, 1]` :
`stability_score ∈ [0.60 ; 1.00]`, `g_final ∈ [0.40 ; 1.00]`.
Une valeur `g_final = 0.45` est donc proche du plancher, pas simplement
« légèrement sous la moyenne ». Les dérivations sont dans [les limites méthodologiques](docs/LIMITES.md).

Un score de stabilité ne prouve ni la vérité, ni la sécurité, ni l’absence
d’hallucination, ni une capacité prédictive. Il mesure des signaux définis
dans des conditions données.

### Surveiller les écarts de lecture

```python
for w in result.parse_warnings:
    log.warning("contract drift: %s expected %s got %s = %s",
                w.path, w.expected, w.received_type, w.received_repr)
```

Le SDK ne convertit pas automatiquement `"0.5"` en `0.5` ni un booléen
en nombre. Un type inattendu produit un `ParseWarning` et laisse le champ
non renseigné plutôt que de deviner.

Un avertissement est un écart au contrat à examiner et à signaler (§7),
pas à masquer par une conversion permissive. Il n’en a été observé aucun
sur les 11 réponses historiques de l’instance `68d6057`, ni sur la capture
réelle `3.3.1` rejouée le 22 octobre 2026. Cela ne garantit pas votre déploiement.

## 5. Reconnaître une mesure partielle

Quand un signal requis n’a pas été mesuré, le backend retient les agrégats,
dont `g_score`, et en déclare la cause. Le SDK conserve les `null`,
sans les remplacer par zéro ou par une valeur par défaut.

```python
if result.aggregates_publishable is False:
    print("aggregates withheld")
    print("missing:", result.missing_required_signals)
    print("basis:", result.governance.decision_basis)
```

Ou signal par signal :

```python
from neomundi import MeasurementState

for signal in ("coherence_score", "semantic_risk",
               "factual_hallucination_score", "semantic_instability_score"):
    state = result.measurement_state(signal)
    if state is MeasurementState.NOT_MEASURED:
        print(f"{signal}: not measured — {result.unmeasured_reason(signal)}")
    elif state is MeasurementState.MEASURED:
        print(f"{signal}: measured")
    else:
        print(f"{signal}: {state.value}")
```

| État | Signification |
|---|---|
| `MEASURED` | Signal mesuré ; une valeur est publiée |
| `NOT_MEASURED` | Contrôle tenté mais échoué ; cause indiquée |
| `NOT_ATTEMPTED_OR_GATED` | Non tenté ou filtré par le palier ; la réponse ne distingue pas les deux |
| `UNKNOWN` | La réponse ne permet pas d’établir l’état |

L’ambiguïté du troisième état est volontaire : le SDK ne fabrique pas
une distinction absente des données.

### Causes de non-mesure

| Cause | Lecture |
|---|---|
| `*_service_unavailable` | Service non joignable ou délai dépassé |
| `*_malformed_response` | Réponse reçue mais illisible |
| `*_no_input_text` | Texte d’entrée absent |
| `*_empty_verdict`, `*_unparsed_verdict` | Verdict vide ou inexploitable |
| `*_no_score_key`, `*_no_instability_key` | Clé attendue absente |

Un timeout et un service injoignable peuvent recevoir la même cause.
Le SDK ne peut pas les séparer. Sous charge, une hausse de cette cause
justifie d’examiner les délais plutôt que de conclure directement à une panne.

Le terme `measurement_degraded` ne désigne pas un champ du contrat inspecté.
Utilisez les états réellement retournés et `decision_basis`.

### Exploiter une réponse partielle

| Faire | Éviter |
|---|---|
| Enregistrer la mesure partielle et sa cause | Lire un agrégat retenu comme un score favorable |
| Garder les noms des signaux manquants | Remplacer par zéro, une valeur par défaut ou la précédente |
| Décider séparément d’un éventuel nouvel essai | Rejouer automatiquement la requête non idempotente |
| Compter les réponses partielles dans le suivi de couverture | Les retirer silencieusement des statistiques |

Une mesure partielle peut être une réponse HTTP réussie : elle expose
ce qui a pu être mesuré et ce qui manque. L’exclure des statistiques
gonflerait artificiellement la couverture.

## 6. Conserver les preuves

Une mesure réutilisable doit être rattachée à une version, une instance
et un instant.

| À conserver | Source |
|---|---|
| Réponse brute complète | `result.raw` |
| Identifiant | `result.request_id` |
| Version de mesure | `result.audit.measurement_version` |
| Décision et base | `result.governance.decision`, `.decision_basis` |
| État de publication | `result.aggregates_publishable`, `result.missing_required_signals` |
| Avertissements, même vides | `result.parse_warnings` |
| Version du SDK | `neomundi.__version__` |
| Référence de contrat du client | `neomundi.API_CONTRACT` |
| Votre horodatage et votre environnement | Côté application |

Exemple à intégrer à votre politique d’archivage ; `your_timestamp`
doit être défini par votre application :

```python
import json, neomundi

record = {
    "raw": result.raw,
    "request_id": result.request_id,
    "measurement_version": result.audit.measurement_version,
    "decision": result.governance.decision,
    "decision_basis": result.governance.decision_basis,
    "aggregates_publishable": result.aggregates_publishable,
    "missing_required_signals": result.missing_required_signals,
    "parse_warnings": [
        {"path": w.path, "expected": w.expected,
         "received_type": w.received_type, "received_repr": w.received_repr}
        for w in result.parse_warnings
    ],
    "sdk_version": neomundi.__version__,
    "sdk_contract": neomundi.API_CONTRACT,
    "observed_at": your_timestamp,
    "environment": "pilot-test",
}
```

`result.to_dict()` restitue les données brutes reçues, sans perte de champs.

### Version de mesure et comparabilité

La version de mesure se lit dans `result.audit.measurement_version`.
`GET /v1/health` indique la version de l’application, historiquement
`3.0.0`, pas celle des mesures.

```python
served = result.audit.measurement_version

if served not in neomundi.API_CONTRACT["verified_measurement_versions"]:
    # CAN THIS CLIENT READ IT? Unverified contract: fields may have
    # changed meaning. Stop, and report (§7).
    log.error("unverified measurement version: %s", served)

elif served != neomundi.API_CONTRACT["measurement_version"]:
    # MAY THESE NUMBERS SHARE A SERIES? No — not with a series produced
    # under a different measurement version. Parsing is safe; the
    # comparison is not.
    log.info("served %s, derived from %s — record it with the observation",
             served, neomundi.API_CONTRACT["measurement_version"])
```

Le premier contrôle demande si le client sait lire le contrat.
Le second demande si les observations peuvent partager une série.
Le déploiement relu le 22 octobre servait `3.3.1`, le contrat de référence
du client provenait de `3.3.0` : lecture REST compatible, version à conserver
et séries à ne pas mélanger automatiquement.

Aucune spécification OpenAPI figée n’est fournie
(`openapi_frozen: False`). Ne perdez ni le commit de référence ni les
versions effectivement retournées.

### Vérifier votre déploiement avant une campagne

Sur des appels autorisés dans l’environnement visé :

1. Vérifier l’absence de `parse_warnings`.
2. Vérifier que la version de mesure figure dans `verified_measurement_versions`, puis l’enregistrer.
3. Rechercher les champs racine inconnus.
4. Vérifier qu’un appel sans `llm_response` déclare `no_check_attempted` ; ne pas confondre absence de contrôle et mesure complète.

Si les trois premiers contrôles échouent, examiner et signaler l’écart
avant de collecter une série.

Sur la capture `3.3.1` étudiée, les empreintes
`prompt_template_hash`, `inference_config_hash` et `config_fingerprint`
n’étaient renseignées que pour les deux signaux du juge factuel.
`stability_score`, `coherence_score` et `semantic_risk` étaient
`measured` avec ces trois empreintes à `null`. Impossible donc de
démontrer l’identité des configurations sur ces trois signaux.

La sonde factuelle peut être `degraded` alors qu’une mesure ponctuelle
déclare le signal `measured` : un écart entre nom configuré et catalogue
a été documenté. Ne présumez pas la cause d’un nouvel état dégradé ;
lisez les états des signaux dans les réponses et conservez les deux constats.

### Ne pas archiver de secrets

N’enregistrez pas de clé API dans les preuves, ni de données personnelles
en `metadata` qui ne devraient pas figurer dans une archive de mesure.
Aucun secret n’avait été détecté dans les réponses de la campagne
historique ; cela ne dispense pas de contrôler vos propres données.

## 7. Signaler une anomalie

| Observation | Suite |
|---|---|
| `parse_warnings` non vide | Signaler l’écart de contrat |
| Champ racine inconnu | Signaler l’évolution du backend |
| Version hors liste vérifiée | Signaler avant de s’appuyer sur la lecture |
| `3.3.1` au lieu de `3.3.0` | Enregistrer la version ; sa surface REST est vérifiée, sans autoriser le mélange des séries |
| Agrégat `null` sans explication | Signaler |
| `TypeError` / `AttributeError` interne au SDK | Signaler |
| `decision_basis` absent ou inattendu | Signaler |
| Deux requêtes REST identiques, décisions différentes | Fournir les deux réponses brutes expurgées |
| Limite déjà documentée se comportant comme annoncé | Consulter d’abord le registre |

Joindre : réponse brute expurgée sans détruire les champs de mesure,
`request_id`, version du SDK, `API_CONTRACT`, appel sans clé,
résultat attendu/observé et fréquence de reproduction.

**Ne joindre aucune clé, même partiellement.** Le masquage du SDK ne
protège pas un copier-coller d’historique de terminal.

Le dépôt et ses issues sont publics. Réservez les issues aux reproductions
assainies et non sensibles. Transmettez les réponses contenant des données
confidentielles par le canal convenu avec votre contact NeoMundi.

Un écart entre contrat attendu et réponse reçue est un constat d’audit,
pas nécessairement un défaut du client. Le signaler préserve une information
qu’un contournement local pourrait masquer.

## 8. Lire le registre des limites

[KNOWN_LIMITATIONS_FR.md](KNOWN_LIMITATIONS_FR.md) détaille :

| Section | Contenu |
|---|---|
| §1 | État du SDK et portée des suites de tests |
| §2 | Fonctionnalités vérifiées par exécution, rejeu ou simulation |
| §3 | BL-001, BL-002, BL-003 : états, périmètres, causes, preuves et conduite à tenir |
| §4 | SL-001 à SL-005 : limites du client |
| §5 | Conseils de lecture et d’intégration |
| §6 | Compatibilité des versions |
| §7 | Cycle de suivi et vocabulaire des états |

| Limite | Résumé |
|---|---|
| BL-001 | Compte TRIAL/ACTIVE : 402 de quota épuisé puis clés suspendues et 401, malgré un quota non consommé. Faire examiner le compte, pas remplacer aveuglément la clé. |
| BL-002 | Trajectoire SSE sensible au découpage réseau. Correction partielle en `3.3.1` pour une classe de décisions ; trajectoire publiée toujours sensible au découpage. |
| BL-003 | `delta_g` publié même si l’agrégat est retenu. Vérifier l’état de publication avant toute interprétation. |

Le SDK ne contourne aucune de ces limites.

Autres lectures : [accueil français](README_FR.md),
[guide SSE](docs/STREAMING_FR.md), [limites méthodologiques](docs/LIMITES.md),
[contrat REST](docs/CONTRAT_API.md).

## État de validation

**V2 :** 282 tests hors ligne réussis, 12 captures historiques optionnelles
absentes ; CI réussie sous Python 3.9, 3.11, 3.12 et 3.13.
Développement terminé et fusionné ; qualification réelle REST/SSE du SDK V2
installé encore en attente.

**Historique :** les suites antérieures comptaient 347 tests avec les
11 réponses capturées de l’instance `68d6057`, ou 225 réussis et 12 ignorés
sans ces captures. Elles couvraient les trois bases de décision et ne
présentaient ni écart de type ni champ inconnu. Le 22 octobre, une réponse
réelle `3.3.1` a été rejouée sans écart, après comparaison des sources.
Ces nombres décrivent des périmètres historiques différents de la suite V2.

Les tests simulés ne qualifient pas l’authentification, les quotas, les délais
et les erreurs du service déployé. La tenue sous charge et la variance du
juge factuel à entrée constante ne sont pas caractérisées ici.
Une différence entre deux scores ne peut donc pas être déclarée
statistiquement significative sur cette seule base.
Aucune validation supplémentaire par un pilote n’est revendiquée.
