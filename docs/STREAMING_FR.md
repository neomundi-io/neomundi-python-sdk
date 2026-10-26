# REST et SSE dans le SDK 2

[Français](STREAMING_FR.md) · [English](STREAMING.md) · [Accueil](../README_FR.md)

Le SDK est synchrone. SSE permet de recevoir un flux progressif ; cela ne
signifie pas que le client Python utilise `async/await`. Un client
asynchrone n’est pas inclus dans cette version.

| API | Méthode Python | Fonctionnement | Résultat final |
|---|---|---|---|
| `POST /v1/govern` | `client.govern(...)` | Transmettre une exécution déjà produite par votre application | `GovernResult` |
| `POST /v1/govern/stream` | `client.stream(...)` / `client.govern_stream(...)` | L’API NeoMundi appelle le fournisseur choisi et transmet la génération et les contrôles en direct | `StreamResult` après `done` |

REST ne génère pas de nouvelle réponse LLM. Omettre `llm_response` reste
possible, mais ne prouve pas que des contrôles sémantiques ont été mesurés.
SSE exige une clé fournisseur et un modèle ; ce n’est pas un abonnement
ne transportant que des métriques.

La clé NeoMundi est envoyée dans `X-API-Key` ; la clé fournisseur est
envoyée dans le corps JSON à l’API NeoMundi choisie. Les coûts et les
implications pour la confidentialité diffèrent donc du parcours REST après
exécution.

## Lire les événements en direct

```python
import os
from neomundi import NeoMundiClient, StreamError

with NeoMundiClient(
    api_key=os.environ["NEOMUNDI_API_KEY"],
    base_url=os.environ["NEOMUNDI_BASE_URL"],
) as client:
    try:
        with client.stream(
            prompt="Votre question",
            provider=os.environ["LLM_PROVIDER"],
            model=os.environ["LLM_MODEL"],
            provider_api_key=os.environ["LLM_PROVIDER_API_KEY"],
            max_tokens=256,
            temperature=0,
        ) as stream:
            for event in stream:
                if event.event == "chunk":
                    print(event.content, end="", flush=True)
                # Les autres contrôles restent accessibles dans event.data.
            result = stream.result
            assert result is not None
            print(result.request_id, result.decision_basis)
            # La réponse conserve les null explicites et les champs inconnus.
            payload = result.to_dict()
    except StreamError as error:
        # error.partial_text est une réponse partielle, pas une mesure.
        # Ne la stockez que selon votre politique de gestion des données.
        print(type(error).__name__)
```

Créer le flux valide les paramètres sans contacter le serveur. Entrer dans
son contexte ou demander son premier événement déclenche exactement un POST.
Même un contexte dont les événements ne sont pas lus ouvre la requête et
peut consommer un quota. `collect()` consomme le flux et retourne le
`StreamResult` final.

## Vérifier la fin et l’intégrité

Le backend transmet la réponse dans `chunk.content`, puis de nouveau dans
`done.response_text`. **Ce dernier contient le récapitulatif complet,
pas un fragment supplémentaire.** Le SDK compare les deux ; il n’ajoute
jamais ce récapitulatif aux fragments assemblés.

Lorsqu’ils sont fournis, `response_length` (caractères Unicode Python),
`response_bytes` (octets UTF-8) et `response_sha256` sont vérifiés.
Si un contrôle fourni ne correspond pas, `StreamProtocolError` est levée
et aucun résultat final n’est publié. `integrity_verified` vaut `True`
uniquement si les trois métadonnées sont présentes et concordantes.
Le SDK n’invente pas celles qui manquent. L’égalité entre les fragments
assemblés et le récapitulatif final est toujours vérifiée.

L’intégrité du transport ne prouve ni la validité scientifique, ni la
disponibilité des évaluateurs, ni une autorisation d’exécuter une action.
Les scores `null` restent `null`. Une mesure `incomplete` peut être
transportée par une réponse SSE reçue entièrement. À l’inverse, un transport
interrompu n’est pas une mesure incomplète : aucun résultat final réussi
n’est disponible à interpréter.

`StreamResult.payload` contient la véritable réponse finale SSE ; elle
n’est pas convertie en résultat REST. `result.to_dict()` fournit une copie
profonde indépendante. Le SDK conserve les unités et les champs des contrôles
provisoires, y compris les compteurs dont les noms historiques désignent
des fragments plutôt que des tokens.

## Gérer les erreurs et les connexions

- Les erreurs HTTP avant le début du flux utilisent les classes d’erreur HTTP du parcours REST.
- Un événement SSE `error` lève `StreamServerError`, même après HTTP 200.
- Une fin de connexion sans `done`, une erreur réseau en cours de flux ou une interruption déclarée par le serveur lève `StreamInterruptedError`, avec le texte reçu disponible dans `partial_text`.
- Un UTF-8 invalide, un JSON qui n’est pas un objet ou contient des nombres non finis, des champs `chunk` ou `done` invalides, une différence d’assemblage ou un dépassement de taille lève `StreamProtocolError`.
- La sortie du contexte, la fin normale et les erreurs ferment la réponse HTTP. Si vous arrêtez la lecture sans `with`, appelez explicitement `stream.close()`.
- Un `httpx.Client` fourni par l’appelant n’est pas fermé par le SDK. Les redirections ne sont pas suivies pour ce POST contenant des clés.

Il n’y a **aucune reconnexion ni aucun réessai automatique**, même si le
client REST utilise une `RetryPolicy`. Recevoir des métadonnées `retry:`
ou `id:` n’autorise pas à rejouer la requête. Un rejeu peut créer une
seconde génération, une seconde mesure, une nouvelle consommation de quota
et une nouvelle facture fournisseur. Le SDK ne met pas en œuvre de reprise
`Last-Event-ID` pour un POST dont le contrat ne documente pas cette reprise.

Les limites par défaut sont de 1 Mio par événement décodé et 16 Mio pour
le texte de réponse assemblé. Elles se règlent avec `max_event_bytes`
et `max_response_bytes`. La limite par événement peut être atteinte en
premier, car `done` répète la réponse complète.

Les résultats conservés et le texte partiel peuvent contenir des données
sensibles de votre application. Le SDK ne les enregistre ni ne les journalise
automatiquement. Si le serveur renvoie une clé connue dans un événement
réussi, cet événement est retenu ; les clés connues sont masquées dans les
diagnostics d’erreur HTTP/SSE. Les journaux créés par l’utilisateur, les
hooks HTTPX et les transports fournis par l’appelant restent sous sa
responsabilité.

## Contrat et portée des vérifications

L’implémentation a été relue localement au commit backend
`aeff13cca717205c9ebbc83c5755ba6a22b284bb` :
`app/models/requests.py` (`StreamRequest`) et `app/api/v1/streaming.py`.
Leurs empreintes SHA-256 figurent dans [l’audit](AUDIT_SDK_V2.md).

Les données de test hors ligne sont synthétiques et dérivées de ces sources ;
ce ne sont pas des captures de production. Aucun nouvel appel SSE hébergé
ni génération fournisseur n’a été effectué avec le SDK pour qualifier
cette version. La compatibilité du déploiement exige un test contrôlé
distinct contre l’environnement visé. Consulter [l’état des vérifications](VERIFICATION_V2.md).

Références du parseur : [interprétation SSE du standard HTML](https://html.spec.whatwg.org/multipage/server-sent-events.html#event-stream-interpretation)
et [streaming HTTPX](https://www.python-httpx.org/quickstart/#streaming-responses).
