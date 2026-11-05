"""Récupère les illustrations absentes sans réimporter les textes ou les exemplaires."""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from importer import RACINE, API, obtenir_json, recuperer_illustration
from pokemon.connexions import base_mongo


def reparer(carte):
    raw = obtenir_json(API + '/cards/' + carte['id'].replace('%', '%25'),
                       RACINE / 'fiches' / (carte['id'] + '.json'))
    return carte['_id'], recuperer_illustration(raw)


if __name__ == '__main__':
    base = base_mongo()
    cartes = [c for c in base.catalogue.find({'categorie': 'Pokémon'})
              if not c.get('image_locale') or not any(
                  (RACINE / 'images' / (c['id'] + extension)).exists() for extension in ['.webp', '.png'])]
    reussies, echecs, erreurs = 0, [], []
    print('Illustrations à récupérer :', len(cartes), flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        taches = [pool.submit(reparer, c) for c in cartes]
        for i, future in enumerate(as_completed(taches), 1):
            try:
                ref, meta = future.result()
                base.catalogue.update_one({'_id': ref}, {'$set': meta})
                if meta['image_locale']:
                    reussies += 1
                else:
                    echecs.append(ref)
            except Exception as e:
                erreurs.append(str(e))
            if i % 50 == 0:
                print(f'{i}/{len(cartes)} traitées ; {reussies} récupérées.', flush=True)
    bilan = {'recuperees': reussies, 'sans_image': echecs, 'erreurs': erreurs}
    (RACINE / 'bilan_images.json').write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'recuperees': reussies, 'sans_image': len(echecs), 'erreurs': len(erreurs)}), flush=True)
