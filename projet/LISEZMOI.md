# Pokécollection

Un tableau de bord local pour explorer une collection Pokémon de démonstration, sans compte.

## Démarrage

Depuis la racine `nyc-eats`, avec Docker Desktop démarré :

```powershell
docker compose -f docker-compose.yml -f docker-compose.pokemon.yml --profile tous up -d --build
```

La première préparation nécessite Internet (TCGdex, images, modèle). Dans un autre terminal :

```powershell
docker exec python python /projet/importer.py
```

Ouvrir **http://localhost:8501**. API : **http://localhost:8000/docs**.

L’API et Streamlit sont lancés automatiquement par `lancer.py`. Le complément Compose remplace le processus Jupyter par ces deux services. Les bases et fichiers des anciens TP restent séparés : les données Pokémon utilisent la base MongoDB `pokemon`, la table PostgreSQL `pokemon_semantique` et le préfixe Redis `pokemon:`.

Journaux :

```powershell
docker compose -f docker-compose.yml -f docker-compose.pokemon.yml logs -f python
```

Arrêter sans perdre les données :

```powershell
docker compose -f docker-compose.yml -f docker-compose.pokemon.yml --profile tous stop
```

## Import et fonctionnement hors ligne

L’import par défaut télécharge la liste française et les extensions, puis les fiches détaillées des extensions **Set de Base (`base1`), Jungle (`base2`) et Fossile (`base3`)** : au plus 240 fiches. La collection comprend uniquement des cartes de catégorie Pokémon, avec 360 exemplaires simulés. Les prix sont générés avec une graine fixe de 42 ; il ne s’agit pas de prix de marché.

Les fichiers bruts, les images, le modèle et le bilan sont conservés dans `travail/pokemon/`, monté dans le conteneur. Les fiches et images sont mises en cache ; une relance reprend les téléchargements manquants. Les illustrations absentes de la source ont un emplacement explicite dans l’interface.

Reconstituer les bases depuis le cache, sans accès Internet :

```powershell
docker exec python python /projet/importer.py --hors-ligne
```

Autre sélection (à préparer avant la démonstration) :

```powershell
docker exec python python /projet/importer.py --extensions base1,base2,base3 --limite 240 --exemplaires 360
```

Importer toutes les fiches françaises est possible avec `--toutes` ; cela implique des dizaines de milliers de requêtes, d’images et de vectorisations. La petite sélection suffit à la démo. `--sans-vecteurs` prépare seulement MongoDB et les images.

Une relance remplace la sélection et la collection de démonstration de cette application. Effectuer l’import hors démonstration : il n’existe pas de transaction distribuée entre MongoDB et PostgreSQL. Si la préparation des fiches échoue, les bases ne sont pas modifiées ; si la vectorisation échoue après MongoDB, relancer pour reconstruire l’index. Le cache est un instantané, pas une actualisation automatique du catalogue.

Les volumes réellement téléchargés sont écrits dans `travail/pokemon/bilan_import.json`. Aucun appel à TCGdex ou Hugging Face n’est effectué par l’application pendant son utilisation ; les liens documentaires restent facultatifs.

## Fichiers et responsabilités

| Fichier | Rôle |
|---|---|
| `pokemon/dao.py` — `CollectionDAO` | Mario : filtres, fiches et agrégations MongoDB |
| `pokemon/dao.py` — `RechercheDAO` | Swann : index dérivé PostgreSQL/pgvector |
| `pokemon/dao.py` — `HistoriqueDAO` | Dorian : historique temporaire Redis |
| `pokemon/textes.py` | Normalisation des fiches et préparation des textes |
| `pokemon/embeddings.py` | Modèle multilingue local, commun aux cartes et aux recherches |
| `importer.py` | Téléchargement, génération des exemplaires, import et vectorisation |
| `api.py` | FastAPI, validation et dégradation des services facultatifs |
| `tableau_de_bord.py` | Interface Streamlit, accès exclusivement HTTP à l’API |
| `tests/test_pokemon.py` | Tests métier et intégration sur la collection importée |

## Parcours de démonstration

