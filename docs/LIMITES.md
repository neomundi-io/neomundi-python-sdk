# Limites méthodologiques héritées du backend

**À lire avant de communiquer tout chiffre produit par ce SDK.**

Ce document ne décrit pas des limites du SDK. Il décrit ce que l'API
NeoMundi mesure réellement, au commit `68d6057`, version de mesure
`3.3.0`. Le SDK transporte fidèlement ces mesures ; il ne peut pas les
améliorer, et ne doit pas donner l'illusion qu'il le fait.

Source : audit de référence du 2026-10-17, documents 02 et 03, dont les
valeurs numériques ont été recalculées depuis les formules implémentées.

**Ces limites valent aussi sous `3.3.1`**, la version servie par la
production. Vérifié le 2026-10-22 : le calcul de mesure est inchangé
entre les deux commits — rien sous `app/models/`, rien dans la route
REST —, et une réponse réelle de production sous `3.3.1` les exhibe
encore, dont les deux homonymes `stability_score` d'échelles inverses et
le signe de `baseline.delta_E`. Les deux seules sections à lire avec
`3.3.1` à l'esprit sont le §9, sur la comparabilité, et ce qui touche au
chemin SSE, que `3.3.1` modifie et que ce SDK ne couvre pas.

---

## 1. Les scores n'utilisent pas toute l'échelle `[0, 1]`

C'est la limite la plus importante, parce qu'elle porte sur le chiffre
qu'un client, un chercheur ou un journaliste citera.

### Valeurs effectivement publiées

Calculées en reproduisant les formules du backend
(`score_engine.py`, `metrics/g_final.py`), pour une réponse de 500 tokens :

| Situation mesurée | `stability_score` | `g_final` |
|---|---|---|
réponse parfaite | 1,000 | 1,000 |
couverture partielle 2/3 | 0,834 | 0,933 |
hallucination notée **0,73** | 0,757 | **0,901** |
contenu **jugé dangereux** (modération) | 0,717 | **0,887** |
**hallucination maximale (1,0)** | **0,667** | **0,864** |
incohérence totale mesurée (0,0) | 0,500 | 0,600 |
dangereux **et** hallucination maximale | 0,383 | 0,751 |

> **Une réponse que le juge considère comme totalement fausse publie un
> `g_final` de 0,86.** Un lecteur non averti lit « 86 % ».

### Pourquoi

Deux causes arithmétiques.

**a) `G` plafonne à 0,60 par construction.**

```
G = 0.30·confidence + 0.30·coherence − 0.20·semantic_risk − 0.20·hallucination
G_MAX = 0.30 + 0.30 = 0.60        (seuls les termes ADDITIFS plafonnent G)
stability_score = G / G_MAX
```

Les deux termes additifs valent 0,30 chacun ; les deux soustractifs 0,20.
Une hallucination maximale ne peut retirer que 0,20 à un total de 0,60,
soit un tiers.

**b) Deux des quatre termes de `g_final` sont numériquement figés.**

```
g_final = 0.40·S + 0.25·P + 0.15·Q + 0.20·C
P = 1/Di    avec Di = (N + 3H)/N
Q = min(1, N/E)  avec E = N + 3H
```

Le terme de risque est **borné par 3**, quelle que soit la longueur de la
réponse. Donc `Di − 1 = 3H/N` tend vers 0, et `P` comme `Q` tendent vers 1.

Amplitude **totale** de `P` entre une hallucination nulle et maximale :

| `N` (tokens de réponse) | amplitude de `P` |
|---|---|
5 | 0,375 |
30 | 0,091 |
100 | **0,029** |
500 | **0,006** |
4 000 | 0,0007 |

Pour `N = 500`, `0.25·P + 0.15·Q ≈ 0.3988` **en toutes circonstances** :
**40 % du poids de `g_final` est une constante.** Le plancher structurel
de `g_final` est donc ≈ 0,40.

### Plages effectives à publier

| Indicateur | Intervalle déclaré | **Plage effective** (réponse > ~30 tokens) |
|---|---|---|
`quality.stability_score` | `[0, 1]` | **`[0.60 ; 1.00]`** |
`g_final` | `[0, 1]` | **`[0.40 ; 1.00]`** |

