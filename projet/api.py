"""API Pokémon : tous les accès aux données passent par les DAO."""
import logging
import os
import re
from pathlib import Path
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError
from pokemon.dao import CollectionDAO, HistoriqueDAO, RechercheDAO
from pokemon.embeddings import ModeleAbsent, encoder, identite_modele
from pokemon.textes import centrer_requete

app = FastAPI(title='Pokécollection', description='Une collection de démonstration, sans compte.')
collection = CollectionDAO()
historique = HistoriqueDAO()
recherche = RechercheDAO()
IMAGES = Path(os.getenv('POKEMON_IMAGE_DIR', '/travail/pokemon/images'))

@app.exception_handler(PyMongoError)
async def mongo_indisponible(request, erreur):
    logging.warning('MongoDB indisponible : %s', erreur)
    return JSONResponse(status_code=503, content={'detail': 'La collection est momentanément indisponible.'})

@app.get('/sante')
def sante():
    return {'mongodb': collection.base.catalogue.count_documents({}),
            'exemplaires': collection.base.exemplaires.count_documents({}),
            'redis': historique.lire('diagnostic')[1]}

@app.get('/statistiques')
def statistiques():
    return collection.statistiques()

@app.get('/filtres')
def filtres():
    return collection.filtres()

@app.get('/collection')
def cartes(nom: str = '', extension: str = '', type_carte: str = '', rarete: str = '',
           page: Annotated[int, Query(ge=1)] = 1,
           taille: Annotated[int, Query(ge=1, le=48)] = 12):
    return collection.rechercher(nom, extension, type_carte, rarete, page, taille)

@app.get('/cartes/{reference}')
def fiche(reference: str):
    carte = collection.fiche(reference)
    if not carte:
        raise HTTPException(404, 'Cette carte ne fait pas partie de la collection.')
    return carte

class Consultation(BaseModel):
    carte_ref: str = Field(min_length=1, max_length=100)

@app.post('/sessions/{session}/consultations')
def consulter(session: UUID, consultation: Consultation):
    if not collection.fiche(consultation.carte_ref):
        raise HTTPException(404, 'Carte absente de la collection.')
    return {'historique_disponible': historique.enregistrer(str(session), consultation.carte_ref)}

@app.get('/sessions/{session}/consultations')
def dernieres_consultations(session: UUID):
    references, disponible = historique.lire(str(session))
    fiches = collection.fiches(references)
    return {'disponible': disponible, 'cartes': [fiches[ref] for ref in references if ref in fiches]}

class Requete(BaseModel):
    texte: str = Field(min_length=2, max_length=500)

@app.post('/recherche')
def recherche_semantique(requete: Requete):
    texte = requete.texte.strip()
    if len(texte) < 2:
        raise HTTPException(422, 'Saisissez une phrase de recherche.')
    try:
        references = collection.references()
        if not references:
            return {'resultats': []}
        vecteur = encoder([centrer_requete(texte)], requete=True)[0]
        resultats = recherche.rechercher(vecteur, references, identite_modele())
    except (psycopg.Error, ModeleAbsent, OSError, ImportError) as erreur:
        logging.warning('Recherche indisponible : %s', erreur)
        raise HTTPException(503, 'La recherche par sens est indisponible. Les filtres restent utilisables.') from erreur
    fiches = collection.fiches(x['carte_ref'] for x in resultats)
    return {'resultats': [{**x, 'carte': fiches[x['carte_ref']]} for x in resultats if x['carte_ref'] in fiches]}

@app.get('/images/{identifiant}')
def image(identifiant: str):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', identifiant):
        raise HTTPException(404)
    chemin = IMAGES / (identifiant + '.webp')
    if not chemin.is_file():
        raise HTTPException(404, 'Illustration non disponible localement.')
    return FileResponse(chemin, media_type='image/webp', headers={'Cache-Control': 'public, max-age=86400'})
