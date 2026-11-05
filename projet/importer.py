"""Importer une démo TCGdex, ses images et son index sémantique avant utilisation."""
import argparse
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

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


def fiche_et_image(resume, hors_ligne):
    identifiant = resume['id']
    raw = obtenir_json(API + '/cards/' + identifiant, RACINE / 'fiches' / (identifiant + '.json'), hors_ligne)
    carte = normaliser(raw)
    fichier = RACINE / 'images' / (identifiant + '.webp')
    if carte['image_source'] and not fichier.exists() and not hors_ligne:
        try:
            telecharger(carte['image_source'] + '/low.webp', fichier)
        except requests.RequestException as erreur:
            print('Image indisponible :', identifiant, str(erreur), flush=True)
    carte['image_locale'] = fichier.exists()
    return carte


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extensions', default='base1,base2,base3')
    parser.add_argument('--limite', type=int, default=240)
    parser.add_argument('--exemplaires', type=int, default=360)
    parser.add_argument('--toutes', action='store_true', help='Importer toutes les fiches françaises (long)')
    parser.add_argument('--hors-ligne', action='store_true', help='Utiliser uniquement le cache local')
    parser.add_argument('--sans-vecteurs', action='store_true')
    args = parser.parse_args()
    if args.limite < 1 or args.exemplaires < 1:
        parser.error('Les volumes doivent être positifs.')
    catalogue = obtenir_json(API + '/cards', RACINE / 'catalogue_fr.json', args.hors_ligne)
    extensions = obtenir_json(API + '/sets', RACINE / 'extensions_fr.json', args.hors_ligne)
    selection = catalogue
    if not args.toutes:
        ids = {s.strip() for s in args.extensions.split(',')}
        selection = [c for c in catalogue if c['id'].rsplit('-', 1)[0] in ids][:args.limite]
    if not selection:
        raise RuntimeError('Aucune carte sélectionnée : vérifier les identifiants des extensions.')
    print(f'{len(catalogue)} résumés disponibles ; {len(selection)} fiches sélectionnées.', flush=True)
    cartes, echecs = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        taches = {pool.submit(fiche_et_image, c, args.hors_ligne): c['id'] for c in selection}
        for future in as_completed(taches):
            try:
                cartes.append(future.result())
            except Exception as erreur:
                echecs.append({'id': taches[future], 'erreur': str(erreur)})
            if (len(cartes) + len(echecs)) % 25 == 0:
                print(f'{len(cartes)} fiches préparées, {len(echecs)} erreurs.', flush=True)
    if echecs:
        (RACINE / 'erreurs_import.json').write_text(json.dumps(echecs, ensure_ascii=False, indent=2), encoding='utf-8')
        raise RuntimeError(f'{len(echecs)} fiches manquantes. Relancer pour reprendre le cache ; bases inchangées.')
    cartes.sort(key=lambda c: c['_id'])
    pokemon = [c for c in cartes if c['categorie'] == 'Pokémon']
    if not pokemon:
        raise RuntimeError('Aucune carte Pokémon dans cette sélection.')
    alea = random.Random(42)
    possedees = pokemon[:min(len(pokemon), args.exemplaires)]
    exemplaires = []
    for i in range(args.exemplaires):
        carte = possedees[i] if i < len(possedees) else alea.choice(possedees)
        centimes = alea.randint(50, 12000)
        exemplaires.append({'_id': f'exemplaire-{i + 1:05}', 'carte_ref': carte['_id'],
                            'etat': alea.choice(['Excellent', 'Très bon', 'Bon', 'Joué']),
                            'variante': alea.choice(carte['variantes']), 'prix_centimes': centimes,
                            'prix_achat': centimes / 100, 'date_achat': '2026-11-05'})
    base = base_mongo()
    base.catalogue.bulk_write([ReplaceOne({'_id': c['_id']}, c, upsert=True) for c in cartes])
    base.catalogue.delete_many({'_id': {'$nin': [c['_id'] for c in cartes]}})
    base.exemplaires.bulk_write([ReplaceOne({'_id': e['_id']}, e, upsert=True) for e in exemplaires])
    base.exemplaires.delete_many({'_id': {'$nin': [e['_id'] for e in exemplaires]}})
    base.exemplaires.create_index('carte_ref')
    base.catalogue.create_index([('nom', 1), ('_id', 1)])
    for champ in ['extension_id', 'types', 'rarete']:
        base.catalogue.create_index(champ)
    print(f'MongoDB : {len(cartes)} fiches, {len(exemplaires)} exemplaires.', flush=True)
    indexees = [c for c in cartes if c['categorie'] == 'Pokémon' and c['texte']]
    if not args.sans_vecteurs:
        preparer_modele(args.hors_ligne)
        dao = RechercheDAO()
        dao.preparer()
        lignes = []
        for debut in range(0, len(indexees), 20):
            lot = indexees[debut:debut + 20]
            vecteurs = encoder([c['texte'] for c in lot])
            lignes.extend((c['_id'], c['texte'], identite_modele(), v) for c, v in zip(lot, vecteurs))
            print(f'Vectorisation : {min(debut + 20, len(indexees))}/{len(indexees)}', flush=True)
        dao.synchroniser(lignes)
    bilan = {'source': API, 'importe_le': datetime.now(timezone.utc).isoformat(),
             'resumes_fr': len(catalogue), 'extensions_fr': len(extensions),
             'fiches_importees': len(cartes), 'pokemon': len(pokemon), 'textes_utiles': len(indexees),
             'images_locales': sum(c['image_locale'] for c in cartes),
             'exemplaires': len(exemplaires), 'cartes_possedees': len(possedees),
             'index_semantique': not args.sans_vecteurs, 'donnees_achat': 'simulées, graine 42'}
    (RACINE / 'bilan_import.json').write_text(json.dumps(bilan, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(bilan, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