### Conséquence pratique

**Le verdict (`decision`) est plus informatif que le score.** Dans les
trois cas défavorables du tableau ci-dessus, le backend répond bien
`FLAG` — les seuils d'escalade fonctionnent. C'est le score qui ne porte
pas l'information.

```python
# À privilégier
if result.governance.decision == "FLAG":
    ...

# À manier avec prudence, et jamais sans contexte
if result.g_score is not None and result.g_score < 0.4:
    ...
```

---

## 2. Les quatre dimensions de l'ESI ne sont pas indépendantes

`g_final` est présenté comme une combinaison de quatre dimensions. En
substituant les formules :

```
P et Q sont la MÊME expression : N/(N+3H)
H alimente déjà S, via le terme d'hallucination de G
C est coherence_score, qui alimente déjà S, via le terme de cohérence de G
```

En développant, pour une réponse de longueur réaliste :

```
g_final ≈ 0.20·confidence + 0.40·coherence − 0.133·risk − 0.133·hallucination + 0.3988
```

Lecture : **la cohérence pèse trois fois plus que l'hallucination** dans
`g_final` (0,40 contre 0,133), et la seule complétude instrumentale
(`confidence`) pèse autant que l'hallucination et le risque réunis.

**À ne pas affirmer** : « l'ESI combine quatre dimensions indépendantes ».
**À dire** : « quatre termes, dont deux dérivés du score factuel et un
déjà présent dans le premier ».

---

## 3. Le juge de factualité n'est pas déterministe

`temperature = 0.1` (et non 0) dans l'appel au juge. **Deux appels
identiques peuvent produire deux notes différentes.**

**Cet écart n'a jamais été mesuré.** Tant qu'il ne l'est pas, aucune
différence entre deux observations n'est interprétable — ni pour un
pilote, ni en interne, ni dans une publication.

C'est le préalable absolu à toute affirmation de répétabilité, et le
travail le moins coûteux à faire : 30 appels sur une entrée fixe.

### Ce que le juge est, et n'est pas

| | |
|---|---|
**est** | un modèle de langage qui note un texte, sous un prompt dont l'empreinte est publiée |
**n'est pas** | une vérification factuelle. Aucune source externe, aucune base de connaissances, aucune recherche. |

Un `factual_hallucination_score` de `0.0` signifie **« le juge n'a rien
trouvé »**, jamais « il n'y a pas d'hallucination ».

---

## 4. Le risque sémantique est binaire

`semantic_risk` ne prend que **deux valeurs** : `0.0` (verdict `safe`) ou
`0.85` (verdict `unsafe`, constante littérale du backend).

- ce n'est **pas** un score graduel, malgré son type flottant ;
- `0.85` est arbitraire et non documenté comme calibré ;
- `category_scores` affecte la même constante à chaque catégorie
  détectée : **ce ne sont pas des probabilités** ;
- le classifieur est le plus petit de sa famille (1 milliard de
  paramètres), et ses taux d'erreur sur le trafic NeoMundi sont inconnus ;
- **seule la réponse est modérée, pas le prompt** : un prompt dangereux
  avec une réponse anodine est classé `safe`.

---

## 5. La cohérence dépend entièrement du modèle d'embedding

`coherence_score` est une similarité cosinus prompt↔réponse.

- **aucune valeur de référence absolue** : 0,45 peut être excellent pour
  une question ouverte et médiocre pour une reformulation ;
- le seuil d'incohérence (0,30) n'est adossé à aucune calibration
  versionnée ;
- **changer le modèle d'embedding change toutes les valeurs**, sans que
  `measurement_version` ne bouge (voir §8) ;
- une hallucination parfaitement sur-sujet obtient une cohérence élevée ;
- une valeur de `1.0` peut signifier **« contrôle jamais lancé »** et non
  « parfaitement cohérent » — voir §7.

---

## 6. `confidence` n'est pas une confiance statistique

```
confidence = checks_succeeded / checks_attempted      (dénominateur ≤ 3)
```

