"""Mario : MongoDB ; Dorian : Redis ; Swann : index dérivé PostgreSQL."""
import re
from datetime import datetime, timezone
from time import perf_counter

from pymongo import UpdateOne

from redis.exceptions import RedisError

from .connexions import base_mongo, client_redis, connexion_postgres
from .traces import active, evenement, executer_redis, lire_liste_redis, tracer_dao


@tracer_dao
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

    def selection_suppression(self, references):
        exemplaires = list(self.base.exemplaires.find(
            {'carte_ref': {'$in': list(set(references))}}, {'_id': 1, 'carte_ref': 1}).limit(10001))
        return {'identifiants': [e['_id'] for e in exemplaires],
                'cartes': len({e['carte_ref'] for e in exemplaires}),
                'exemplaires': len(exemplaires)}

    def supprimer_exemplaires(self, identifiants):
        # Identifiants précis : les exemplaires ajoutés après la sélection sont conservés.
        return self.base.exemplaires.delete_many({'_id': {'$in': list(set(identifiants))}}).deleted_count

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


@tracer_dao
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


@tracer_dao
class HistoriqueDAO:
    def __init__(self, client=None, expiration=1800):
        self.redis = client if client is not None else client_redis()
        self.expiration = expiration

    def enregistrer(self, session, reference):
        try:
            # MULTI/EXEC : déplacer la carte en tête, limiter et renouveler le TTL atomiquement.
            with self.redis.pipeline(transaction=True) as pipe:
                cle = 'pokemon:session:' + session + ':consultations'
                pipe.lrem(cle, 0, reference)
                pipe.lpush(cle, reference)
                pipe.ltrim(cle, 0, 9)
                pipe.expire(cle, self.expiration)
                if active():
                    pipe.llen(cle)
                    pipe.ttl(cle)
                    pipe.lrange(cle, 0, 9)
                resultat = executer_redis(pipe, cle)
                if active():
                    evenement('Redis', 'État après consultation', cle=cle, longueur=resultat[-3],
                              ttl_secondes=resultat[-2], contenu_liste=resultat[-1])
            return True
        except RedisError:
            return False

    def lire(self, session):
        try:
            cle = 'pokemon:session:' + session + ':consultations'
            references = lire_liste_redis(self.redis, cle)
            if active():
                # Observations en lecture seule : aucune prolongation de l'historique.
                try:
                    with self.redis.pipeline(transaction=False) as pipe:
                        pipe.llen(cle)
                        pipe.ttl(cle)
                        longueur, ttl = executer_redis(pipe, cle)
                    evenement('Redis', 'État de la liste', cle=cle, longueur=longueur, ttl_secondes=ttl)
                except Exception as erreur:
                    evenement('Redis', 'Diagnostic indisponible', cle=cle, erreur=type(erreur).__name__, message=str(erreur))
            # Les sessions antérieures peuvent encore contenir des doublons.
            # Préserver la consultation la plus récente, sans prolonger le TTL à la lecture.
            return list(dict.fromkeys(references)), True
        except RedisError as erreur:
            evenement('Redis', 'Indisponible', erreur=type(erreur).__name__, message=str(erreur))
            return [], False


@tracer_dao
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

    def rechercher(self, vecteur, references, modele, limite=10):
        if not references:
            return []
        evenement('pgvector', 'Paramètres de recherche', modele=modele, dimension=len(vecteur),
                  vecteur=vecteur, ratio_similarite=0.95, seuil_absolu=0.841,
                  limite=limite, references_possedees=references)
        with connexion_postgres() as connexion:
            # Filtre AVANT LIMIT : uniquement les références possédées actuellement.
            candidats_sql = '''
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
                    ORDER BY carte_ref, distance, texte
                ), scores AS (
                    SELECT carte_ref, texte, distance, 1 - distance AS similarite,
                           greatest(0.841, 0.95 * max(1 - distance) OVER ()) AS seuil_similarite
                    FROM meilleurs
                ) '''
            parametres = (vecteur, references, modele, vecteur, references, modele)
            lignes = connexion.execute(candidats_sql + '''
                  SELECT carte_ref, texte, distance, similarite, seuil_similarite FROM scores
                  WHERE similarite > 0 AND similarite >= seuil_similarite
                  ORDER BY distance, carte_ref LIMIT %s
            ''', (*parametres, limite)).fetchall()
            if active():
                try:
                    # Diagnostic réel en lecture seule ; ne remplace pas la sélection métier.
                    diagnostic_debut = perf_counter()
                    candidats = connexion.execute(candidats_sql + '''
                        SELECT carte_ref, texte, distance, similarite, seuil_similarite
                        FROM scores ORDER BY distance, carte_ref''', parametres).fetchall()
                    retenus = {ligne[0] for ligne in lignes}
                    decisions = [{'carte_ref': ref, 'passage_compare': texte, 'distance': float(distance),
                                  'similarite': float(similarite),
                                  'accepte': ref in retenus,
                                  'raison': 'retenu' if ref in retenus else
                                  ('similarité non positive' if similarite <= 0 else
                                   'similarité inférieure au seuil absolu de 0,841' if similarite < 0.841 else
                                   'similarité inférieure à 95 % du meilleur score' if similarite < seuil
                                   else f'limite de {limite} résultats')}
                                 for ref, texte, distance, similarite, seuil in candidats]
                    evenement('pgvector', 'Candidats acceptés / rejetés',
                              seuil_similarite=float(candidats[0][4]) if candidats else None,
                              duree_ms=round((perf_counter() - diagnostic_debut) * 1000, 2),
                              modele=modele, dimension=len(vecteur), references_possedees=references,
                              diagnostic_lecture_seule=True, candidats=decisions,
                              total=len(candidats), acceptes=len(retenus), rejetes=len(candidats)-len(retenus))
                except Exception as erreur:
                    evenement('pgvector', 'Diagnostic indisponible', erreur=type(erreur).__name__, message=str(erreur))
        return [{'carte_ref': ref, 'passage': texte, 'distance': float(distance),
                 'similarite': float(similarite), 'seuil_similarite': float(seuil)}
                for ref, texte, distance, similarite, seuil in lignes]
