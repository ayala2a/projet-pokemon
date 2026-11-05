"""Mario : MongoDB ; Dorian : Redis ; Swann : index dérivé PostgreSQL."""
import re

from redis.exceptions import RedisError

from .connexions import base_mongo, client_redis, connexion_postgres


class CollectionDAO:
    def __init__(self):
        self.base = base_mongo()

    def references(self):
        return self.base.exemplaires.distinct('carte_ref')

    def _pipeline(self, nom='', extension='', type_carte='', rarete=''):
        filtre = {}
        if nom:
            filtre['nom'] = {'$regex': re.escape(nom), '$options': 'i'}
        for champ, valeur in [('extension_id', extension), ('types', type_carte), ('rarete', rarete)]:
            if valeur:
                filtre[champ] = valeur
        return [
            {'$group': {'_id': '$carte_ref', 'quantite': {'$sum': 1},
                        'depenses_centimes': {'$sum': '$prix_centimes'}}},
            {'$lookup': {'from': 'catalogue', 'localField': '_id', 'foreignField': '_id', 'as': 'fiche'}},
            {'$unwind': '$fiche'},
            {'$replaceRoot': {'newRoot': {'$mergeObjects': ['$fiche', {
                'quantite': '$quantite', 'depenses_centimes': '$depenses_centimes'}]}}},
            {'$match': filtre},
        ]

    def rechercher(self, nom='', extension='', type_carte='', rarete='', page=1, taille=12):
        pipeline = self._pipeline(nom, extension, type_carte, rarete)
        pipeline.append({'$facet': {
            'cartes': [{'$sort': {'nom': 1, '_id': 1}}, {'$skip': (page - 1) * taille}, {'$limit': taille}],
            'total': [{'$count': 'nombre'}],
        }})
        resultat = next(self.base.exemplaires.aggregate(pipeline))
        return {'cartes': resultat['cartes'], 'total': (resultat['total'] or [{'nombre': 0}])[0]['nombre']}

    def fiches(self, references):
        return {c['_id']: c for c in self.base.catalogue.find({'_id': {'$in': list(references)}})}

    def fiche(self, reference):
        exemplaires = list(self.base.exemplaires.find({'carte_ref': reference}))
        if not exemplaires:
            return None
        carte = self.base.catalogue.find_one({'_id': reference})
        if carte:
            carte['exemplaires'] = exemplaires
        return carte

    def filtres(self):
        cartes = {'_id': {'$in': self.references()}}
        return {
            'extensions': sorted([{'id': x['_id'], 'nom': x['nom']} for x in self.base.catalogue.aggregate([
                {'$match': cartes}, {'$group': {'_id': '$extension_id', 'nom': {'$first': '$extension'}}}
            ])], key=lambda x: x['nom']),
            'types': sorted(self.base.catalogue.distinct('types', cartes)),
            'raretes': sorted(self.base.catalogue.distinct('rarete', cartes)),
        }

    def statistiques(self):
        resultat = list(self.base.exemplaires.aggregate([
            {'$facet': {
                'totaux': [{'$group': {'_id': None, 'exemplaires': {'$sum': 1},
                                     'depenses_centimes': {'$sum': '$prix_centimes'},
                                     'references': {'$addToSet': '$carte_ref'}}}],
                'extensions': [
                    {'$lookup': {'from': 'catalogue', 'localField': 'carte_ref', 'foreignField': '_id', 'as': 'carte'}},
                    {'$unwind': '$carte'},
                    {'$group': {'_id': '$carte.extension', 'exemplaires': {'$sum': 1}}},
                    {'$sort': {'exemplaires': -1, '_id': 1}},
                ],
                'raretes': [
                    {'$lookup': {'from': 'catalogue', 'localField': 'carte_ref', 'foreignField': '_id', 'as': 'carte'}},
                    {'$unwind': '$carte'},
                    {'$group': {'_id': '$carte.rarete', 'exemplaires': {'$sum': 1}}},
                    {'$sort': {'exemplaires': -1, '_id': 1}},
                ],
            }}
        ]))[0]
        total = (resultat['totaux'] or [{}])[0]
        return {'exemplaires': total.get('exemplaires', 0),
                'cartes_distinctes': len(total.get('references', [])),
                'depenses': total.get('depenses_centimes', 0) / 100,
                'extensions': resultat['extensions'], 'raretes': resultat['raretes']}


class HistoriqueDAO:
    def __init__(self, client=None, expiration=1800):
        self.redis = client if client is not None else client_redis()
        self.expiration = expiration

    def enregistrer(self, session, reference):
        try:
            # MULTI/EXEC : ajout, taille et expiration restent cohérents en concurrence.
            with self.redis.pipeline(transaction=True) as pipe:
                cle = 'pokemon:session:' + session + ':consultations'
                pipe.lpush(cle, reference)
                pipe.ltrim(cle, 0, 9)
                pipe.expire(cle, self.expiration)
                pipe.execute()
            return True
        except RedisError:
            return False

    def lire(self, session):
        try:
            return self.redis.lrange('pokemon:session:' + session + ':consultations', 0, 9), True
        except RedisError:
            return [], False


class RechercheDAO:
    def preparer(self):
        with connexion_postgres(vector=False) as connexion:
            connexion.execute('CREATE EXTENSION IF NOT EXISTS vector')
            connexion.execute('''CREATE TABLE IF NOT EXISTS pokemon_semantique (
                carte_ref text PRIMARY KEY, texte text NOT NULL,
                modele text NOT NULL, embedding vector(384) NOT NULL)''')

    def synchroniser(self, lignes):
        with connexion_postgres() as connexion:
            with connexion.transaction():
                connexion.execute('DELETE FROM pokemon_semantique')
                with connexion.cursor() as curseur:
                    curseur.executemany('INSERT INTO pokemon_semantique VALUES (%s,%s,%s,%s)', lignes)

    def rechercher(self, vecteur, references, modele):
        if not references:
            return []
        with connexion_postgres() as connexion:
            # Filtre AVANT LIMIT : uniquement les références possédées actuellement.
            lignes = connexion.execute('''
                SELECT carte_ref, embedding <=> %s AS distance
                FROM pokemon_semantique
                WHERE carte_ref = ANY(%s) AND modele = %s
                ORDER BY embedding <=> %s, carte_ref LIMIT 5
            ''', (vecteur, references, modele, vecteur)).fetchall()
        return [{'carte_ref': ref, 'distance': float(distance)} for ref, distance in lignes]