Valeurs possibles : **`0`, `1/3`, `1/2`, `2/3`, `1`**. Rien d'autre.

Ce n'est ni un intervalle, ni une probabilité, ni une mesure de la
qualité des mesures réussies. C'est un **taux de complétude
instrumentale**.

Deux propriétés à son crédit : elle est **re-dérivable** par le
consommateur, et son origine est toujours déclarée.

```python
m = result.measurement
assert round(m.checks_succeeded / m.checks_attempted, 6) == m.coverage
m.confidence_basis   # 'measurement_coverage' | 'no_server_check'
```

**Piège** : `coverage` vaut `1.0` quand **rien** n'a été tenté. À lire
**toujours** avec `status` :

```python
if result.measurement.status == "not_attempted":
    # coverage = 1.0 ne signifie PAS « tout a été mesuré »
    ...
```

---

## 7. Un contrôle jamais lancé crédite `G` sans le dire

Asymétrie déclarée dans le backend, non fermée.

| Signal non lancé | Valeur par défaut dans `G` | Effet |
|---|---|---|
`semantic_risk` | `0.0` — terme soustractif | neutre |
`hallucination_score` | `0.0` — terme soustractif | neutre |
**`coherence_score`** | **`1.0`** — terme **additif** | **crédite `G` de 0,30 et `g_final` de 0,20** |

Et cette valeur de convention est **publiée comme une valeur** :
`quality.coherence_score` vaut `1.0`, et ce signal **n'apparaît ni dans
`measured_signals` ni dans `unmeasured_signals`**.

**Atteignable par configuration** : un client qui désactive le contrôle de
cohérence pour réduire sa facture obtient un `stability_score` et un
`g_final` **systématiquement plus hauts**. Les scores des deux comptes ne
sont pas comparables, et aucun champ de la réponse ne le signale.

Le SDK rend ce cas détectable sans le trancher :

```python
state = result.measurement_state("coherence_score")
if state is MeasurementState.NOT_ATTEMPTED_OR_GATED:
    # Soit jamais lancé (et quality.coherence_score peut valoir 1.0 par
    # convention), soit masqué par le palier (et il vaut null).
    # Le serveur ne distingue pas les deux sur le fil.
    result.measurement.status          # indice : 'not_attempted' ?
    result.measurement.checks_attempted
```

---

## 8. La version de mesure ne couvre pas l'identité des instruments

`measurement_version` est **le seul numéro qui ait un sens scientifique**,
et le backend le protège par une batterie de tests comportementaux.

**Mais ce garde-fou protège les formules, pas les instruments.**

| Changement | Les valeurs changent ? | `measurement_version` bouge ? |
|---|---|---|
poids de `G`, coefficients β, seuils | oui | **oui — gardé** |
formules de `Di`, `E`, `P`, `Q` | oui | **oui — gardé** |
**modèle du juge de factualité** | **oui, massivement** | **non** |
**modèle d'embedding** | **oui, toutes les cohérences** | **non** |
**modèle de modération** | **oui** | **non** |
**texte du prompt système du juge** | **oui** | **non** |

Une série de 30 jours peut donc traverser un changement de modèle
d'évaluateur sans qu'aucun champ ne change de version.

### Comment s'en protéger avec ce SDK

Le backend publie déjà, par observation, les empreintes nécessaires :

```python
ev = result.evaluator_of("factual_hallucination_score")
ev["model_used"]              # le modèle qui a RÉPONDU
ev["model_configured"]        # le modèle VISÉ par l'appel
ev["prompt_template_hash"]    # empreinte du prompt de jugement
ev["inference_config_hash"]   # empreinte des réglages d'inférence
ev["config_fingerprint"]      # une valeur pour toute la configuration
ev["served_by"]               # 'primary' | 'fallback'
```

**Relever `config_fingerprint` au début d'une série et vérifier qu'il ne
bouge pas** est la seule garantie disponible aujourd'hui que les
observations ont été produites sous la même configuration.

---

## 9. Conditions de comparabilité entre deux résultats

Deux observations ne sont comparables que si **toutes** ces conditions
sont réunies :

