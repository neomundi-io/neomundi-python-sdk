# Migrer vers le SDK 2.0.0

La version du paquet devient 2.0.0. Elle ne change pas la version des
mesures de l'API et ne certifie pas un nouveau déploiement du backend.

Les imports, `NeoMundiClient.govern(...)`, ses paramètres REST et
`GovernResult` restent disponibles. Les régressions REST existantes sont
exécutées avec les nouveaux tests SSE. Une requête REST avec un coût ou
une latence NaN/infini est désormais refusée avant le transport, de même
qu'un délai numérique non fini.

Pour le flux SSE, ajouter `client.stream(...)` (alias `govern_stream`).
Il faut fournir un prompt, un modèle et une clé fournisseur distincte de
la clé NeoMundi. Lire [STREAMING.md](STREAMING.md) avant un appel réel :
cette route génère un texte et peut consommer un quota et une facturation
fournisseur. Le SDK ne choisit pas OpenAI par défaut.

Utiliser un contexte `with`. Afficher `event.content` uniquement pour les
événements `chunk`, puis lire `stream.result`. Ne pas concaténer le texte
de `done` aux chunks et ne pas soumettre automatiquement cette même
réponse une seconde fois à REST pour « finir » le flux.

Les erreurs HTTP gardent leurs classes. Les erreurs après HTTP 200
utilisent `StreamServerError`, `StreamInterruptedError` ou
`StreamProtocolError`, toutes sous `StreamError`. Aucun réessai de SSE
n'est activé par la politique de réessai REST.

Le client reste synchrone. Aucun serveur MCP, plugin, ordonnanceur,
service hébergé ou secret n'est installé par cette mise à jour. Aucun
choix de licence ni publication PyPI n'est effectué.
