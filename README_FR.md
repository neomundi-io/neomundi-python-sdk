# SDK Python NeoMundi 2

[Français](README_FR.md) · [English](README.md)

[![PyPI version](https://img.shields.io/pypi/v/neomundi?style=flat-square)](https://pypi.org/project/neomundi/) ![REST](https://img.shields.io/badge/transport-REST-blue) ![SSE](https://img.shields.io/badge/transport-SSE-blue) ![Validation](https://img.shields.io/badge/validation-REST_SSE_live_pass-green)

**Version 2.0.0 — publiée sur [PyPI](https://pypi.org/project/neomundi/). REST et SSE disponibles ; qualification réelle de portée pilote.**

Intégrez les mesures NeoMundi à votre infrastructure, ou
[découvrez Station](https://github.com/neomundi-io/neomundi-station-public).
Consultez ses conditions d’accès et sa disponibilité actuelles ; son tableau de bord évolue séparément.
[Comprendre les mesures](https://github.com/neomundi-io/neomundi-metric-contract) ·
[Flux de données et confidentialité](https://github.com/neomundi-io/neomundi-io-data-protection)

## Où en sommes-nous ?

Le développement de la V2 est terminé et [fusionné dans la branche principale](https://github.com/neomundi-io/neomundi-python-sdk/pull/3).
Les deux modes REST et SSE sont disponibles dans le code du SDK.

| Étape | État |
|---|---|
| Distribution publique PyPI | Publiée le 14/11/2026 ; installation et import vérifiés sur Windows avec Python 3.12.10 |\n| Développement REST et SSE | Terminé |
| Tests hors ligne | Suite de régression verte dans GitHub CI ; captures historiques optionnelles suivies séparément |
| Tests automatisés GitHub | Réussis sous Python 3.9, 3.11, 3.12 et 3.13 |
| Validation réelle REST et SSE du SDK V2 installé | Les deux réussies le 13/11/2026, dans les limites précisées ci-dessous |

Le 13/11/2026, le SDK installé depuis sa roue a réussi un appel REST
(mesure complète, couverture 1.0, cinq signaux mesurés) et un appel SSE
(sept événements, événement final présent, intégrité vérifiée).
Le rapport complet et les identifiants de requête restent privés.
Les schémas REST/SSE publics ont également été comparés octet par octet
aux schémas servis par l'API via
[GitHub Actions](https://github.com/neomundi-io/neomundi-python-sdk/actions/runs/43526131929).
Ces résultats n'établissent ni la validité scientifique, ni la compatibilité
avec tous les fournisseurs, ni les cas réellement dégradés sous 3.5.0.
Voir [la portée de la qualification 3.5.0](docs/COMPATIBILITY_350.md).
La publication PyPI est terminée ; l'intégration à Station reste une étape distincte.

## Choisir son mode

| Votre besoin | Méthode Python | Route API |
|---|---|---|
| Mesurer une exécution déjà produite par votre application | `client.govern(...)` | `POST /v1/govern` |
| Générer une réponse via l’API et recevoir les contrôles progressivement | `client.stream(...)` | `POST /v1/govern/stream` |

Les deux routes utilisent des requêtes et des résultats différents.
SSE n’est pas un abonnement aux résultats REST. Le client Python est
synchrone dans les deux modes ; cette version ne propose pas de client
`async/await`.

NeoMundi fournit des mesures et leur provenance, y compris lorsque certaines
mesures sont indisponibles. L’interprétation et l’autorité d’exécution restent
dans votre application. Le SDK n’ajoute pas de seuils de décision et ne
remplace pas les valeurs `null` par zéro.

## Installer le SDK

Python 3.9 ou plus récent ; `httpx` est la seule dépendance directe à l’exécution.
Le SDK est **publié sur [PyPI](https://pypi.org/project/neomundi/)** sous le nom `neomundi` (version `2.0.0`), sans changement de l'import Python `import neomundi`.
Le SDK est placé sous [licence Apache-2.0](LICENSE), sous réserve de vérification des droits des contributeurs : voir [les limites de licence](LICENSE_NOTICE.md). L’**API Runtime Measurement hébergée reste propriétaire et commerciale** : clé autorisée, crédits/quotas et conditions de service s’appliquent. Le SDK libre n'accorde pas d'accès gratuit au service.

Depuis un terminal, après installation de Git et Python :

```sh
python -m pip install neomundi==2.0.0
# Pour les contributeurs souhaitant installer depuis les sources :
git clone https://github.com/neomundi-io/neomundi-python-sdk.git
cd neomundi-python-sdk
python -m pip install .
# Ou installer un paquet construit localement :
python -m pip install dist/neomundi-2.0.0-py3-none-any.whl
```

Le SDK ne contient aucune clé API, ne recherche pas automatiquement de clés
et ne les enregistre pas. Choisissez explicitement l’adresse de votre API avec
`base_url`.

Les exemples suivants lisent les variables d’environnement du processus :
`NEOMUNDI_API_KEY` pour la clé NeoMundi et `NEOMUNDI_BASE_URL` pour
l’adresse de l’API. Le mode SSE demande également `LLM_PROVIDER`,
`LLM_MODEL` et `LLM_PROVIDER_API_KEY`. Ne placez aucune clé réelle dans
vos fichiers versionnés.

## REST : mesurer une réponse existante

```python
import os
from neomundi import NeoMundiClient

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    result = client.govern(
        token_count=128,          # consommation réellement observée
        latency_ms=842.0,        # latence réellement mesurée
        llm_prompt="Quelle est la capitale de la France ?",
        llm_response="Paris.",
    )
    print(result.request_id, result.format_score("g_score"))
```

Cet appel transmet une réponse existante ; il ne génère pas de nouvelle
réponse. Les nombres sont illustratifs : remplacez-les par les observations
de votre application.

Vous pouvez transmettre uniquement des métriques, mais cela ne prouve pas
que des contrôles sémantiques ont été effectués. Les champs optionnels laissés
à `None` sont omis, sans être silencieusement remplacés par zéro.

## SSE : recevoir la réponse et les contrôles en direct

```python
import os
from neomundi import NeoMundiClient, StreamError

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    try:
        with client.stream(
            prompt="Explique le sujet choisi.",
            model=os.environ["LLM_MODEL"],
            provider=os.environ["LLM_PROVIDER"],
            provider_api_key=os.environ["LLM_PROVIDER_API_KEY"],
            max_tokens=256,
        ) as stream:
            for event in stream:
                if event.event == "chunk":
                    print(event.content, end="", flush=True)
            result = stream.result
            assert result is not None
            print(result.request_id, result.integrity_verified)
    except StreamError as error:
        print(type(error).__name__)  # aucun réessai automatique
```

L’API de streaming reçoit la clé fournisseur dans le corps JSON de la
requête, puis appelle le fournisseur choisi. Cela peut entraîner un coût
fournisseur et une consommation de quota NeoMundi.
Le SDK ne sélectionne ni OpenAI ni un modèle par défaut.

Utilisez `with` pour fermer le flux, notamment si vous interrompez sa lecture.
Le champ `done.response_text` répète la réponse complète :
**ne l’ajoutez pas aux fragments déjà reçus**.
Le SDK vérifie leur assemblage et les métadonnées de longueur, d’octets
et d’empreinte lorsqu’elles sont fournies.

Les erreurs après HTTP 200, l’absence d’événement final et les flux tronqués
sont signalés explicitement. Aucun flux n’est reconnecté ou rejoué, même
si des réessais REST ont été activés.

## Ce qui est vérifié et ce qui reste à vérifier

Le contrat SSE de la V2 provient du code backend inspecté au commit
`aeff13c`. Les tests utilisent des flux synthétiques et fragmentés avec
un transport simulé. Un test réel borné de REST et un de SSE ont été réussis le 13/11/2026
avec une roue V2 installée ; les limites de cette qualification sont
consignées dans [COMPATIBILITY_350.md](docs/COMPATIBILITY_350.md).
Ces essais ne qualifient ni tous les fournisseurs, ni les cas réellement
dégradés, ni la comparabilité scientifique.

Le résultat SSE `StreamResult` conserve sa propre réponse brute ; il n’est
pas converti en résultat REST `GovernResult`.
Un transport terminé peut contenir une mesure incomplète.
Les contrôles d’intégrité ne prouvent pas la validité scientifique.
Le SDK ne corrige pas les défauts de métriques, de trajectoires, de quotas
ou d’évaluateurs du backend.

## Pour aller plus loin

Les trois guides principaux sont disponibles en français et proposent
un lien vers leur version anglaise. Les noms de méthodes et de champs
restent ceux du SDK.

- [Fonctionnement SSE, erreurs, intégrité et limites](docs/STREAMING_FR.md)
- [Passer de la version 0.1 à la V2](docs/MIGRATION_V2.md)
- [Audit et réparations livrées](docs/AUDIT_SDK_V2.md)
- [Résultats des vérifications et état des tests réels](docs/VERIFICATION_V2.md)
- [Limites connues du backend et du SDK](KNOWN_LIMITATIONS_FR.md)
- [Guide pilote REST](PILOT_INTEGRATION_GUIDE_FR.md)
- [Contrat REST inspecté](docs/CONTRAT_API.md) · [Limites des mesures](docs/LIMITES.md)
- [Exemple SSE hors ligne](examples/04_streaming_sse.py)

Pour exécuter les tests et l’exemple simulé, puis construire les paquets :

```sh
python -m pip install -e ".[dev]"
python -m pytest tests
python examples/04_streaming_sse.py
python -m build
```

**La version 2.0.0 désigne le SDK, pas une version de mesure 2.0.0.**
Vérifiez la version de mesure effectivement retournée par votre déploiement
avant de comparer des observations.
