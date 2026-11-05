# Pertinence de la recherche

La liste des références possédées vient de MongoDB à chaque requête. PostgreSQL filtre les passages et l'ancien index de fiches par ces références **avant le classement**, choisit le passage le plus proche par carte, écarte les distances supérieures au seuil puis trie et limite à cinq cartes distinctes. Une collection sans correspondance renvoie une liste vide, sans remplissage. L'interface affiche alors « Aucun résultat suffisamment pertinent dans votre collection ».

## Calibration du 5 novembre 2026

Le seuil **0,12265604734420776** est associé à `Xenova/multilingual-e5-small@761b726dd34fb83930e26aab4e9ac3899aa1fa78`. Un changement de modèle exige une nouvelle calibration ; l'application refuse d'utiliser silencieusement ce seuil pour une autre révision.

Six cartes témoins, dont les descriptions et effets sont vérifiés manuellement : Airmure EX8-26 (pioche), Abo Base3-46 (poison), Dracaufeu Base1-4 (incendies), Abra Base1-43 (télépathie), Pikachu Base1-58 (orages), Carapuce Base1-63 (protection). Douze requêtes de calibration : sept besoins présents et cinq absents, comprenant des effets voisins absents (soin, sommeil, récupération depuis la défausse) et des demandes hors sujet. Chaque couple requête/carte est étiqueté : 72 distances mesurées. Douze autres formulations sont réservées à la validation, soit 72 autres distances.

Le script teste les frontières entre toutes les distances de calibration et maximise F0.5, qui privilégie la précision par rapport au rappel. En cas d'égalité, le seuil le plus strict est retenu. La validation n'intervient pas dans ce choix. L'inférence est unitaire, comme dans l'API : le padding par lots peut modifier légèrement les résultats de ce modèle quantifié.

| Jeu | Couples pertinents retenus | Faux positifs | Pertinents écartés | Précision | Rappel |
| --- | ---: | ---: | ---: | ---: | ---: |
| Calibration | 3 | 0 | 4 | 100 % | 42,9 % |
| Validation indépendante | 2 | 0 | 5 | 100 % | 28,6 % |

**Limite importante : ce seuil est conservateur.** Sur ce jeu témoin, les recherches sur les incendies et la télépathie passent ; plusieurs formulations sur la pioche et le poison sont écartées malgré leur pertinence. Le modèle confond parfois poison et paralysie : élargir simplement le seuil réintroduirait des faux positifs. Le seuil réduit le bruit mais ne garantit pas une compréhension correcte de toute requête ; les filtres classiques restent disponibles. Ces résultats sur six cartes ne constituent pas une évaluation de tout le catalogue. Améliorer le rappel nécessite une meilleure représentation ou un autre modèle, puis une nouvelle calibration sur un jeu plus large.

Les [mesures complètes](calibration_recherche.json) contiennent le modèle, les exemples, les étiquettes, les distances et les statistiques. Aucune requête réelle de visiteur n'est enregistrée par ce mécanisme.

## Reproduire

Depuis le projet déjà importé :

```powershell
docker exec -w /projet python python calibrer_recherche.py
```

Cette commande lit les index sans les modifier et écrit `travail/pokemon/calibration_recherche.json`. Elle ne change pas automatiquement le seuil actif. Pour publier une nouvelle calibration, examiner le rapport et la validation, conserver le rapport dans `docs/calibration_recherche.json`, puis reporter ses champs `modele` et `seuil_distance` dans `projet/pokemon/seuil_recherche.json` et redémarrer le service Python. Ni import ni démarrage ne recalibre automatiquement le seuil.