1. Ouvrir la collection ; montrer les trois indicateurs calculés par MongoDB.
2. Filtrer par nom, extension, type ou rareté et ouvrir une fiche illustrée.
3. Montrer les exemplaires : état, variante, date et prix d’achat simulé.
4. Dans « Recherche par sens », saisir « un Pokémon qui provoque des incendies » : Dracaufeu figure parmi les résultats.
5. Montrer les cinq cartes et leurs distances cosinus (plus faible = texte plus proche ; ce n’est pas un score de confiance).
6. Consulter plusieurs cartes puis ouvrir « Dernières consultations ».
7. Montrer les statistiques par extension et par rareté, doublons inclus.

Chaque session Streamlit reçoit un UUID anonyme. Un nouveau chargement du navigateur peut créer une nouvelle session ; aucun historique durable ni compte n’est créé. Seuls les clics d’ouverture créent une consultation, pas les rechargements internes de Streamlit. La liste conserve les doublons et expire après 30 minutes sans nouvelle consultation ; une lecture de la liste ne prolonge pas le délai.

## Recherche sémantique

Les textes réunissent le nom, les types, la description et les noms/effets des attaques et capacités. Une carte sans description ni effet utile reste au catalogue mais n’est pas indexée.

Modèle : `Xenova/multilingual-e5-small`, 384 dimensions, inférence CPU ONNX quantifiée. La révision téléchargée est enregistrée dans le manifeste et dans chaque ligne PostgreSQL. Les textes longs sont découpés pour ne pas ignorer les derniers effets. Les cartes et les requêtes utilisent les mêmes poids et la même normalisation, avec les préfixes E5 attendus : passage: pour les cartes et query: pour les recherches.

Les formules introductives génériques (« un Pokémon qui », « mes cartes ») sont retirées de la requête pour centrer l’embedding sur le besoin. Le texte descriptif n’est pas remplacé par des mots-clés prédéfinis.

La requête SQL limite d’abord les références aux cartes effectivement possédées dans MongoDB, puis trie par distance cosinus et conserve cinq résultats. Une recherche exacte suffit pour cette petite sélection ; un index HNSW n’est pas requis. Les filtres classiques sont indépendants de la recherche par sens.

## Disponibilité et CAP

MongoDB est la référence durable, en replica set ; les écritures utilisent `w: majority` avec un délai maximal de cinq secondes pour obtenir l’accusé de réception. Sans majorité, les écritures ne sont pas confirmées. Un délai dépassé n’implique pas nécessairement que l’écriture n’a pas été appliquée : les identifiants déterministes permettent de relancer l’import.

PostgreSQL contient un index reconstruit lors de l’import. Son arrêt rend uniquement la recherche par sens indisponible. Redis conserve un historique non durable du point de vue métier : une panne retire cette fonction mais laisse fonctionner la collection et les fiches. On ne qualifie donc pas toute l’architecture d’AP du seul fait de ce mode dégradé.

Redis utilise une transaction `LPUSH`, `LTRIM 0 9`, `EXPIRE 1800`. Les prix sont stockés et additionnés en centimes entiers pour éviter les imprécisions monétaires.

## Validation

Après l’import :

```powershell
docker exec -e PYTHONPATH=/projet -e POKEMON_INTEGRATION=1 python python -m unittest discover -s /projet/tests -v
```

Ces tests vérifient les statistiques, les filtres, la pagination, les textes sans contenu utile, l’isolation des sessions, les doublons, la taille et l’expiration Redis, la dégradation en cas de panne Redis et la recherche sémantique limitée à la collection. Les historiques de test utilisent des UUID distincts et sont supprimés.

## Sources et présentation

- Données et illustrations : TCGdex, https://tcgdex.dev/fr/ ; API française https://api.tcgdex.net/v2/fr/cards.
- Modèle : https://huggingface.co/Xenova/multilingual-e5-small (MIT).
- Modèle d’origine et conventions d’encodage : https://huggingface.co/intfloat/multilingual-e5-small.
- Cartes Pokémon : illustrations et marques de leurs ayants droit ; ce projet est une démonstration pédagogique non officielle.
- Mentionner l’aide de l’IA à l’implémentation sur une diapositive, conformément au livret. Chaque membre doit pouvoir expliquer ses DAO et la circulation des données.