| Condition | Comment la vérifier |
|---|---|
même `measurement_version` | `result.audit.measurement_version` |
même couverture de mesure | `result.measurement.coverage` et `.status` |
mêmes modèles d'évaluateur | `result.evaluator_of(signal)["config_fingerprint"]` |
mêmes poids β | `result.esi.betas` |
même route | ce SDK n'expose que `POST /v1/govern` — déjà garanti |
mêmes contrôles actifs | `result.measurement.checks_attempted` |

Énoncé du backend lui-même, à reprendre tel quel :

> Les résultats sous 3.2.0 et 3.3.0 ne sont **pas** comparables pour une
> même entrée dès que (a) l'observation vient du chemin SSE, (b) un signal
> requis n'a pas été mesuré, ou (c) le client est en TRIAL ou TIER_01.
> Partout ailleurs ils sont identiques. **Toute étude longitudinale doit se
> tenir entièrement d'un seul côté de la frontière.**

Et pour `3.3.0` face à `3.3.1` — la version que sert la production — le
backend est plus étroit, également à reprendre tel quel :

> Sous 3.3.0 et 3.3.1 les résultats diffèrent pour une même entrée
> **uniquement** sur une observation en flux qui (a) était laissée à
> `ALLOW` par les signaux mesurés et (b) produisait un profil `DROP` ou
> `OSCILLATING` à partir de points non mesurés. Partout ailleurs — **tout
> le chemin REST**, chaque agrégat, chaque état de couverture, chaque
> champ filtré par palier — les deux sont identiques.

**Ce qu'il faut en faire, et ce qu'il ne faut pas en faire.** C'est
l'énoncé du backend sur sa propre formule, et il est corroboré par la
comparaison des sources entre les deux commits : rien sous `app/models/`,
rien dans la route REST. Ce n'est pas pour autant une autorisation de
mêler deux séries. La pratique prudente ne coûte rien : consigner
`result.audit.measurement_version` avec chaque observation, et tenir une
série d'un seul côté. Une mesure dont la version n'a pas été consignée ne
se rattrape pas après coup.

**Le SDK ne vérifie pas ces conditions à votre place** : décider qu'une
série est valide est une décision méthodologique, pas une opération de
transport.

---

## 10. Champs dont la sémantique est ambiguë

Exposés tels quels, sous leur chemin complet, avec l'ambiguïté déclarée.

### `stability_score` — deux champs, échelles **inversées**

```python
result.quality.stability_score   # G / 0.60       -> 1 = stable
result.metrics.stability_score   # 1 − G / 0.60   -> 0 = stable
```

Même nom, même réponse JSON, sens opposés. Pour une réponse parfaite :
`1.0` et `0.0`.

Le SDK **n'expose aucun raccourci** `result.stability_score` : choisir un
des deux sens serait trancher une ambiguïté du contrat.

### `delta_E` — le signe documenté est l'inverse du signe calculé

| | |
|---|---|
description du champ côté serveur | `observed_energy - reference_energy` |
implémentation | `reference − observed` |

**Divergence découverte pendant le développement de ce SDK, signalée,
non tranchée.** Le SDK expose la valeur brute et ne recalcule rien. **Ne
déduire aucun signe de ce champ** avant arbitrage.

### Les deux `Q`

| Champ | Formule | Portée |
|---|---|---|
`esi.q_value` | `min(1, N/E)` | par requête |
`baseline.esi_q` | variabilité en fenêtre glissante de l'énergie observée | **en mémoire par processus serveur**, perdue au redémarrage, incohérente entre plusieurs processus |

### Les deux « densités »

| Champ | Mesure | Entre dans `g_final` ? |
|---|---|---|
`quality.information_density` | densité réelle du texte (répétitions, compression, remplissage) | **NON** |
`density.informational_density` | `(N + 3H)/N` | **OUI** (terme `P`) |

Le champ qui mesure réellement une densité d'information **n'entre dans
aucun agrégat**.

### `delta_g` — ne mesure pas une dérive

C'est l'écart de `G` avec la **requête précédente du même compte**,
quelle que soit la question posée, dans une fenêtre d'une heure.

Trois réserves :

