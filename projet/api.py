"""API Pokémon : tous les accès aux données passent par les DAO."""
import logging
import os
import re
from pathlib import Path
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError
from pokemon.dao import CatalogueDAO, CollectionDAO, HistoriqueDAO, RechercheDAO
from pokemon.embeddings import ModeleAbsent, encoder, identite_modele
from pokemon.textes import centrer_requete
from pokemon import traces

app = FastAPI(title='Pokécollection', description='Catalogue et collection locale persistante, sans compte.')
collection = CollectionDAO()
catalogue = CatalogueDAO()
historique = HistoriqueDAO()
recherche = RechercheDAO()
IMAGES = Path(os.getenv('POKEMON_IMAGE_DIR', '/travail/pokemon/images'))


def identite_console(request):
    return traces.identite(request.headers.get('X-Poke-Session'), request.headers.get('X-Poke-Trace-Token'))


@app.middleware('http')
async def tracer_requete(request: Request, call_next):
    cle = identite_console(request)
    if request.url.path.startswith('/debug/') or request.headers.get('X-Poke-Debug') != '1' or not cle:
        return await call_next(request)
    trace, jeton, debut = traces.commencer(request.method, request.url.path,
                                         dict(request.query_params))
    statut = 500
    try:
        reponse = await call_next(request)
        statut = reponse.status_code
        reponse.headers['X-Request-ID'] = trace['requete_id']
        return reponse
    except Exception as erreur:
        traces.evenement('HTTP', 'Erreur', erreur=type(erreur).__name__, message=str(erreur))
        raise
    finally:
        traces.terminer(cle, trace, jeton, debut, statut)


def autoriser_console(request):
    cle = identite_console(request)
    if not cle:
        raise HTTPException(403, 'Session de console requise.')
    return cle


@app.get('/debug/traces', include_in_schema=False)
def lire_console(request: Request, inclure_images: bool = False):
    return JSONResponse({'requetes': traces.consulter(autoriser_console(request), inclure_images=inclure_images)},
                        headers={'Cache-Control': 'no-store'})


@app.delete('/debug/traces', include_in_schema=False)
def effacer_console(request: Request):
    traces.effacer(autoriser_console(request))
    return JSONResponse({'efface': True}, headers={'Cache-Control': 'no-store'})

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
def filtres(bloc: str = ''):
    return collection.filtres(bloc)

@app.get('/catalogue/filtres')
def filtres_catalogue(bloc: str = ''):
    return catalogue.filtres(bloc)

@app.get('/catalogue/perimetre')
def perimetre():
    return catalogue.perimetre()

@app.get('/catalogue')
def cartes_catalogue(nom: str = '', extension: str = '', type_carte: str = '', rarete: str = '', bloc: str = '',
                     page: Annotated[int, Query(ge=1)] = 1,
                     taille: Annotated[int, Query(ge=1, le=48)] = 12):
    return catalogue.rechercher(nom, extension, type_carte, rarete, page, taille, bloc)

@app.get('/collection')
def cartes(nom: str = '', extension: str = '', type_carte: str = '', rarete: str = '', bloc: str = '',
           page: Annotated[int, Query(ge=1)] = 1,
           taille: Annotated[int, Query(ge=1, le=48)] = 12):
    return collection.rechercher(nom, extension, type_carte, rarete, page, taille, bloc)

class InformationsExemplaire(BaseModel):
    etat: str | None = Field(default=None, max_length=40)
    variante: str | None = Field(default=None, max_length=60)
    prix_achat: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)

class AjoutExemplaires(InformationsExemplaire):
    references: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(min_length=1, max_length=200)
    requete_id: UUID = Field(default_factory=uuid4)

def informations_modele(modele):
    donnees = modele.model_dump(exclude={'references', 'requete_id'}, exclude_unset=True)
    if 'prix_achat' in donnees:
        prix = donnees['prix_achat']
        donnees['prix_centimes'] = int(prix * 100) if prix is not None else None
        donnees['prix_achat'] = float(prix) if prix is not None else None
    return donnees

@app.post('/collection/exemplaires')
def ajouter_exemplaires(ajout: AjoutExemplaires):
    try:
        return collection.ajouter(ajout.references, str(ajout.requete_id), informations_modele(ajout))
    except ValueError as erreur:
        raise HTTPException(404, str(erreur)) from erreur

@app.delete('/collection/exemplaires/{identifiant}')
def retirer_exemplaire(identifiant: str):
    if not collection.retirer(identifiant):
        raise HTTPException(404, 'Exemplaire introuvable.')
    return {'retire': True}


class SelectionCartes(BaseModel):
    references: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(min_length=1, max_length=200)


class SuppressionExemplaires(BaseModel):
    identifiants: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(min_length=1, max_length=10000)


@app.post('/collection/selection')
def selection_collection(selection: SelectionCartes):
    return collection.selection_suppression(selection.references)


@app.post('/collection/exemplaires/supprimer')
def supprimer_exemplaires(suppression: SuppressionExemplaires):
    return {'supprimes': collection.supprimer_exemplaires(suppression.identifiants)}

@app.patch('/collection/exemplaires/{identifiant}')
def modifier_exemplaire(identifiant: str, informations: InformationsExemplaire):
    donnees = informations_modele(informations)
    if not donnees:
        raise HTTPException(422, 'Aucune information à modifier.')
    if not collection.modifier(identifiant, donnees):
        raise HTTPException(404, 'Exemplaire introuvable.')
    return {'modifie': True}

@app.get('/cartes/{reference}')
def fiche(reference: str):
    carte = collection.fiche(reference)
    if not carte:
        raise HTTPException(404, 'Cette carte est absente du catalogue Pokémon local.')
    return carte

class Consultation(BaseModel):
    carte_ref: str = Field(min_length=1, max_length=100)

@app.post('/sessions/{session}/consultations')
def consulter(session: UUID, consultation: Consultation):
    if not collection.fiche(consultation.carte_ref):
        raise HTTPException(404, 'Carte absente du catalogue Pokémon local.')
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
    from pokemon.pertinence import CalibrationAbsente
    texte = requete.texte.strip()
    if len(texte) < 2:
        raise HTTPException(422, 'Saisissez une phrase de recherche.')
    try:
        references = collection.references()
        if not references:
            return {'resultats': []}
        vecteur = encoder([centrer_requete(texte)], requete=True)[0]
        resultats = recherche.rechercher(vecteur, references, identite_modele())
    except (psycopg.Error, ModeleAbsent, CalibrationAbsente, OSError, ImportError) as erreur:
        logging.warning('Recherche indisponible : %s', erreur)
        raise HTTPException(503, 'La recherche par sens est indisponible. Les filtres restent utilisables.') from erreur
    fiches = collection.fiches(x['carte_ref'] for x in resultats)
    return {'resultats': [{**x, 'carte': fiches[x['carte_ref']]} for x in resultats if x['carte_ref'] in fiches]}

@app.get('/images/{identifiant}')
def image(identifiant: str):
    if not re.fullmatch(r'(?:[A-Za-z0-9_!-]|%[0-9A-Fa-f]{2})+', identifiant):
        raise HTTPException(404)
    chemin = IMAGES / (identifiant + '.webp')
    if not chemin.is_file():
        chemin = IMAGES / (identifiant + '.png')
    if not chemin.is_file():
        raise HTTPException(404, 'Illustration non disponible localement.')
    return FileResponse(chemin, media_type='image/png' if chemin.suffix == '.png' else 'image/webp',
                        headers={'Cache-Control': 'public, max-age=86400'})
