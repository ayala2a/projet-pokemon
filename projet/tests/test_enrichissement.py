"""Filtres et parcours d'une carte d'un nouveau bloc, après import enrichi."""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pokemon.dao import CollectionDAO
from pokemon.connexions import connexion_postgres


@unittest.skipUnless(os.getenv('POKEMON_INTEGRATION') == '1', 'Catalogue enrichi requis')
class EnrichissementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import api
        cls.api = api
        cls.source = api.collection.base
        cls.client = TestClient(api.app)
        for bloc in ['base', 'ex', 'dp', 'pl', 'hgss']:
            if not cls.source.catalogue.find_one({'bloc_id': bloc}):
                raise unittest.SkipTest('Importer les quatre blocs avant ce test enrichi.')

    def test_filtres_blocs_extensions_et_pagination(self):
        for bloc in ['base', 'ex', 'dp', 'pl', 'hgss']:
            with self.subTest(bloc=bloc):
                reponse = self.client.get('/catalogue', params={'bloc': bloc, 'taille': 12})
                self.assertEqual(reponse.status_code, 200)
                resultat = reponse.json()
                self.assertGreater(resultat['total'], 0)
                self.assertTrue(all(c['bloc_id'] == bloc for c in resultat['cartes']))
                filtres = self.client.get('/catalogue/filtres', params={'bloc': bloc}).json()
                for extension in filtres['extensions']:
                    cartes = self.client.get('/catalogue', params={'bloc': bloc, 'extension': extension['id']}).json()['cartes']
                    self.assertTrue(cartes)
                    self.assertTrue(all(c['extension_id'] == extension['id'] for c in cartes))
                page2 = self.client.get('/catalogue', params={'bloc': bloc, 'page': 2}).json()['cartes']
                self.assertFalse({c['_id'] for c in resultat['cartes']} & {c['_id'] for c in page2})

    def test_ajout_nouveau_bloc_utilise_son_vecteur_existant(self):
        carte = self.source.catalogue.find_one({'bloc_id': 'ex', 'categorie': 'Pokémon', 'texte': {'$ne': ''}})
        with connexion_postgres() as c:
            avant = c.execute('SELECT texte, modele, embedding::text FROM pokemon_semantique WHERE carte_ref=%s',
                              (carte['_id'],)).fetchone()
        self.assertIsNotNone(avant)
        nom = 'pokemon_test_' + uuid4().hex
        base = self.source.client.get_database(nom, write_concern=self.source.write_concern)
        try:
            base.catalogue.insert_one(carte.copy())
            dao = CollectionDAO()
            dao.base = base
            with patch.object(self.api, 'collection', dao):
                with patch.object(self.api, 'encoder', side_effect=AssertionError('Aucun embedding à l’ajout')):
                    ajout = self.client.post('/collection/exemplaires', json={'references': [carte['_id']]})
                    self.assertEqual(ajout.json()['ajoutes'], 1)
                self.assertEqual(self.client.get('/statistiques').json()['cartes_distinctes'], 1)
                resultat = self.client.post('/recherche', json={'texte': (carte.get('description') or carte['nom'])[:200]}).json()
                self.assertEqual([x['carte_ref'] for x in resultat['resultats']], [carte['_id']])
            with connexion_postgres() as c:
                apres = c.execute('SELECT texte, modele, embedding::text FROM pokemon_semantique WHERE carte_ref=%s',
                                  (carte['_id'],)).fetchone()
            self.assertEqual(avant, apres)
        finally:
            self.source.client.drop_database(nom)


if __name__ == '__main__':
    unittest.main()