1. un compte qui alterne entre deux cas d'usage produit un `delta_g`
   oscillant qui ne décrit **aucune** dérive ;
2. le champ peut porter un **nombre** alors que `g_score` vaut `None` ;
3. quand l'agrégat est retenu, le serveur **mémorise `0.0`** comme
   référence : le `delta_g` de l'appel suivant en est faussé d'environ
   +0,5.

```python
if result.g_score is None and result.delta_g is not None:
    # Incohérence connue : un delta dérivé d'un agrégat non publiable.
    pass
```

### `trajectory_points` et `provider` — toujours `None` en REST

`None` signifie ici **« sans objet sur cette route »**, et non « zéro ».

### Les compteurs qui disent « tokens »

Sur le chemin SSE (hors périmètre de ce SDK), `tokens_so_far`,
`token_position` et `tokens_checked` comptent des **fragments de flux**,
pas des tokens. Le backend le déclare dans `counter_units`. Mentionné ici
pour le futur client SSE.

### `prompt_length` et `response_length` — en caractères

Documentés en **caractères**. La route lit `prompt_length` comme
`tokens_in` pour calculer `volumetric_density`, qui est donc un ratio
**tokens / caractères** — ce que le champ `volumetric_density_basis`
déclare.

---

## 11. `suspect_phrases` peut contenir des extraits que personne n'a désignés

Quand le juge note une fausseté supérieure à 0,3 **sans** renvoyer
d'extrait, le serveur publie **les trois premières phrases de la
réponse** avec `category: "factual_error"`, une sévérité, et une
explication générique.

**Aucun évaluateur n'a désigné ces phrases** : leur position dans le texte
est leur seule qualification.

Le SDK transporte ces extraits tels quels. **Il ne peut pas distinguer un
extrait désigné par le juge d'un extrait auto-extrait** : le serveur ne le
signale pas sur le fil.

À ne pas présenter comme « les passages que le juge a identifiés ».

---

## 12. Ce que NeoMundi ne démontre pas

| Affirmation interdite | Pourquoi |
|---|---|
« score élevé ⇒ réponse vraie » | aucun signal ne consulte de source de vérité |
« score bas ⇒ réponse fausse » | `G` chute aussi quand un instrument tombe, ou quand la couverture est partielle |
« `semantic_risk = 0.0` ⇒ contenu sûr » | verdict binaire d'un classifieur de 1 Md de paramètres, sur la réponse seule |
« `factual = 0.0` ⇒ pas d'hallucination » | le juge n'a rien trouvé ; il n'a pas cherché dans une base de faits |
« `coherence = 1.0` ⇒ réponse pertinente » | peut signifier « contrôle jamais lancé » |
« `delta_g` mesure une dérive » | voir §10 |
« `g_final = 0.86` ⇒ très bonne réponse » | une hallucination maximale publie 0,864 |
« les scores sont comparables entre deux clients » | poids β et contrôles actifs sont personnalisables par compte |
« une observation établit une récurrence ou une dérive » | **interdit par le contrat RGC du backend lui-même**, qui versionne un contre-exemple |
« NeoMundi a une capacité prédictive » | rien dans le code ne modélise un futur |

### Ce que `FLAG` signifie, et ne signifie pas

`FLAG` est **consultatif**. NeoMundi n'autorise, ne refuse, ne suspend et
ne modifie **aucune** exécution.

Et un `FLAG` **ne porte pas toujours sur le contenu** :

```python
if result.governance.decision_basis == "incomplete_measurement":
    # Ce FLAG dit « la mesure ne s'est pas terminée ».
    # Il ne dit RIEN de la qualité de la réponse.
    pass
```

---

## 13. Ce que les tests de ce SDK ne prouvent pas

Les 206 tests passent sur **transport simulé**, avec des fixtures
**construites depuis la lecture du code** du backend — non capturées
depuis un serveur en fonctionnement.

**Conséquence** : un écart entre ce que `responses.py` déclare et ce que
le serveur déployé émet réellement resterait invisible.

Lever cette limite demande de capturer des charges réelles depuis une
instance de test, et de rejouer la suite contre elles. C'est la première
action recommandée avant tout pilote.
