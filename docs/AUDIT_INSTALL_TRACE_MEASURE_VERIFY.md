# Audit du 2026-11-15 — INSTALL → TRACE → MEASURE → VERIFY

Issue de référence : [#20](https://github.com/neomundi-io/neomundi-python-sdk/issues/20).

Ce document est le relevé de ce qui **existe**, de ce qui **manque** et de ce
qui est **proposé**, avant toute ligne de code. Chaque affirmation nomme sa
source. Quand une affirmation n'a pas pu être établie, elle est marquée
**NON ÉTABLI** plutôt que déduite.

---

## 0. Ce qui a servi de source

| Source | Nature | Date de relevé |
|---|---|---|
| `neomundi-python-sdk` `main` = `210eb29` | code du SDK | 2026-11-15 |
| `20261017_API/govern-v3` | code du backend, copie active | 2026-11-15 |
| `GET https://api.neomundi.io/v1/contracts/govern-rest-1.0.json` | **contrat déployé**, route publique et non facturée | 2026-11-15 |
| `GET https://api.neomundi.io/v1/contracts/govern-sse-1.0.json` | idem | 2026-11-15 |
| `GET /v1/health`, `GET /v1/rgc/schema`, `GET /v1/rgc/jwks`, deux sondes 404 de vérification | routes publiques | 2026-11-15 |
| `pypi.org/pypi/neomundi/json` et `.../neomundi-evidence-verify/json` | métadonnées publiées | 2026-11-15 |
| Rapport de qualification réelle du SDK V2 | hors dépôt | 2026-11-13 |

**Preuve que le contrat lu est bien le contrat déployé :** les deux fichiers
servis par la production sont **identiques octet pour octet** à
`app/contracts/schemas/` du dépôt backend
(`bcd5588edc92376f59d57ad9ae155b09f5ab3fe49e15ece6cb2fe5adbf4835ef` et
`358fc2ec1869471896d08c8e2cc0855b15def6433340a0506dae180733c7fefe`). Ces
fichiers sont **générés** depuis `GovernResponse`, et un test backend éprouve
leur égalité à l'octet. Le modèle de réponse déployé est donc celui de cette
copie du dépôt. Les deux empreintes sont mesurées à chaque exécution de la
suite (`tests/test_wire_contract_deploye.py`), et les fixtures sont les
fichiers téléchargés eux-mêmes.

⚠ **Ce raisonnement couvre la réponse, pas la requête.** `requests.py` n'est
pas exporté en schéma, et `/openapi.json` comme `/docs` rendent **404** en
production. Voir §2.

---

## 1. TRACE

### Existant

| Fait | Source |
|---|---|
| `metadata: Dict[str, Any]`, décrit « opaque metadata forwarded for tracing » | `app/models/requests.py:224` |
| `audit.trace_id` dans la réponse | `app/models/responses.py:828` |
| `request_id` : UUID complet, dans le corps **et** dans l'en-tête `X-Request-ID` posé sur toute réponse | `app/main.py` |
| `GET /v1/govern/{request_id}` permet de relire une observation | `app/api/v1/governance.py:820` |

### Manquant — et c'est le fait structurant

🔴 **Il n'existe aucune route de traçage indépendante de la mesure.** Les huit
routeurs enregistrés (`app/main.py:_include_routers` : `streaming`, `demo`,
`governance`, `reports`, `health`, `contracts`, `exports`, `rgc`) ont été
relevés route par route. Aucun point d'entrée n'accepte une interaction sans la
mesurer. `POST /v1/govern` **est** la seule voie d'entrée, et elle débite un
quota (`enforce_trial_quota`, `governance.py:174`).

🔴 **`metadata` est accepté et abandonné.** La route ne le lit jamais : l'objet
persisté est `response.model_dump()` augmenté d'un `_audit_context` qui ne
porte que des **longueurs** (`governance.py:533-564`). Un identifiant de
corrélation transmis là n'est ni republié, ni stocké. Conséquence :
**la corrélation ne peut être établie que chez l'appelant**, en appariant son
identifiant au `request_id` rendu.

🔴 **`audit.trace_id` n'est pas un identifiant.** Il vaut
`f"trace-{request_id[:8]}"` (`governance.py:1573`, `streaming.py:1422`) : huit
caractères hexadécimaux, donc **non unique par construction**. Le contrat RGC
en calcule un second, de forme `traceparent` W3C, qui ne remplace pas le
premier (`app/rgc/builder.py:56-62`).

🔴 **Le 200 de `POST /v1/govern` ne confirme aucun enregistrement.** L'écriture
du journal est enveloppée dans un `try/except` qui journalise et continue
(`governance.py:575`), et un commentaire du backend l'énonce : « the REST
response makes no persistence claim ». Le contrat REST ne publie donc **aucun**
champ de persistance.

### Existant, et sous-exploité — la découverte utile de cet audit

🟢 **La route SSE, elle, confirme l'enregistrement.** Le contrat SSE déployé
publie `log_persisted` (booléen ou nul) et `log_write` (chaîne ou nulle), que
le contrat REST ne porte pas. Et la sémantique est fine :
**les deux clés sont absentes sur le chemin nominal**, le serveur ne les
émettant que lorsque l'écriture n'a pas été une insertion propre
(`streaming.py:1644-1653`). `already_exists` garde `log_persisted` vrai,
`already_exists_divergent` le met à faux.

C'est **la seule confirmation d'enregistrement de toute la plateforme**, et le
SDK 2.0.0 ne l'exposait pas.

### Proposé, et implémenté dans cette branche

`client.trace()` + `TraceRecord` (`src/neomundi/trace.py`) :

- chronomètre `time.monotonic()` autour du bloc applicatif → `latency_ms`
  devient une valeur **mesurée** ;
- `token_count` reste **exigé de l'appelant** : sans lui, `ConfigurationError`
  et **aucune requête émise** ;
- `registered = None` sur REST, `True`/`False` seulement par
  `TraceRecord.from_stream` ;
- `acknowledged` (le serveur a répondu avec un `request_id`) est distinct de
  `registered` ;
- `submit=False` n'ouvre aucune socket ;
- un échec applicatif n'émet **rien** et ne masque pas l'exception ;
- refermer deux fois n'émet qu'une requête — la route n'est pas idempotente ;
- `TraceRecord` ne porte **ni prompt ni réponse**, seulement leurs longueurs,
  si bien que `to_dict()` est journalisable par construction.

### Proposé et NON retenu

- **Une route `POST /v1/trace` côté backend.** Elle impliquerait une table, une
  politique de rétention, une règle de facturation et une décision RGPD. Rien
  de tout cela n'est arbitrable depuis ce dépôt, et l'issue #20 demande de
  formaliser le contrat *avant* d'implémenter. **Non engagé.**
- **Rendre `registered` vrai sur REST.** Ce serait inventer une confirmation.
- **Une estimation de `token_count`.** Elle entrerait dans `cost_proxy` et dans
  la densité volumétrique, donc dans des chiffres présentés comme mesurés.

---

## 2. MEASURE

### Existant

`client.govern()` et `client.stream()` fonctionnent et ont été **qualifiés en
direct** le 2026-11-13 contre `https://api.neomundi.io` : REST PASS
(`complete`, couverture 1.0, 5 signaux `measured`, 0 avertissement) et SSE PASS
(7 événements sur 1,937 s, `done` présent, sha256 recalculé identique, 0
duplication).

### `token_count` et `latency_ms` peuvent-ils être omis ?

**Non.** Trois éléments concordants :

1. le contrat déployé **de la réponse** republie
   `token_count_source: "caller_declared"` comme **`const` d'un champ
   requis** — le serveur déclare lui-même qu'il ne compte pas, qu'il republie
   la déclaration de l'appelant ;
2. `RawMetrics.token_count` et `.latency_ms` sont déclarés `Field(..., ge=0)`,
   donc requis (`app/models/requests.py:36-45`) ;
3. l'appel réel du 2026-11-13 les a transmis tous les deux.

⚠ **NON ÉTABLI : la sonde live de la requête.** Une sonde non facturée était
prévue — un `POST /v1/govern` dont le `mode` est invalide, pour que la
validation pydantic rejette la requête **avant** `enforce_trial_quota` et que
le 422 nomme les champs manquants. Elle **n'a pas pu être exécutée** : l'accès
au magasin de clés de ce poste est refusé par la politique de l'environnement.
Les trois éléments ci-dessus sont donc des preuves de code et de contrat de
réponse, pas une mesure du validateur déployé. **Les deux champs restent
requis dans le SDK, et c'est la conduite prudente.**

### Écart relevé — corrigé en amont, verrouillé ici

La qualification du 2026-11-13 avait noté **quatre champs racine requis par le
contrat déployé et inconnus du SDK**, qui atterrissaient dans
`unknown_fields` : `contract_version`, `token_count_source`,
`token_count_scope`, `token_count_unit` (+ `stream_contract_metadata`,
nullable). 🟢 **Les PR #18 et #19 les ont déjà ajoutés à `GovernResult`** ;
cette branche n'y touche pas.

Ce qu'elle ajoute : les deux schémas **téléchargés depuis la production** sont
versionnés comme fixtures, leurs empreintes sont mesurées à chaque exécution,
et un test échoue si un champ que le contrat déployé déclare **requis**
redevient inconnu du SDK. `scripts/check_live_wire_schemas.py` établit la même
parité en ligne, mais sur commande explicite seulement ; ce contrôle-ci tourne
hors ligne, à chaque exécution de la suite.

⚠ **Observation de compatibilité, non corrigée.** Ces cinq champs ont été
insérés **avant** `raw`, `unknown_fields` et `parse_warnings`, qui passent de
l'index 28 à l'index 33. Une construction **positionnelle** de `GovernResult`
à 29 arguments ou plus lirait désormais un champ pour un autre, **sans
erreur**. Aucun code du SDK ne le construit autrement que par mots-clés, et le
déplacement est déjà fusionné : il est consigné par
`tests/test_contract_drift.py` plutôt que défait. La règle pour la suite :
**ajouter tout nouveau champ en fin de déclaration.**

Deux observations de contrat, non corrigées parce qu'elles appartiennent au
backend :

- `token_count_scope` vaut `caller_declared` sur REST — ce qui n'est pas un
  périmètre. Le contrat ne dit donc pas si le décompte couvre le prompt et la
  réponse ou la réponse seule ;
- sur SSE, `token_count_unit` peut valoir `chunks` : `total_tokens` compte
  alors des chunks. Les deux valeurs sont désormais exposées par
  `StreamResult`, pour qu'un consommateur ne compare pas des chunks à des
  tokens.

### Version de mesure

`verified_measurement_versions` vaut toujours `("3.3.0", "3.3.1")`, et
**`3.5.0` n'y a pas été ajoutée** alors que la production la sert. L'ajouter
pour faire taire l'avertissement déclarerait une compatibilité que personne n'a
vérifiée. L'avertissement est correct, et voulu.

---

## 3. VERIFY

### Existant — trois surfaces, trois objets

| Surface | Route / outil | Auth | Facturé | Ce qu'elle établit |
|---|---|---|---|---|
| Contrat RGC signé | `GET /v1/rgc/verify/{request_id}` | **aucune** | non | empreinte canonique recalculée + signature JWS Ed25519 |
| Certificat d'audit TIER_03 | `GET /v1/audit/verify/{audit_trail_id}` | **aucune** | non | l'empreinte imprimée sur le document correspond-elle à l'observation stockée |
| Archive Evidence | `neomundi-evidence verify` (PyPI `neomundi-evidence-verify` 0.1.0) | — | — | intégrité hors ligne de l'archive |

Les deux routes ont été **sondées en production le 2026-11-15** : elles rendent
le 404 documenté sur un identifiant inexistant, et `GET /v1/rgc/jwks` publie la
clé publique Ed25519 `neomundi-rgc-2026-01`.

🔴 **Deux pièges de lecture, tous les deux dans le code du backend :**

1. `GET /v1/audit/verify/{id}` **sans `?sha256=`** rend `valid: null` —
   « rien n'a été vérifié ». Aucune empreinte n'est conservée à l'émission :
   la seule chose comparable est celle imprimée sur le document du porteur.
2. un **404** de `GET /v1/rgc/verify/{id}` signifie « aucun contrat RGC émis
   pour cette observation », pas « signature invalide ». L'émission est un
   appel distinct, réservé au palier TIER_03.

### Manquant

- **Evidence n'a aucune API.** Le moteur est une collection de programmes en
  ligne de commande ; il n'est pas installable par `pip` et aucun service HTTP
  ne l'expose. La seule voie est le sous-processus.
- **Aucun lien attesté observation → archive Evidence.** Rien, dans la réponse
  de `/v1/govern`, ne nomme une archive Evidence, et rien, dans une archive,
  ne porte un `request_id` NeoMundi. 🔴 **Le lien demandé par l'issue #20
  §4 n'existe donc pas encore, et ce SDK ne le fabrique pas.** Ce que la
  branche livre à sa place : les deux vérifications d'émission réelles
  ci-dessus, et un adaptateur vers le vérificateur indépendant.
- **Le corpus de conformité n'est pas dans la roue PyPI** du vérificateur :
  `pip install` suffit pour vérifier ses propres archives, pas pour rejouer le
  corpus publié.

### Proposé, et implémenté

`src/neomundi/verification.py` :

- `client.verify(request_id)` → `ContractVerification`, `valid` **tri-état**
  (`True` / `False` / `None` = rien à vérifier) ;
- `client.verify_audit_certificate(id, sha256=...)` →
  `AuditCertificateVerification`, même règle tri-état, et le `null` du serveur
  n'est jamais replié ;
- `verify_evidence_archive(path)` → sous-processus vers `neomundi-evidence`,
  les cinq codes de sortie republiés sans traduction, `verification_performed`
  faux pour 3 et 4, `passed` à `None` pour le code 2 (vérification
  *incomplète*, pas échouée), et une exception — non un verdict — quand le
  programme est absent ;
- aucun secret transmis au sous-processus : toute variable dont le nom contient
  `KEY`, `TOKEN`, `SECRET`, `PASSWORD` ou `CREDENTIAL` est retirée de son
  environnement ;
- un test interdit à ce module d'importer `hashlib`, `zipfile`, `hmac`,
  `base64` ou `cryptography` : **il appelle, il ne recalcule pas.**

### Proposé et NON retenu

- **Réimplémenter le vérificateur Evidence dans le SDK.** Interdit par l'issue,
  et ce serait une seconde implémentation de l'intégrité.
- **Un `verify()` qui rendrait un booléen.** Replier `None` sur `False`
  effacerait la distinction entre « non vérifié » et « invalide », qui est
  l'objet même de l'étape.

---

## 4. INSTALL

🟢 **Déjà en ordre dans `main`, et cet audit l'a découvert en retard.** Le
chantier a d'abord été mené sur un `main` local périmé (`210eb29`), parce
qu'un `git fetch` avait expiré en silence. Les PR #17 à #19, fusionnées le
2026-11-14, portaient déjà :

- `name = "neomundi"` — le dépôt déclarait `neomundi-sdk`, un projet absent de
  PyPI, et ne pouvait donc pas reproduire son propre artefact publié. **Corrigé
  en amont** ;
- le retrait **délibéré** du classificateur `Private :: Do Not Upload`, la
  licence `Apache-2.0`, un flux `publish-pypi.yml` en `workflow_dispatch`
  verrouillé (branche, tag, phrase de confirmation, environnement, OIDC) et
  `tests/test_pypi_release_guard.py` qui éprouve ces verrous.

**Conséquence pour cette branche :** la version reste **`2.0.0`**. Le
garde-fou de publication épingle ce numéro et le tag `sdk-v2.0.0` ; le bouger
depuis une branche de fonctionnalité relâcherait un contrôle de publication
délibéré. **Choisir le numéro de la prochaine version est une décision de
publication**, à prendre avec le tag et le garde-fou — pas un effet de bord de
ce travail. La documentation dit donc l'écart au lieu de le chiffrer : la roue
publiée ne porte ni `trace()` ni `verify()`.

⚠ **Leçon de méthode :** un `git fetch` qui expire laisse un `main` local
silencieusement périmé. Ici, cela a coûté un travail en double sur
`models.py` et sur `pyproject.toml`, rattrapé par rebase. Le remède est connu
et documenté : brancher `gh` comme assistant d'identifiants avant de lire ou
d'écrire sur le distant.

---

## 5. RGPD — provenance, conservation, transmission

| Donnée | Transmise ? | Conservée ? | Source |
|---|---|---|---|
| `llm_prompt` | oui, traitée en mémoire | **jamais** — seule sa longueur | `governance.py:539-553` |
| `llm_response` | oui | **des extraits VERBATIM**, dans `quality.suspect_phrases`, quand le score de factualité dépasse son seuil | code déployé du détecteur |
| `rag_context`, `documents` | oui, au juge d'ancrage | **jamais** | `requests.py` |
| `metadata` | oui | **jamais** — la route ne le lit pas | §1 |
| Réponse de mesure complète | — | oui, `governance_logs.full_json` | `governance.py:564` |

- **Écrire « aucun contenu client n'est conservé » serait faux.** La
  formulation exacte : *le prompt n'est jamais conservé ; des extraits de la
  réponse le sont lorsque le score de factualité dépasse le seuil.*
- **Rétention :** aucune purge n'est en place côté plateforme ; les sauvegardes
  tournent sur 14 jours.
- **Transmission :** trois signaux sur cinq sont calculés sur des modèles
  hébergés sur la machine du service ; la factualité et l'instabilité
  sémantique appellent **un** sous-traitant. L'hébergement est en **Suisse**
  (décision d'adéquation, mais hors UE — le fait doit être énoncé).
- **Apport de cette branche :** `TraceRecord` ne porte aucun contenu, donc
  journaliser une trace ne peut pas faire fuir un prompt ; et le sous-processus
  de vérification ne reçoit aucune clé.

Le dossier de référence reste
[neomundi-io-data-protection](https://github.com/neomundi-io/neomundi-io-data-protection).

---

## 6. Ce que cette branche NE fait pas

- aucune modification du backend, aucune route ajoutée, aucun déploiement ;
- aucun appel facturé ni aucune mutation en production : les seules requêtes
  réelles émises par cet audit sont des **GET publics et non facturés**
  (`/v1/health`, `/v1/contracts/*`, `/v1/rgc/schema`, `/v1/rgc/jwks`, deux 404
  de vérification) ;
- aucune publication PyPI, aucune fusion automatique, aucun changement du
  flux de publication verrouillé ni de son garde-fou ;
- aucune signature existante modifiée : `govern()`, `stream()`,
  `GovernResult` et `StreamResult` restent compatibles. Les cinq nouveaux
  champs de `GovernResult` sont ajoutés **en fin de déclaration**.
