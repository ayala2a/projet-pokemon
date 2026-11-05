# Pokécollection

Un catalogue Pokémon local et une collection persistante à constituer, sans compte.

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

L’import par défaut télécharge la liste française, les métadonnées des extensions/blocs, puis les fiches détaillées des extensions **Set de Base (`base1`), Jungle (`base2`) et Fossile (`base3`)** : au plus 240 fiches. Le catalogue affiché comprend uniquement les cartes de catégorie Pokémon. Le nombre de cartes, les blocs et les extensions réellement disponibles sont indiqués dans l’interface.

Sur une nouvelle installation, la collection commence vide. Dans « Catalogue », cocher les cartes et cliquer sur « Ajouter à ma collection » : un exemplaire est créé par carte, sans formulaire obligatoire. Répéter l’ajout pour posséder plusieurs exemplaires. Ouvrir une fiche pour retirer un exemplaire ou renseigner, facultativement, son état, sa variante et son prix d’achat. Un prix absent n’est pas considéré comme un achat à zéro euro ; les statistiques distinguent le total des achats et le nombre de prix renseignés.

La collection est commune à cette installation et persistante dans MongoDB ; elle ne dépend pas de la session Redis. Les exemplaires ajoutés sont conservés avec leurs informations. L’import n’insère, ne modifie et ne supprime aucun exemplaire. L’ancienne option de génération simulée a été retirée ; il n’existe aucun remplissage ni nettoyage automatique de la collection.

Les fichiers bruts, les images, le modèle et le bilan sont conservés dans `travail/pokemon/`, monté dans le conteneur. Les fiches et images sont mises en cache ; une relance reprend les téléchargements manquants. Les illustrations absentes de la source ont un emplacement explicite dans l’interface.

Reconstituer les bases depuis le cache, sans accès Internet :

```powershell
docker exec python python /projet/importer.py --hors-ligne
```

Autre sélection (à préparer avant la démonstration) :

```powershell
docker exec python python /projet/importer.py --extensions base1,base2,base3 --limite 240
# Import configurable par bloc ; 0 signifie sans limite
docker exec python python /projet/importer.py --blocs base --limite 0
# Enrichissement retenu, en conservant le catalogue existant
docker exec python python /projet/importer.py --blocs base,ex,dp,pl,hgss --limite 0
```

Importer toutes les fiches françaises est possible avec `--toutes` ; cela implique des dizaines de milliers de requêtes, d’images et de vectorisations. La petite sélection suffit à la démo. `--sans-vecteurs` prépare seulement MongoDB et les images.

Les imports sont cumulatifs. Une relance met à jour les fiches sélectionnées sans supprimer les autres fiches ni les exemplaires. L’index PostgreSQL est enrichi de la même manière ; un vecteur devenu inexploitable est retiré uniquement pour la référence réimportée. Effectuer l’import hors démonstration : il n’existe pas de transaction distribuée entre MongoDB et PostgreSQL. Si la préparation des fiches échoue, les bases ne sont pas modifiées ; si la vectorisation échoue après MongoDB, relancer pour compléter l’index. Le cache est un instantané, pas une actualisation automatique du catalogue.

Les volumes réellement téléchargés sont écrits dans `travail/pokemon/bilan_import.json`. Aucun appel à TCGdex ou Hugging Face n’est effectué par l’application pendant son utilisation ; les liens documentaires restent facultatifs.

Le bilan distingue le lot importé du catalogue cumulé : cartes Pokémon par bloc et extension, illustrations manquantes (références incluses), textes exploitables et cartes dont le vecteur est réellement à jour. Les filtres et le détail du périmètre sont lus dans MongoDB, sans appel externe. Les totaux annoncés par TCGdex incluent aussi les cartes Dresseur/Énergie et peuvent différer du nombre de fiches françaises effectivement disponibles.

## Fichiers et responsabilités

