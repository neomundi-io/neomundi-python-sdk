# Vérification de livraison — SDK 2.0.0

Date : 26 octobre 2026. Exécution locale sur Windows, Python **3.12.10**,
HTTPX **0.28.1**. Aucun appel NeoMundi hébergé ou fournisseur LLM.

| Contrôle exécuté | Résultat |
|---|---|
| `python -m pytest -o addopts='' -q` | **282 réussis, 12 ignorés** |
| Captures historiques optionnelles | 12 ignorés car les captures non versionnées sont absentes |
| Parseur et transport SSE | 54 nouveaux cas, plus l'exemple SSE exécuté dans les tests |
| Exemple `04_streaming_sse.py` | Exécuté sur transport simulé, intégrité vraie et mesure incomplète conservée |
| Ruff E/F/I/B sur les nouveaux fichiers, hors E501 | Conforme |
| Compilation des sources/tests/exemples | Conforme |
| Analyse grammaticale des sources en mode Python 3.9 | Conforme ; ne remplace pas une exécution sous Python 3.9 |
| `python -m build --no-isolation` | Wheel et archive source 2.0.0 construits |
| Import du wheel depuis un dossier distinct | Conforme ; version, exports, py.typed et scénario SSE vérifiés |
| Contenu de l'archive source | Exemples et fixtures de tests inclus ; captures privées non versionnées exclues |
| `git diff --check` | Conforme |

Les tests REST existants sont conservés. Les nouveaux tests vérifient
notamment une livraison du premier événement avant lecture de la fin du
flux : un tampon fixe HTTPX ne doit pas transformer le streaming en lot.

Le linter complet du dépôt conserve les avertissements historiques de
modernisation de types ; sa CI reste non bloquante comme avant. Les
nouveaux fichiers ont été contrôlés séparément sur les erreurs, imports
et règles de robustesse.

## Validation GitHub exécutée

Le [run CI 40285081931](https://github.com/neomundi-io/neomundi-python-sdk/actions/runs/40285081931)
valide les sept contrôles sur le commit `85eef9959c2ee77b1a8b28facfbeb4501fee68a1` :
tests et exemples sous Python **3.9, 3.11, 3.12 et 3.13**, construction et
installation isolée du wheel, syntaxe et contrôle des secrets.

Le premier run échouait avant les tests Python 3.9 : setup-python ne
fournit pas cette version sur Ubuntu 26.04. Ce cas utilise désormais
Ubuntu 22.04 ; les trois autres versions conservent ubuntu-latest.

Les comparaisons avec la production sont celles des anciennes preuves
REST documentées, pas des acquisitions réalisées pour V2. SSE a été
vérifié contre le contrat source local et des flux synthétiques ; une
validation réelle contrôlée reste distincte.
