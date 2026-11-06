"""Tests métier et intégration sur l'import de démonstration.

POKEMON_INTEGRATION=1 python -m unittest discover -s /projet/tests -v
Les écritures de test utilisent des bases MongoDB jetables et des historiques Redis nettoyés.
"""
import os
import time
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError

from pokemon.dao import HistoriqueDAO
from pokemon.textes import centrer_requete, normaliser, texte_recherche


class TextesTest(unittest.TestCase):
    def test_requete_centre_le_besoin_et_conserve_les_noms(self):
        self.assertEqual(centrer_requete('Un Pokémon qui provoque des incendies'), 'provoque des incendies')
        self.assertEqual(centrer_requete('Pikachu'), 'Pikachu')
        self.assertEqual(centrer_requete('mes cartes permettant de piocher'), 'permettant de piocher')

    def test_nom_seul_exclu(self):
        self.assertEqual(texte_recherche({'name': 'Pikachu', 'types': ['Électrique']}), '')

    def test_effet_sans_description_est_indexable(self):
        texte = texte_recherche({'name': 'Test', 'attacks': [{'name': 'Pioche', 'effect': ' Piochez\n2 cartes. '}]})
        self.assertIn('Piochez 2 cartes.', texte)

    def test_normalisation_champs_manquants(self):
        carte = normaliser({'id': 'test-1', 'name': 'Test'})
        self.assertEqual(carte['_id'], 'fr:test-1')
        self.assertEqual(carte['texte'], '')
        self.assertEqual(carte['types'], [])

    def test_redis_indisponible(self):
        class HorsService:
            def pipeline(self, **kwargs):
                raise ConnectionError('Redis arrêté')
            def lrange(self, *args):
                raise ConnectionError('Redis arrêté')
        dao = HistoriqueDAO(HorsService())
        self.assertFalse(dao.enregistrer('test', 'fr:base1-4'))
        self.assertEqual(dao.lire('test'), ([], False))


