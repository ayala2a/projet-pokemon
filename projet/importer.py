"""Importer une démo TCGdex, ses images et son index sémantique avant utilisation."""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote
from threading import Lock

import requests
from pymongo import ReplaceOne
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pokemon.connexions import base_mongo
from pokemon.dao import RechercheDAO
from pokemon.embeddings import DOSSIER_MODELE, MODELE, encoder, identite_modele
from pokemon.textes import normaliser

RACINE = Path(os.getenv('POKEMON_DATA_DIR', '/travail/pokemon'))
API = 'https://api.tcgdex.net/v2/fr'
VERROU_SOURCES_IMAGES = Lock()


def client_http():
    session = requests.Session()
    session.headers['User-Agent'] = 'PokemonCollection-M2/1.0 (educational demo)'
    session.mount('https://', HTTPAdapter(max_retries=Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    return session


def obtenir_json(url, fichier, hors_ligne=False):
    if fichier.exists():
        return json.loads(fichier.read_text(encoding='utf-8'))
    if hors_ligne:
        raise RuntimeError('Cache absent : ' + str(fichier))
    with client_http() as http:
        reponse = http.get(url, timeout=(10, 60))
        reponse.raise_for_status()
        valeur = reponse.json()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix('.tmp')
    temporaire.write_text(json.dumps(valeur, ensure_ascii=False), encoding='utf-8')
    temporaire.replace(fichier)
    return valeur


def telecharger(url, fichier):
    if fichier.exists():
        return
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix('.part')
    with client_http() as http, http.get(url, stream=True, timeout=(10, 180)) as reponse:
        reponse.raise_for_status()
        with temporaire.open('wb') as sortie:
            for morceau in reponse.iter_content(1024 * 1024):
                sortie.write(morceau)
    temporaire.replace(fichier)


def preparer_modele(hors_ligne):
    manifeste = DOSSIER_MODELE / 'manifest.json'
    if manifeste.exists() and all((DOSSIER_MODELE / f).exists() for f in ['model.onnx', 'tokenizer.json']):
        return
    if hors_ligne:
        raise RuntimeError('Modèle absent : effectuer une première préparation connectée.')
    with client_http() as http:
        reponse = http.get('https://huggingface.co/api/models/' + MODELE, timeout=60)
        reponse.raise_for_status()
        revision = reponse.json()['sha']
    racine = 'https://huggingface.co/' + MODELE + '/resolve/' + revision + '/'
    print('Téléchargement du modèle multilingue ONNX (une seule fois)…', flush=True)
    telecharger(racine + 'tokenizer.json', DOSSIER_MODELE / 'tokenizer.json')
    telecharger(racine + 'onnx/model_quantized.onnx', DOSSIER_MODELE / 'model.onnx')
    manifeste.write_text(json.dumps({'modele': MODELE, 'revision': revision}), encoding='utf-8')


def fiche_et_image(resume, hors_ligne, extensions):
    identifiant = resume['id']
    raw = obtenir_json(API + '/cards/' + quote(identifiant, safe=''), RACINE / 'fiches' / (identifiant + '.json'), hors_ligne)
    raw = {**raw, 'set': {**(raw.get('set') or {}), **extensions.get((raw.get('set') or {}).get('id'), {})}}
    carte = normaliser(raw)
    carte.update(recuperer_illustration(raw, hors_ligne))
    return carte


def recuperer_illustration(raw, hors_ligne=False):
    """Même référence TCGdex, FR en priorité ; secours EN signalé, toujours local."""
    identifiant = raw['id']
    fichier = RACINE / 'images' / (identifiant + '.webp')
    provenance = RACINE / 'images_meta' / (identifiant + '.json')
    if fichier.exists() or fichier.with_suffix('.png').exists():
        meta = json.loads(provenance.read_text()) if provenance.exists() else {'langue': 'fr', 'source': raw.get('image')}
        return {'image_locale': True, 'image_langue': meta['langue'], 'image_source_affichage': meta.get('source')}
    if not hors_ligne:
        for langue in ['fr', 'en']:
            try:
                donnees = raw if langue == 'fr' else obtenir_json(
                    'https://api.tcgdex.net/v2/en/cards/' + quote(identifiant, safe=''),
                    RACINE / 'fiches_en' / (identifiant + '.json'))
                if donnees.get('id') != identifiant or not donnees.get('image'):
                    continue
                source = donnees['image']
                telecharger(source + '/low.webp', fichier)
                provenance.parent.mkdir(parents=True, exist_ok=True)
                provenance.write_text(json.dumps({'langue': langue, 'source': source}), encoding='utf-8')
                return {'image_locale': True, 'image_langue': langue, 'image_source_affichage': source}
            except requests.RequestException:
                continue
        # Ces deux sous-collections ont des identifiants différents entre les
        # bases. Vérifier numéro, Pokédex et PV avant d'utiliser l'autre scan.
        numero = unquote(str(raw.get('localId', '')))
        autre_set = 'ex10' if identifiant.startswith('exu-') else 'hsp' if identifiant.startswith('hgssp-') else None
        if autre_set:
            try:
                with VERROU_SOURCES_IMAGES:
                    donnees = obtenir_json(
                        'https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/cards/en/' + autre_set + '.json',
                        RACINE / 'sources_images' / (autre_set + '.json'))
                carte = next((c for c in donnees if c['id'] == autre_set + '-' + numero), None)
                if (carte and carte.get('number') == numero and
                    set(carte.get('nationalPokedexNumbers') or []) == set(raw.get('dexId') or []) and
                    str(carte.get('hp')) == str(raw.get('hp'))):
                    source = carte['images']['small']
                    telecharger(source, fichier.with_suffix('.png'))
                    provenance.parent.mkdir(parents=True, exist_ok=True)
                    provenance.write_text(json.dumps({'langue': 'en', 'source': source}), encoding='utf-8')
                    return {'image_locale': True, 'image_langue': 'en', 'image_source_affichage': source}
            except requests.RequestException:
                pass
    return {'image_locale': False, 'image_langue': None, 'image_source_affichage': None}


def indexer_cartes(cartes, hors_ligne):
    """Comparer texte normalisé et révision du modèle ; sauvegarder chaque lot."""
    preparer_modele(hors_ligne)
    modele = identite_modele()
    dao = RechercheDAO()
    dao.preparer()
    eligibles = [c for c in cartes if c['categorie'] == 'Pokémon' and c['texte']]
    etat = dao.etat_index([c['_id'] for c in eligibles])
    manquantes = [c for c in eligibles if etat.get(c['_id']) != (c['texte'], modele)]
    reutilises = len(eligibles) - len(manquantes)
    print(f'Index : {reutilises} vecteurs déjà à jour ; {len(manquantes)} à préparer.', flush=True)
    for debut in range(0, len(manquantes), 20):
        lot = manquantes[debut:debut + 20]
        vecteurs = encoder([c['texte'] for c in lot])
        dao.synchroniser([(c['_id'], c['texte'], modele, v) for c, v in zip(lot, vecteurs)])
        print(f'Vectorisation : {min(debut + 20, len(manquantes))}/{len(manquantes)} (lot sauvegardé)', flush=True)
    exclus = [c['_id'] for c in cartes if c['categorie'] != 'Pokémon' or not c['texte']]
    if exclus:
        dao.synchroniser([], exclus)
    return {'vecteurs_reutilises': reutilises, 'vecteurs_calcules': len(manquantes)}, dao.etat_index(), modele


def bilan_catalogue(base, index, modele):
    """Périmètre réel cumulé, distinct du seul lot de cette invocation."""
    blocs, extensions, manquantes = {}, {}, []
    for c in base.catalogue.find({'categorie': 'Pokémon'}):
        bloc = blocs.setdefault(c.get('bloc_id', 'inconnu'), {
            'nom': c.get('bloc', 'Non renseigné'), 'cartes': 0, 'images_manquantes': 0,
            'textes_exploitables': 0, 'cartes_indexees': 0})
        extension = extensions.setdefault(c['extension_id'], {'nom': c['extension'], 'bloc': c.get('bloc'), 'cartes': 0})
        extension['cartes'] += 1
        bloc['cartes'] += 1
        if not c.get('image_locale'):
            bloc['images_manquantes'] += 1
            manquantes.append(c['_id'])
        if c.get('texte'):
            bloc['textes_exploitables'] += 1
            if index is not None and index.get(c['_id']) == (c['texte'], modele):
                bloc['cartes_indexees'] += 1
    return {'blocs': blocs, 'extensions': extensions, 'images_manquantes': sorted(manquantes),
            'cartes_pokemon': sum(b['cartes'] for b in blocs.values()),
            'cartes_indexees': sum(b['cartes_indexees'] for b in blocs.values()) if index is not None else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choix = parser.add_mutually_exclusive_group()
    choix.add_argument('--extensions', help='Identifiants séparés par des virgules ; défaut : base1,base2,base3')
    choix.add_argument('--blocs', help='Identifiants de blocs TCGdex, par exemple base ou swsh,sv')
    choix.add_argument('--toutes', action='store_true', help='Importer toutes les fiches françaises (long)')
    parser.add_argument('--limite', type=int, default=240, help='Nombre maximal de fiches ; 0 = aucune limite')
    parser.add_argument('--hors-ligne', action='store_true', help='Utiliser uniquement le cache local')
    parser.add_argument('--sans-vecteurs', action='store_true')
    args = parser.parse_args()
    if args.limite < 0:
        parser.error('Les volumes ne peuvent pas être négatifs.')
    catalogue = obtenir_json(API + '/cards', RACINE / 'catalogue_fr.json', args.hors_ligne)
    extensions = obtenir_json(API + '/sets', RACINE / 'extensions_fr.json', args.hors_ligne)
    selection = catalogue
    if not args.toutes:
        if args.blocs:
            ids = set()
            for bloc in filter(None, (s.strip() for s in args.blocs.split(','))):
                serie = obtenir_json(API + '/series/' + bloc, RACINE / 'blocs' / (bloc + '.json'), args.hors_ligne)
                ids.update(s['id'] for s in serie['sets'])
        else:
            ids = {s.strip() for s in (args.extensions or 'base1,base2,base3').split(',')}
        selection = [c for c in catalogue if c['id'].rsplit('-', 1)[0] in ids]
        if args.limite:
            selection = selection[:args.limite]
    if not selection:
        raise RuntimeError('Aucune carte sélectionnée : vérifier les identifiants des extensions.')
    print(f'{len(catalogue)} résumés disponibles ; {len(selection)} fiches sélectionnées.', flush=True)
    metadonnees = {}
    for identifiant in sorted({c['id'].rsplit('-', 1)[0] for c in selection}):
        extension = obtenir_json(API + '/sets/' + identifiant,
                                  RACINE / 'extensions' / (identifiant + '.json'), args.hors_ligne)
        # Ne pas imbriquer la liste complète des cartes dans chaque fiche.
        metadonnees[identifiant] = {k: extension[k] for k in ['id', 'name', 'serie'] if k in extension}
    cartes, echecs = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        taches = {pool.submit(fiche_et_image, c, args.hors_ligne, metadonnees): c['id'] for c in selection}
        for future in as_completed(taches):
            try:
                cartes.append(future.result())
            except Exception as erreur:
                echecs.append({'id': taches[future], 'erreur': str(erreur)})
                print('Fiche à reprendre :', taches[future], str(erreur), flush=True)
            if (len(cartes) + len(echecs)) % 100 == 0:
                print(f'{len(cartes)} fiches préparées, {len(echecs)} erreurs.', flush=True)
    if echecs:
        (RACINE / 'erreurs_import.json').write_text(json.dumps(echecs, ensure_ascii=False, indent=2), encoding='utf-8')
        raise RuntimeError(f'{len(echecs)} fiches manquantes. Relancer pour reprendre le cache ; bases inchangées.')
    cartes.sort(key=lambda c: c['_id'])
    pokemon = [c for c in cartes if c['categorie'] == 'Pokémon']
    if not pokemon:
        raise RuntimeError('Aucune carte Pokémon dans cette sélection.')
    base = base_mongo()
    base.catalogue.bulk_write([ReplaceOne({'_id': c['_id']}, c, upsert=True) for c in cartes])
    # Aucun effacement : import cumulatif et exemplaires existants conservés.
    base.exemplaires.create_index('carte_ref')
    base.catalogue.create_index([('nom', 1), ('_id', 1)])
    for champ in ['bloc_id', 'extension_id', 'types', 'rarete']:
        base.catalogue.create_index(champ)
    print(f'MongoDB : {len(cartes)} fiches importées, {base.exemplaires.count_documents({})} exemplaires conservés.', flush=True)
    indexees = [c for c in cartes if c['categorie'] == 'Pokémon' and c['texte']]
    index, modele, compteurs = None, None, {}
    if not args.sans_vecteurs:
        compteurs, index, modele = indexer_cartes(cartes, args.hors_ligne)
        from indexer_passages import indexer
        indexer(cartes)
    bilan = {'source': API, 'importe_le': datetime.now(timezone.utc).isoformat(),
             'resumes_fr': len(catalogue), 'extensions_fr': len(extensions),
             'fiches_importees': len(cartes), 'pokemon': len(pokemon), 'textes_utiles': len(indexees),
             'images_locales': sum(c['image_locale'] for c in cartes),
             'blocs_importes': sorted({c['bloc'] for c in cartes}),
             'extensions_demandees': sorted(ids) if not args.toutes else None,
             'extensions_sans_fiche_francaise': sorted(ids - {c['id'].rsplit('-', 1)[0] for c in catalogue}) if not args.toutes else [],
             'extensions_importees': sorted({c['extension_id'] for c in cartes}),
             'exemplaires': base.exemplaires.count_documents({}),
             'cartes_possedees': len(base.exemplaires.distinct('carte_ref')),
             'index_semantique': not args.sans_vecteurs, **compteurs,
             'catalogue_cumule': bilan_catalogue(base, index, modele)}
    (RACINE / 'bilan_import.json').write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding='utf-8')
    resume = {**bilan, 'catalogue_cumule': {k: v for k, v in bilan['catalogue_cumule'].items()
                                         if k not in ['images_manquantes', 'extensions']}}
    resume['catalogue_cumule']['nombre_images_manquantes'] = len(bilan['catalogue_cumule']['images_manquantes'])
    print(json.dumps(resume, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
