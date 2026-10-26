# Audit et réparation du SDK — 26 octobre 2026

## Constat initial

Base locale : branche `verif/compat-3.3.1`, commit SDK `1e510c4`.
Version de paquet 0.1.0. La branche GitHub principale a été relue à
`e6d552fb621ffeb5c4527b58f36bd985c239f0c9` (25/10) : ses liens Station
et flux de données sont conservés. La compatibilité REST 3.3.1 de la
branche locale est intégrée au lot V2, pas abandonnée. Seul `POST /v1/govern` était implémenté et le
README annonçait explicitement l'absence de SSE. Des modèles REST, des
erreurs typées et une politique de réessai non automatique existaient déjà.

Le backend local de référence est au commit
`aeff13cca717205c9ebbc83c5755ba6a22b284bb`.

| Source | SHA-256 |
|---|---|
| `govern-v3/app/api/v1/streaming.py` | `7b04cd943fbb3b0c959a679cfc74b539a4f59cc1b298bd35ed8a22cd9b58f6bf` |
| `govern-v3/app/models/requests.py` | `d114058048c915f47b6ec3d007b8c751d82557d2832f7297850c6771d927c8b8` |

## Points à corriger

| Écart | Réparation V2 | Vérification |
|---|---|---|
| Transport SSE absent | `stream()` et alias `govern_stream()` | Route, authentification et corps `StreamRequest` testés |
| Deux parcours confondus possibles | Résultats REST/SSE distincts | Aucun faux bloc REST ni métrique d'entrée fabriquée |
| Risque de texte doublé | Assemblage des chunks comparé au récapitulatif | Unicode, longueur, octets et empreinte contrôlés |
| Erreur après HTTP 200 | Exceptions de flux dédiées | Événement error et interruption explicitement testés |
| Rejeu non idempotent | Aucun reconnect ou retry SSE | Un seul POST malgré RetryPolicy et interruption |
| Fragilité du framing | Parseur UTF-8 incrémental borné | BOM, CR/LF/CRLF, multiligne, commentaire et fragmentation |
| Données et états manquants | Conservation du payload et des null | Champs inconnus, mesures incomplètes et compteurs préservés |
| Ressources ouvertes à l'abandon | Contexte et close explicite | Fin, exception, annulation, client HTTP externe |
| Échos de clés dans les erreurs | Diagnostics expurgés / événement de succès retenu | Clés factices recherchées dans erreurs et repr |
| Nombres non finis acceptés côté REST | Refus local coût, latence et timeout non finis | Tests sans émission réseau |

## Plan de réparation appliqué

1. Conserver le parcours REST et sa suite de régression.
2. Ajouter une API SSE séparée, sans nouvelle dépendance de production.
3. Tester la livraison réellement progressive : le premier événement ne
   doit pas attendre la fin du flux ni un tampon de taille fixe.
4. Ajouter les tests de terminaison, intégrité, limites et absence de rejeu.
5. Actualiser version, CI, exemples et documentation ; construire et
   vérifier l'installation du paquet.

## Limites de cette vérification

Les tests utilisent un transport HTTPX simulé et des événements
synthétiques dérivés du code. Ils ne constituent pas des acquisitions
scientifiques, des appels du SDK contre l'API hébergée, ni une validation
de tous les fournisseurs. Les captures REST optionnelles non suivies
dans Git ne sont pas recréées : leurs tests peuvent rester ignorés.

Le rapport de livraison précise les commandes et résultats réellement
exécutés. La matrice Python de CI n'est validée que lorsqu'elle a tourné ;
un test local sur Python 3.12 ne démontre pas les autres versions.
Résultats exécutés : [VERIFICATION_V2.md](VERIFICATION_V2.md).

La licence non arbitrée et les limites backend historiques ne sont pas
changées par l'ajout de SSE. Aucun correctif serveur ou déploiement n'est
inclus. La métrologie de la trajectoire et son éventuelle dépendance au
framing restent des propriétés du backend, pas des réparations du SDK.
