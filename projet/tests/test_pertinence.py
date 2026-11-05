import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pokemon.dao import CollectionDAO


@unittest.skipUnless(os.getenv('POKEMON_INTEGRATION') == '1', 'Passages du catalogue préparés requis')
class PertinenceTest(unittest.TestCase):
    def test_seuil_rejette_les_formulations_trop_eloignees(self):
        import api
        source = api.collection.base
        nom = 'pokemon_test_' + uuid4().hex
        base = source.client.get_database(nom, write_concern=source.write_concern)
        try:
            cartes = list(source.catalogue.find({'_id': {'$in': ['fr:base1-4', 'fr:base1-43']}}))
            self.assertEqual(len(cartes), 2)
            base.catalogue.insert_many(cartes)
            base.exemplaires.insert_many([{'_id': c['_id'], 'carte_ref': c['_id']} for c in cartes])
            dao = CollectionDAO()
            dao.base = base
            with patch.object(api, 'collection', dao), TestClient(api.app) as client:
                for question, reference in [
                    ('fondre la roche avec un souffle brûlant', 'fr:base1-4'),
                    ('sentir le danger grâce à la télépathie', 'fr:base1-43'),
                ]:
                    resultat = client.post('/recherche', json={'texte': question}).json()['resultats']
                    self.assertEqual([x['carte_ref'] for x in resultat], [reference])
                for question in ['comment préparer des pâtes carbonara',
                                 'restaurer les points de vie de mes alliés',
                                 'mes cartes permettant de piocher']:
                    self.assertEqual(client.post('/recherche', json={'texte': question}).json()['resultats'], [])
        finally:
            source.client.drop_database(nom)


if __name__ == '__main__':
    unittest.main()