@unittest.skipUnless(os.getenv('POKEMON_INTEGRATION') == '1', 'Bases de démonstration requises')
class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api
        from pokemon.dao import CollectionDAO
        cls.api = api
        source = api.collection.base
        cartes = list(source.catalogue.find({'extension_id': {'$in': ['base1', 'base2', 'base3']}}))
        if not cartes:
            raise RuntimeError('Importer le catalogue de démonstration avant les tests d’intégration.')
        nom_base = 'pokemon_test_' + uuid4().hex
        base = source.client.get_database(nom_base, write_concern=source.write_concern)
        cls.addClassCleanup(source.client.drop_database, nom_base)
        base.catalogue.insert_many(cartes)
        base.exemplaires.insert_many([{'_id': 'test-' + c['id'], 'carte_ref': c['_id'], 'prix_centimes': 100}
                                      for c in cartes if c['categorie'] == 'Pokémon'])
        dao = CollectionDAO()
        dao.base = base
        patcher = patch.object(api, 'collection', dao)
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        cls.client = TestClient(api.app)

    def test_agregations_et_filtres(self):
        base = self.api.collection.base
        exemplaires = list(base.exemplaires.find({}))
        stats = self.client.get('/statistiques').json()
        self.assertEqual(stats['exemplaires'], len(exemplaires))
        self.assertEqual(stats['cartes_distinctes'], len({e['carte_ref'] for e in exemplaires}))
        self.assertAlmostEqual(stats['depenses'], sum(e.get('prix_centimes') or 0 for e in exemplaires) / 100)
        self.assertEqual(sum(e['exemplaires'] for e in stats['extensions']), len(exemplaires))
        cartes = self.client.get('/collection', params={'nom': 'Dracaufeu'}).json()
        self.assertGreater(cartes['total'], 0)
        self.assertTrue(all('dracaufeu' in c['nom'].lower() for c in cartes['cartes']))
        filtre = self.client.get('/filtres').json()
        extension = filtre['extensions'][0]['id']
        cartes = self.client.get('/collection', params={'extension': extension}).json()['cartes']
        self.assertTrue(all(c['extension_id'] == extension for c in cartes))
        cartes = self.client.get('/collection', params={'type_carte': 'Feu'}).json()['cartes']
        self.assertTrue(cartes)
        self.assertTrue(all('Feu' in c['types'] for c in cartes))

    def test_validation_et_pagination(self):
        self.assertEqual(self.client.get('/collection?page=0').status_code, 422)
        self.assertEqual(self.client.get('/cartes/fr:inconnue').status_code, 404)
        self.assertEqual(self.client.get('/sessions/pas-un-uuid/consultations').status_code, 422)
        self.assertEqual(self.client.post('/recherche', json={'texte': '  '}).status_code, 422)
        self.assertEqual(self.client.post('/recherche', json={'texte': 'incendies', 'top_k': 0}).status_code, 422)
        a = self.client.get('/collection?page=1').json()['cartes']
        b = self.client.get('/collection?page=2').json()['cartes']
        self.assertFalse({c['_id'] for c in a} & {c['_id'] for c in b})

    def test_historique_cartes_uniques_recence_isolation_expiration(self):
        session = str(uuid4())
        autre = str(uuid4())
        dao = self.api.historique
        cle = 'pokemon:session:' + session + ':consultations'
        try:
            for _ in range(12):
                reponse = self.client.post(f'/sessions/{session}/consultations', json={'carte_ref': 'fr:base1-4'})
                self.assertTrue(reponse.json()['historique_disponible'])
            cartes = self.client.get(f'/sessions/{session}/consultations').json()['cartes']
            self.assertEqual([c['_id'] for c in cartes], ['fr:base1-4'])
            references = ['fr:temoin-' + str(i) for i in range(12)]
            for reference in references:
                dao.enregistrer(session, reference)
            attendus = list(reversed(references))[:10]
            self.assertEqual(dao.lire(session)[0], attendus)
            dao.enregistrer(session, attendus[4])
            self.assertEqual(dao.lire(session)[0], [attendus[4]] + attendus[:4] + attendus[5:])
            self.assertEqual(dao.lire(autre)[0], [])
            self.assertGreater(dao.redis.ttl(cle), 1790)
            dao.redis.expire(cle, 30)
            # Anciennes sessions : ne pas afficher les doublons déjà enregistrés.
            dao.redis.lpush(cle, attendus[4], attendus[4])
            self.assertEqual(dao.lire(session)[0].count(attendus[4]), 1)
            self.assertLessEqual(dao.redis.ttl(cle), 30)
            dao.enregistrer(session, 'fr:base1-4')
            self.assertGreater(dao.redis.ttl(cle), 1790)
            court = HistoriqueDAO(dao.redis, expiration=1)
            court.enregistrer(session, 'fr:base1-4')
            time.sleep(1.2)
            self.assertEqual(court.lire(session)[0], [])
        finally:
            dao.redis.delete(cle)

    def test_api_avec_redis_en_panne(self):
        session = str(uuid4())
        with patch.object(self.api.historique.redis, 'pipeline', side_effect=ConnectionError('panne')):
            self.assertEqual(self.client.get('/collection').status_code, 200)
            reponse = self.client.post(f'/sessions/{session}/consultations', json={'carte_ref': 'fr:base1-4'})
            self.assertEqual(reponse.status_code, 200)
            self.assertFalse(reponse.json()['historique_disponible'])

    def test_recherche_semantique_et_perimetre(self):
        reponse = self.client.post('/recherche', json={'texte': 'Un Pokémon qui provoque des incendies'})
        self.assertEqual(reponse.status_code, 200, reponse.text)
        resultats = reponse.json()['resultats']
        self.assertTrue(1 <= len(resultats) <= 10)
        self.assertIn('fr:base1-4', [x['carte_ref'] for x in resultats])
        distances = [x['distance'] for x in resultats]
        self.assertEqual(distances, sorted(distances))
        self.assertTrue(all(x['similarite'] >= max(.841, .95 * resultats[0]['similarite']) for x in resultats))
        tous = self.client.post('/recherche', json={'texte': 'Un Pokémon qui provoque des incendies',
                                                   'top_k': None}).json()['resultats']
        un = self.client.post('/recherche', json={'texte': 'Un Pokémon qui provoque des incendies',
                                                 'top_k': 1}).json()['resultats']
        self.assertEqual(resultats, tous[:10])
        self.assertEqual(un, tous[:1])
        references = set(self.api.collection.references())
        self.assertTrue(all(x['carte_ref'] in references and x['carte']['texte'] for x in resultats))
        from pokemon.embeddings import encoder, identite_modele
        self.assertEqual(self.api.recherche.rechercher(encoder(['incendie'])[0], ['fr:absente'], identite_modele()), [])


if __name__ == '__main__':
    unittest.main()
