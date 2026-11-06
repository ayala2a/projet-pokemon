# Catalogue français importé — 5 novembre 2026

Le périmètre cumulé contient **3 174 cartes Pokémon**, issues de **37 extensions françaises disponibles** dans TCGdex. Il conserve les fiches Base préexistantes et ajoute les blocs EX, Diamant & Perle, Platine et HeartGold SoulSilver. Base a été complété pour atteindre la cible sans introduire un autre bloc.

| Bloc | Cartes Pokémon | Images locales | Images manquantes | Cartes indexées pour la recherche |
|---|---:|---:|---:|---:|
| Base | 283 | 283 | 0 | 283 |
| EX | 1 361 | 1 361 | 0 | 1 301 |
| Diamant & Perle | 784 | 784 | 0 | 776 |
| Platine | 365 | 365 | 0 | 352 |
| HeartGold SoulSilver | 381 | 381 | 0 | 352 |
| **Total** | **3 174** | **3 174** | **0** | **3 064** |

Les **110 cartes sans texte exploitable** restent consultables et filtrables. Les 746 scans français indisponibles ont été remplacés par des scans anglais vérifiés, explicitement signalés dans l’interface : 710 provenant de TCGdex et 36 du jeu de données public Pokémon TCG API. Les 2 428 autres illustrations sont françaises. Tous les fichiers sont locaux ; les fiches et les effets restent en français.

## Extensions retenues

Toutes les fiches françaises disponibles des extensions ci-dessous sont importées, sans limite de cartes ni tronquage d’une extension :

| Bloc | Extensions |
|---|---|
| Base | `base1` Set de Base ; `base2` Jungle ; `base3` Fossile ; `base5` Team Rocket ; `basep` Wizards Black Star Promos |
| EX | `ex1` Rubis & Saphir ; `ex2` Tempête de sable ; `ex3` Dragon ; `ex4` Team Magma vs Team Aqua ; `ex5` Légendes Oubliées ; `ex6` Rouge Feu & Vert Feuille ; `ex8` Deoxys ; `ex9` Émeraude ; `ex10` Forces Cachées ; `exu` Collection Zarbi ; `ex11` Espèces Delta ; `ex12` Créateurs de légendes ; `ex13` Fantômes Holon ; `ex14` Gardiens de Cristal ; `ex15` Île des Dragons ; `ex16` Gardiens du Pouvoir |
| Diamant & Perle | `dp1` Diamant & Perle ; `dp2` Trésors Mystérieux ; `dp3` Merveilles Secrètes ; `dp4` Duels au Sommets ; `dp5` Aube Majestueuse ; `dp6` Éveil des Légendes ; `dp7` Tempête ; `dpp` Promo DP |
| Platine | `pl1` Platine ; `pl2` Rivaux Émergeants ; `pl3` Vainqueurs Suprêmes |
| HeartGold SoulSilver | `hgss1` HeartGold SoulSilver ; `hgss2` Déchaînement ; `hgss3` Indomptable ; `hgss4` Triomphant ; `hgssp` Promo HGSS |

La série Base déclare également `wp` (W Promotional), mais le catalogue français ne fournit aucune fiche pour cette extension dans cet instantané. Les nombres officiels des extensions peuvent inclure des cartes absentes du catalogue français. Les volumes ci-dessus comptent les fiches réellement disponibles ; aucune carte manquante n’a été inventée.

## Reproduire et reprendre

```powershell
docker exec python python /projet/importer.py --blocs base,ex,dp,pl,hgss --limite 0
# Une fois le cache constitué : aucune connexion à TCGdex nécessaire
docker exec python python /projet/importer.py --blocs base,ex,dp,pl,hgss --limite 0 --hors-ligne
```

Les 3 679 fiches détaillées stockées dans MongoDB comprennent aussi des cartes Dresseur et Énergie. L’interface n’affiche que les 3 174 cartes de catégorie Pokémon. Aucun exemplaire n’est créé par l’import ; la collection locale est conservée.

L’indexation compare le texte normalisé et la révision du modèle : les 189 vecteurs préexistants sont réutilisés, seuls les 2 875 nouveaux vecteurs sont préparés. Les lots sont enregistrés progressivement et une relance identique ne recalcule aucun vecteur à jour.

Le bilan détaillé, avec la liste des références sans illustration et les compteurs par extension, est dans [catalogue_bilan.json](catalogue_bilan.json). L’original local est `travail/pokemon/bilan_import.json`.

## Source et fonctionnement local

Les identifiants ont été vérifiés auprès de l’[API française TCGdex](https://api.tcgdex.net/v2/fr/series), puis dans les détails des séries `base`, `ex`, `dp`, `pl` et `hgss`. Les fiches, les images disponibles et le modèle sont téléchargés avant utilisation. La pagination, les filtres et les fiches interrogent uniquement FastAPI et les bases locales. La recherche n’interroge que les références possédées et classe les résultats par similarité décroissante, avec un minimum de 95 % du meilleur score et un plancher de 0,841. Le curseur Top K choisit combien en afficher, jusqu'au nombre total de cartes admissibles.

Les scans anglais complémentaires sont référencés dans le [jeu de données Pokémon TCG API](https://github.com/PokemonTCG/pokemon-tcg-data), avec vérification du numéro, du Pokédex et des PV avant téléchargement. La recherche utilise maintenant des passages distincts et affiche l’effet ou la description correspondant au résultat.