| Fichier | Rôle |
|---|---|
| `pokemon/dao.py` — `CatalogueDAO` | Mario : catalogue paginé, filtres par bloc/extension et périmètre importé |
| `pokemon/dao.py` — `CollectionDAO` | Mario : filtres, fiches et agrégations MongoDB |
| `pokemon/dao.py` — `RechercheDAO` | Swann : index dérivé PostgreSQL/pgvector |
| `pokemon/dao.py` — `HistoriqueDAO` | Dorian : historique temporaire Redis |
| `pokemon/textes.py` | Normalisation des fiches et préparation des textes |
| `pokemon/embeddings.py` | Modèle multilingue local, commun aux cartes et aux recherches |
| `importer.py` | Téléchargement, import cumulatif du catalogue et vectorisation ; aucun remplissage de la collection |
| `api.py` | FastAPI, validation et dégradation des services facultatifs |
| `tableau_de_bord.py` | Interface Streamlit, accès exclusivement HTTP à l’API |
| `tests/test_pokemon.py` | Tests métier et intégration sur la collection importée |

## Parcours de démonstration

1. Ouvrir le catalogue et montrer le périmètre local disponible.
2. Filtrer par bloc ou extension, puis sélectionner plusieurs cartes.
3. Cliquer sur « Ajouter à ma collection », sans saisir d’informations complémentaires.
4. Ouvrir « Ma collection » ; montrer les quantités et les statistiques MongoDB. Ouvrir une fiche pour retirer un exemplaire.
5. Dans « Recherche par sens », saisir « un Pokémon qui provoque des incendies ». Seules les cartes possédées participent ; Dracaufeu doit avoir été ajouté pour pouvoir apparaître.
6. Montrer jusqu’à cinq cartes pertinentes et leurs distances cosinus (plus faible = texte plus proche ; ce n’est pas un score de confiance), puis une recherche sans résultat.
7. Consulter plusieurs cartes puis ouvrir « Dernières consultations » pour montrer l’historique Redis.

Chaque session Streamlit reçoit un UUID anonyme. Un nouveau chargement du navigateur peut créer une nouvelle session ; aucun historique durable ni compte n’est créé. Seuls les clics d’ouverture créent une consultation, pas les rechargements internes de Streamlit. La liste conserve les doublons et expire après 30 minutes sans nouvelle consultation ; une lecture de la liste ne prolonge pas le délai.

## Recherche sémantique

Les textes réunissent le nom, les types, la description et les noms/effets des attaques et capacités. Ils sont aussi préparés en passages distincts (identité, description, chaque effet) dans `pokemon_passages`, afin qu’un effet court ne soit pas noyé dans la fiche entière. La requête retient le passage le plus proche par carte et l’interface affiche cet extrait. Une carte sans description ni effet utile reste au catalogue mais n’est pas indexée.

Modèle : `Xenova/multilingual-e5-small`, 384 dimensions, inférence CPU ONNX quantifiée. La révision téléchargée est enregistrée dans le manifeste et dans chaque ligne PostgreSQL. Les textes longs sont découpés pour ne pas ignorer les derniers effets. Les cartes et les requêtes utilisent les mêmes poids et la même normalisation, avec les préfixes E5 attendus : passage: pour les cartes et query: pour les recherches.

Les formules introductives génériques (« un Pokémon qui », « mes cartes ») sont retirées de la requête pour centrer l’embedding sur le besoin. Le texte descriptif n’est pas remplacé par des mots-clés prédéfinis.

Tous les textes exploitables des cartes Pokémon importées sont vectorisés, même si ces cartes ne sont pas encore possédées. Aucun calcul d’embedding ni tâche en arrière-plan n’est exécuté à l’ajout : seul MongoDB reçoit un exemplaire. La requête SQL limite d’abord les références aux cartes effectivement possédées dans MongoDB, choisit le meilleur passage par carte, applique le seuil calibré puis trie et conserve au plus cinq cartes. Elle ne complète jamais avec des distances supérieures au seuil. Une recherche exacte suffit pour cette petite sélection ; un index HNSW n’est pas requis. Les filtres classiques sont indépendants de la recherche par sens. Voir [la calibration et ses limites](../docs/RECHERCHE.md).

