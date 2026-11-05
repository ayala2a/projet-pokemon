"""Bilan des ressources réellement présentes, sans réimport ni vectorisation."""
import json
from collections import Counter
from datetime import datetime, timezone

from importer import RACINE, bilan_catalogue
from pokemon.connexions import base_mongo, connexion_postgres
from pokemon.dao import RechercheDAO
from pokemon.embeddings import identite_modele


if __name__ == '__main__':
    base = base_mongo()
    fichier = RACINE / 'bilan_import.json'
    bilan = json.loads(fichier.read_text()) if fichier.exists() else {}
    index = RechercheDAO().etat_index()
    bilan['verifie_le'] = datetime.now(timezone.utc).isoformat()
    bilan['catalogue_cumule'] = bilan_catalogue(base, index, identite_modele())
    bilan['images_langues'] = dict(Counter(
        c.get('image_langue') or 'fr' for c in base.catalogue.find({'categorie': 'Pokémon', 'image_locale': True})))
    bilan['images_locales'] = base.catalogue.count_documents({'image_locale': True})
    bilan['images_pokemon_locales'] = sum(bilan['images_langues'].values())
    with connexion_postgres() as c:
        nombre, cartes = c.execute('SELECT count(*), count(DISTINCT carte_ref) FROM pokemon_passages').fetchone()
    bilan['passages_semantiques'] = {'passages': nombre, 'cartes': cartes}
    bilan['exemplaires'] = base.exemplaires.count_documents({})
    bilan['cartes_possedees'] = len(base.exemplaires.distinct('carte_ref'))
    fichier.write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'images_langues': bilan['images_langues'], 'images_manquantes':
        len(bilan['catalogue_cumule']['images_manquantes']), 'index': bilan['passages_semantiques'],
        'exemplaires_preserves': bilan['exemplaires']}, ensure_ascii=False))
