# Pertinence de la recherche

La liste des références possédées vient de MongoDB à chaque requête. PostgreSQL filtre les passages et l'ancien index de fiches par ces références **avant le classement**, puis choisit le passage le plus proche par carte.

## Seuil relatif à 95 % et plancher absolu à 0,841

La similarité cosinus vaut `1 - distance cosinus` : plus elle est grande, plus les textes sont proches. Pour chaque recherche, le seuil est `max(0,841 ; 0,95 × meilleure similarité)` parmi les cartes possédées et indexées avec le modèle utilisé. Les deux conditions sont nécessaires : atteindre 95 % du meilleur score et le plancher absolu de 0,841. Les résultats sont triés par similarité décroissante, puis par référence en cas d'égalité.

Le curseur **Top K** règle le nombre de cartes affichées, entre **1 et le nombre total de cartes admissibles**. Sa valeur initiale est 10, ou le maximum disponible s'il est plus petit. La valeur choisie est conservée pour les recherches suivantes, ramenée au nouveau maximum si nécessaire. Le maximum n'est pas plafonné à dix. Avec une seule carte admissible, l'interface affiche directement ce résultat ; sans résultat, elle masque le curseur. Les résultats sont conservés dans la session : déplacer le curseur ne relance ni l'encodage ni la requête de recherche. L'API accepte `top_k` (entier positif, 10 par défaut) ou `null` pour obtenir toutes les cartes qui passent le seuil, comme le fait Streamlit.

Exemples : si le meilleur score est `0,90`, le seuil est `0,855`. S'il est `0,85`, le seuil est `0,841`, car le plancher absolu domine. Si même le meilleur score est inférieur à `0,841`, aucun résultat n'est retenu. L'API renvoie pour chaque résultat la distance, la similarité et le seuil effectif. L'interface affiche le rang, la similarité et le passage correspondant ; la console développeur distingue les rejets par seuil absolu et par seuil relatif.

Le seuil relatif est recalculé à chaque recherche et dépend des cartes possédées ; le plancher 0,841 est un paramètre fixé, pas le résultat d'une nouvelle calibration. Une collection vide, sans vecteur correspondant au modèle, ou dont toutes les similarités restent sous le plancher renvoie une liste vide. Une similarité n'est pas une probabilité de pertinence : les seuils ne garantissent ni une compréhension correcte ni dix résultats. Aucun réimport ni recalcul des embeddings n'est nécessaire pour ce changement de sélection.

## Ancienne calibration du 5 novembre 2026 (historique)

L'ancien seuil fixe **0,12265604734420776** était associé à `Xenova/multilingual-e5-small@761b726dd34fb83930e26aab4e9ac3899aa1fa78`. Il n'est plus utilisé par la recherche. Les mesures ci-dessous évaluent uniquement cette ancienne règle, pas le classement dynamique actuel.

Six cartes témoins, dont les descriptions et effets sont vérifiés manuellement : Airmure EX8-26 (pioche), Abo Base3-46 (poison), Dracaufeu Base1-4 (incendies), Abra Base1-43 (télépathie), Pikachu Base1-58 (orages), Carapuce Base1-63 (protection). Douze requêtes de calibration : sept besoins présents et cinq absents, comprenant des effets voisins absents (soin, sommeil, récupération depuis la défausse) et des demandes hors sujet. Chaque couple requête/carte est étiqueté : 72 distances mesurées. Douze autres formulations sont réservées à la validation, soit 72 autres distances.

Le script teste les frontières entre toutes les distances de calibration et maximise F0.5, qui privilégie la précision par rapport au rappel. En cas d'égalité, le seuil le plus strict est retenu. La validation n'intervient pas dans ce choix. L'inférence est unitaire, comme dans l'API : le padding par lots peut modifier légèrement les résultats de ce modèle quantifié.

| Jeu | Couples pertinents retenus | Faux positifs | Pertinents écartés | Précision | Rappel |
| --- | ---: | ---: | ---: | ---: | ---: |
| Calibration | 3 | 0 | 4 | 100 % | 42,9 % |
| Validation indépendante | 2 | 0 | 5 | 100 % | 28,6 % |

**Limite importante : ce seuil est conservateur.** Sur ce jeu témoin, les recherches sur les incendies et la télépathie passent ; plusieurs formulations sur la pioche et le poison sont écartées malgré leur pertinence. Le modèle confond parfois poison et paralysie : élargir simplement le seuil réintroduirait des faux positifs. Le seuil réduit le bruit mais ne garantit pas une compréhension correcte de toute requête ; les filtres classiques restent disponibles. Ces résultats sur six cartes ne constituent pas une évaluation de tout le catalogue. Améliorer le rappel nécessite une meilleure représentation ou un autre modèle, puis une nouvelle calibration sur un jeu plus large.

Les [mesures complètes](calibration_recherche.json) contiennent le modèle, les exemples, les étiquettes, les distances et les statistiques. Aucune requête réelle de visiteur n'est enregistrée par ce mécanisme.

## Reproduire l'ancienne calibration

Depuis le projet déjà importé :

```powershell
docker exec -w /projet python python calibrer_recherche.py
```

Cette commande lit les index sans les modifier et écrit `travail/pokemon/calibration_recherche.json`. Le script, son rapport et `projet/pokemon/seuil_recherche.json` sont conservés comme historique de la méthode précédente. Modifier ce fichier ne change plus la recherche active, dont le seuil relatif est calculé en SQL dans `RechercheDAO.rechercher`.