L’import compare le texte normalisé et l’identifiant exact du modèle à ceux de PostgreSQL. Les vecteurs déjà à jour ne sont ni recalculés ni réécrits ; les autres sont enregistrés par lots de vingt. Relancer la même commande réutilise donc aussi les lots déjà enregistrés. Une carte sans description ni effet utile reste accessible dans le catalogue mais ne participe pas à la recherche.

Les passages sont également préparés pendant l’import, par lots sauvegardés de trente cartes, et réutilisés si leur texte et le modèle sont inchangés. Pour migrer un index existant sans réimporter le catalogue : `docker exec python python /projet/indexer_passages.py`. Aucun calcul n’est lancé à l’ajout d’un exemplaire.

## Illustrations de secours

Les scans français sont prioritaires. Si TCGdex n’en propose pas, l’import prépare localement le scan anglais de la même référence et conserve sa langue/provenance dans `images_meta/`. Les Zarbi de la sous-collection EX et certaines promos HGSS utilisent une correspondance vérifiée dans le jeu de données public Pokémon TCG API (numéro, numéro Pokédex et PV). Ces scans restent anglais et sont signalés comme tels ; les textes de la fiche restent français.

Réparation ponctuelle d’un cache existant : `docker exec python python /projet/reparer_images.py`. La commande ne modifie ni les exemplaires ni les textes ou embeddings. `docker exec python python /projet/actualiser_bilan.py` régénère ensuite les compteurs sans téléchargement ni calcul de vecteurs. Les fichiers WebP et PNG sont servis par l’API locale ; aucun appel externe n’est nécessaire à l’affichage.

## Disponibilité et CAP

MongoDB est la référence durable, en replica set ; les écritures utilisent `w: majority` avec un délai maximal de cinq secondes pour obtenir l’accusé de réception. Sans majorité, les écritures ne sont pas confirmées. Un délai dépassé n’implique pas nécessairement que l’écriture n’a pas été appliquée : les identifiants déterministes permettent de relancer l’import.

PostgreSQL contient un index reconstruit lors de l’import. Son arrêt rend uniquement la recherche par sens indisponible. Redis conserve un historique non durable du point de vue métier : une panne retire cette fonction mais laisse fonctionner la collection et les fiches. On ne qualifie donc pas toute l’architecture d’AP du seul fait de ce mode dégradé.

Redis utilise une transaction `LPUSH`, `LTRIM 0 9`, `EXPIRE 1800`. Les prix sont stockés et additionnés en centimes entiers pour éviter les imprécisions monétaires.

## Validation

Après l’import :

```powershell
docker exec -e PYTHONPATH=/projet -e POKEMON_INTEGRATION=1 python python -m unittest discover -s /projet/tests -v
```

Ces tests vérifient les statistiques, les filtres, la pagination, la collection vide, les ajouts simples et répétés, le retrait d’un exemplaire, les métadonnées facultatives et la recherche limitée aux possessions. Les nouveaux tests d’écriture utilisent des bases MongoDB jetables au nom aléatoire, supprimées après chaque test. Les historiques de test utilisent des UUID distincts et sont supprimés. La collection de l’application est préservée.

## Sources et présentation

- Données et illustrations : TCGdex, https://tcgdex.dev/fr/ ; API française https://api.tcgdex.net/v2/fr/cards.
- Modèle : https://huggingface.co/Xenova/multilingual-e5-small (MIT).
- Modèle d’origine et conventions d’encodage : https://huggingface.co/intfloat/multilingual-e5-small.
- Cartes Pokémon : illustrations et marques de leurs ayants droit ; ce projet est une démonstration pédagogique non officielle.
- Mentionner l’aide de l’IA à l’implémentation sur une diapositive, conformément au livret. Chaque membre doit pouvoir expliquer ses DAO et la circulation des données.
