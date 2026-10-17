# Mention de licence

**Statut : non arbitré.**

Ce paquet n'embarque aucun fichier `LICENSE` parce que le choix de
licence est une décision produit qui n'a pas été prise. Ce document
existe pour que l'absence soit explicite plutôt que subie.

## État actuel

- Code propriétaire NeoMundi, usage interne et pilotes sous accord.
- `Private :: Do Not Upload` est déclaré dans les classificateurs de
  `pyproject.toml` : une publication accidentelle sur PyPI est refusée
  par l'index tant que ce classificateur est présent.
- **Aucune publication n'a été effectuée.**

## À arbitrer avant toute publication publique

| Question | Pourquoi elle bloque |
|---|---|
Licence du SDK (propriétaire ? Apache-2.0 ? MIT ?) | un paquet sans licence n'est légalement pas réutilisable, même publié |
Compatibilité avec la dépendance `httpx` | httpx est sous BSD-3-Clause — compatible avec tous les choix ci-dessus, aucun blocage attendu |
Retrait du classificateur `Private :: Do Not Upload` | il doit être retiré **consciemment**, au moment de la décision de publier |

## Dépendance de production

| Paquet | Licence | Rôle |
|---|---|---|
`httpx` | BSD-3-Clause | transport HTTP |

Aucune autre dépendance de production. `pytest` (MIT) n'est utilisé qu'en
développement.
