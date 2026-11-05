"""Mario : MongoDB ; Dorian : Redis ; Swann : index dérivé PostgreSQL."""
import re
from datetime import datetime, timezone

from pymongo import UpdateOne

from redis.exceptions import RedisError

from .connexions import base_mongo, client_redis, connexion_postgres


class CollectionDAO:
    def __init__(self):
        self.base = base_mongo()

    def references(self):
        return self.base.exemplaires.distinct('carte_ref')

    def _filtre(self, nom='', extension='', type_carte='', rarete='', bloc=''):
        filtre = {'categorie': 'Pokémon'}
        if nom:
            filtre['nom'] = {'$regex': re.escape(nom), '$options': 'i'}
        for champ, valeur in [('extension_id', extension), ('types', type_carte), ('rarete', rarete), ('bloc_id', bloc)]:
            if valeur:
                filtre[champ] = valeur
        return filtre

    def _pipeline(self, nom='', extension='', type_carte='', rarete='', bloc=''):
        return [
            {'$group': {'_id': '$carte_ref', 'quantite': {'$sum': 1},
                        'depenses_centimes': {'$sum': '$prix_centimes'}}},
            {'$lookup': {'from': 'catalogue', 'localField': '_id', 'foreignField': '_id', 'as': 'fiche'}},
            {'$unwind': '$fiche'},
            {'$replaceRoot': {'newRoot': {'$mergeObjects': ['$fiche', {
                'quantite': '$quantite', 'depenses_centimes': '$depenses_centimes'}]}}},
            {'$match': self._filtre(nom, extension, type_carte, rarete, bloc)},
        ]

    def rechercher(self, nom='', extension='', type_carte='', rarete='', page=1, taille=12, bloc=''):
        pipeline = self._pipeline(nom, extension, type_carte, rarete, bloc)
        pipeline.append({'$facet': {
            'cartes': [{'$sort': {'nom': 1, '_id': 1}}, {'$skip': (page - 1) * taille}, {'$limit': taille}],
            'total': [{'$count': 'nombre'}],
        }})
        resultat = next(self._source().aggregate(pipeline))
        return {'cartes': resultat['cartes'], 'total': (resultat['total'] or [{'nombre': 0}])[0]['nombre']}

    def _source(self):
        return self.base.exemplaires

    def fiches(self, references):
        return {c['_id']: c for c in self.base.catalogue.find({'_id': {'$in': list(references)}})}

    def fiche(self, reference):
        exemplaires = list(self.base.exemplaires.find({'carte_ref': reference}))
        carte = self.base.catalogue.find_one({'_id': reference, 'categorie': 'Pokémon'})
        if carte:
            carte['exemplaires'] = exemplaires
        return carte

    def filtres(self, bloc=''):
        cartes = self._filtre(bloc=bloc)
        if not isinstance(self, CatalogueDAO):
            cartes['_id'] = {'$in': self.references()}
        return {
            'blocs': sorted([{'id': x['_id'], 'nom': x['nom']} for x in self.base.catalogue.aggregate([
                {'$match': {**cartes, **({'bloc_id': {'$exists': True}} if not bloc else {})}},
                {'$group': {'_id': '$bloc_id', 'nom': {'$first': '$bloc'}}}
            ])], key=lambda x: x['nom']),
            'extensions': sorted([{'id': x['_id'], 'nom': x['nom']} for x in self.base.catalogue.aggregate([
                {'$match': cartes}, {'$group': {'_id': '$extension_id', 'nom': {'$first': '$extension'},
                                               'bloc_id': {'$first': '$bloc_id'}}}
            ])], key=lambda x: x['nom']),
            'types': sorted(self.base.catalogue.distinct('types', cartes)),
            'raretes': sorted(self.base.catalogue.distinct('rarete', cartes)),
        }

    def ajouter(self, references, requete_id, informations):
        references_connues = self.base.catalogue.count_documents({
            '_id': {'$in': list(set(references))}, 'categorie': 'Pokémon'})
        if references_connues != len(set(references)):
            raise ValueError('Une carte sélectionnée est absente du catalogue Pokémon local.')
        documents = [{'_id': f'ajout-{requete_id}-{i}', 'carte_ref': reference,
                      'ajoute_le': datetime.now(timezone.utc).isoformat(), **informations}
                     for i, reference in enumerate(references)]
        resultat = self.base.exemplaires.bulk_write([
            UpdateOne({'_id': d['_id']}, {'$setOnInsert': d}, upsert=True) for d in documents])
        return {'ajoutes': resultat.upserted_count, 'exemplaires': [d['_id'] for d in documents]}

    def retirer(self, identifiant):
        return self.base.exemplaires.delete_one({'_id': identifiant}).deleted_count == 1

    def modifier(self, identifiant, informations):
        return self.base.exemplaires.update_one({'_id': identifiant}, {'$set': informations}).matched_count == 1

    def statistiques(self):
        resultat = list(self.base.exemplaires.aggregate([
            {'$facet': {
                'totaux': [{'$group': {'_id': None, 'exemplaires': {'$sum': 1},
                                     'depenses_centimes': {'$sum': '$prix_centimes'},
                                     'achats_renseignes': {'$sum': {'$cond': [{'$isNumber': '$prix_centimes'}, 1, 0]}},
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
                'achats_renseignes': total.get('achats_renseignes', 0),
                'extensions': resultat['extensions'], 'raretes': resultat['raretes']}


class CatalogueDAO(CollectionDAO):
    def _source(self):
        return self.base.catalogue

    def _pipeline(self, nom='', extension='', type_carte='', rarete='', bloc=''):
        return [
            {'$match': self._filtre(nom, extension, type_carte, rarete, bloc)},
            {'$lookup': {'from': 'exemplaires', 'localField': '_id', 'foreignField': 'carte_ref', 'as': 'possessions'}},
            {'$set': {'quantite': {'$size': '$possessions'}}},
            {'$unset': 'possessions'},
        ]

    def perimetre(self):
        extensions = list(self.base.catalogue.aggregate([
            {'$match': {'categorie': 'Pokémon'}},
            {'$group': {'_id': '$extension_id', 'extension': {'$first': '$extension'},
                        'bloc': {'$first': '$bloc'}, 'bloc_id': {'$first': '$bloc_id'}, 'cartes': {'$sum': 1},
                        'images_manquantes': {'$sum': {'$cond': [{'$ifNull': ['$image_locale', False]}, 0, 1]}},
                        'images_anglaises': {'$sum': {'$cond': [{'$eq': ['$image_langue', 'en']}, 1, 0]}},
                        'textes_exploitables': {'$sum': {'$cond': [
                            {'$ne': [{'$ifNull': ['$texte', '']}, '']}, 1, 0]}}}},
            {'$sort': {'bloc': 1, 'extension': 1}},
        ]))
        return {'cartes': sum(e['cartes'] for e in extensions), 'extensions': extensions,
                'images_manquantes': sum(e['images_manquantes'] for e in extensions),
                'images_anglaises': sum(e['images_anglaises'] for e in extensions),
                'textes_exploitables': sum(e['textes_exploitables'] for e in extensions),
                'blocs': sorted({e.get('bloc') or 'Non renseigné' for e in extensions})}


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
    def etat_index(self, references=None):
        with connexion_postgres() as connexion:
            if references is not None:
                lignes = connexion.execute('SELECT carte_ref, texte, modele FROM pokemon_semantique WHERE carte_ref = ANY(%s)',
                                            (list(references),)).fetchall()
            else:
                lignes = connexion.execute('SELECT carte_ref, texte, modele FROM pokemon_semantique').fetchall()
        return {ref: (texte, modele) for ref, texte, modele in lignes}

    def preparer(self):
        with connexion_postgres(vector=False) as connexion:
            connexion.execute('CREATE EXTENSION IF NOT EXISTS vector')
            connexion.execute('''CREATE TABLE IF NOT EXISTS pokemon_semantique (
                carte_ref text PRIMARY KEY, texte text NOT NULL,
                modele text NOT NULL, embedding vector(384) NOT NULL)''')
            connexion.execute('''CREATE TABLE IF NOT EXISTS pokemon_passages (
                carte_ref text NOT NULL, position integer NOT NULL, texte text NOT NULL,
                modele text NOT NULL, embedding vector(384) NOT NULL,
                PRIMARY KEY (carte_ref, position))''')

    def etat_passages(self):
        with connexion_postgres() as connexion:
            lignes = connexion.execute('''SELECT carte_ref, array_agg(texte ORDER BY position),
                min(modele), count(DISTINCT modele) FROM pokemon_passages GROUP BY carte_ref''').fetchall()
        return {ref: (textes, modele) for ref, textes, modele, n in lignes if n == 1}

    def synchroniser_passages(self, documents):
        with connexion_postgres() as connexion:
            with connexion.transaction():
                connexion.execute('DELETE FROM pokemon_passages WHERE carte_ref=ANY(%s)',
                                  ([ref for ref, _ in documents],))
                lignes = [(ref, i, texte, modele, vecteur) for ref, passages in documents
                          for i, (texte, modele, vecteur) in enumerate(passages)]
                with connexion.cursor() as curseur:
                    curseur.executemany('INSERT INTO pokemon_passages VALUES (%s,%s,%s,%s,%s)', lignes)

    def synchroniser(self, lignes, exclure=()):
        with connexion_postgres() as connexion:
            with connexion.transaction():
                if exclure:
                    connexion.execute('DELETE FROM pokemon_semantique WHERE carte_ref = ANY(%s)', (list(exclure),))
                with connexion.cursor() as curseur:
                    curseur.executemany('''INSERT INTO pokemon_semantique VALUES (%s,%s,%s,%s)
                        ON CONFLICT (carte_ref) DO UPDATE SET texte=EXCLUDED.texte,
                        modele=EXCLUDED.modele, embedding=EXCLUDED.embedding''', lignes)

    def rechercher(self, vecteur, references, modele):
        if not references:
            return []
        from pokemon.pertinence import seuil_distance
        seuil = seuil_distance(modele)
        with connexion_postgres() as connexion:
            # Filtre AVANT LIMIT : uniquement les références possédées actuellement.
            lignes = connexion.execute('''
                WITH candidats AS (
                    SELECT carte_ref, texte, embedding <=> %s AS distance
                    FROM pokemon_passages WHERE carte_ref=ANY(%s) AND modele=%s
                    UNION ALL
                    SELECT s.carte_ref, s.texte, s.embedding <=> %s AS distance
                    FROM pokemon_semantique s WHERE s.carte_ref=ANY(%s) AND s.modele=%s
                    AND NOT EXISTS (SELECT 1 FROM pokemon_passages p
                                    WHERE p.carte_ref=s.carte_ref AND p.modele=s.modele)
                ), meilleurs AS (
                    SELECT DISTINCT ON (carte_ref) carte_ref, texte, distance FROM candidats
                    ORDER BY carte_ref, distance
                ) SELECT carte_ref, texte, distance FROM meilleurs
                  WHERE distance <= %s ORDER BY distance, carte_ref LIMIT 5
            ''', (vecteur, references, modele, vecteur, references, modele, seuil)).fetchall()
        return [{'carte_ref': ref, 'passage': texte, 'distance': float(distance)} for ref, texte, distance in lignes]
