"""Nouveau parcours testé dans une base MongoDB jetable, sans toucher la collection locale."""
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from pokemon.dao import CatalogueDAO, CollectionDAO
from pokemon.textes import normaliser


class BlocsTest(unittest.TestCase):
    def test_numero_special_decodage_sans_changer_reference(self):
        carte = normaliser({'id': 'exu-%3F', 'localId': '%3F', 'name': 'Zarbi'})
        self.assertEqual(carte['numero'], '?')
        self.assertEqual(carte['_id'], 'fr:exu-%3F')

    def test_bloc_provient_des_metadonnees_extension(self):
        carte = normaliser({'id': 'test-1', 'name': 'Test', 'set': {
            'id': 'test', 'name': 'Test', 'serie': {'id': 'base', 'name': 'Base'}}})
        self.assertEqual(carte['bloc_id'], 'base')
        self.assertEqual(carte['bloc'], 'Base')


@unittest.skipUnless(os.getenv('POKEMON_INTEGRATION') == '1', 'Bases préparées requises')
class ParcoursTest(unittest.TestCase):
    def setUp(self):
        import api
        self.api = api
        self.nom_base = 'pokemon_test_' + uuid4().hex
        self.base = api.collection.base.client.get_database(self.nom_base,
            write_concern=api.collection.base.write_concern)
        carte = api.collection.base.catalogue.find_one({'_id': 'fr:base1-4'})
        self.assertIsNotNone(carte)
        self.base.catalogue.insert_many([carte,
            normaliser({'id': 'test-sans-texte', 'name': 'Sans texte', 'category': 'Pokémon',
                        'set': {'id': 'test', 'name': 'Autre extension', 'serie': {'id': 'test', 'name': 'Autre bloc'}}}),
            normaliser({'id': 'test-dresseur', 'name': 'Dresseur', 'category': 'Dresseur'})])
        self.collection = CollectionDAO()
        self.collection.base = self.base
        self.catalogue = CatalogueDAO()
        self.catalogue.base = self.base
        self.patches = [patch.object(api, 'collection', self.collection), patch.object(api, 'catalogue', self.catalogue)]
        for p in self.patches:
            p.start()
        self.client = TestClient(api.app)

    def tearDown(self):
        for p in self.patches:
            p.stop()
        # Nom aléatoire créé dans setUp ; ne jamais supprimer la base applicative.
        assert self.nom_base.startswith('pokemon_test_')
        self.base.client.drop_database(self.nom_base)

    def ajouter(self, reference='fr:base1-4', requete_id=None, **infos):
        return self.client.post('/collection/exemplaires', json={
            'references': [reference], 'requete_id': requete_id or str(uuid4()), **infos})

    def test_catalogue_accessible_collection_vide_et_filtres(self):
        self.assertEqual(self.client.get('/catalogue').json()['total'], 2)
        self.assertEqual(self.client.get('/collection').json()['total'], 0)
        self.assertEqual(self.client.get('/statistiques').json()['exemplaires'], 0)
        self.assertEqual(self.client.get('/cartes/fr:base1-4').json()['exemplaires'], [])
        self.assertEqual(self.client.get('/catalogue?bloc=base').json()['total'], 1)
        self.assertEqual(self.client.get('/catalogue?extension=test').json()['total'], 1)
        self.assertEqual(self.client.get('/catalogue?nom=Sans').json()['total'], 1)
        self.assertEqual(self.client.get('/catalogue?type_carte=Feu').json()['total'], 1)
        self.assertEqual(self.client.get('/catalogue?rarete=Rare').json()['total'], 1)
        filtres = self.client.get('/catalogue/filtres?bloc=base').json()
        self.assertEqual([e['id'] for e in filtres['extensions']], ['base1'])
        self.assertEqual(self.client.get('/catalogue/perimetre').json()['cartes'], 2)
        self.assertEqual(self.client.get('/catalogue?taille=1&page=2').json()['cartes'][0]['nom'], 'Sans texte')

    def test_ajouts_quantites_persistance_retrait_et_informations_facultatives(self):
        token = str(uuid4())
        # Les ajouts ne doivent exécuter aucune vectorisation.
        with patch.object(self.api, 'encoder', side_effect=AssertionError('Pas d’indexation à l’ajout')):
            premier = self.ajouter(requete_id=token).json()
            self.assertEqual(premier['ajoutes'], 1)
            self.assertEqual(self.ajouter(requete_id=token).json()['ajoutes'], 0)
            second = self.ajouter().json()
        self.assertEqual(self.base.exemplaires.count_documents({}), 2)
        self.assertEqual(self.client.get('/collection').json()['cartes'][0]['quantite'], 2)
        persistance = CollectionDAO()
        persistance.base = self.base
        self.assertEqual(persistance.statistiques()['exemplaires'], 2)
        stats = self.client.get('/statistiques').json()
        self.assertEqual((stats['depenses'], stats['achats_renseignes']), (0, 0))
        identifiant = premier['exemplaires'][0]
        r = self.client.patch('/collection/exemplaires/' + identifiant,
            json={'etat': 'Excellent', 'variante': 'Holo', 'prix_achat': 12.34})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.base.exemplaires.find_one({'_id': identifiant})['prix_centimes'], 1234)
        self.assertEqual(self.client.get('/statistiques').json()['depenses'], 12.34)
        self.assertEqual(self.client.delete('/collection/exemplaires/' + identifiant).status_code, 200)
        self.assertEqual(self.client.get('/collection').json()['cartes'][0]['quantite'], 1)
        self.assertEqual(self.client.delete('/collection/exemplaires/' + second['exemplaires'][0]).status_code, 200)
        self.assertEqual(self.client.get('/collection').json()['total'], 0)
        self.assertEqual(self.client.get('/catalogue').json()['total'], 2)

    def test_validation_sans_ajout_partiel(self):
        reponse = self.client.post('/collection/exemplaires', json={'references': ['fr:base1-4', 'fr:absente']})
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(self.base.exemplaires.count_documents({}), 0)
        self.assertEqual(self.ajouter('fr:test-dresseur').status_code, 404)
        self.assertEqual(self.ajouter(prix_achat=-1).status_code, 422)
        self.assertEqual(self.client.post('/collection/exemplaires', json={'references': []}).status_code, 422)

    def test_vecteurs_prepares_recherche_limitee_aux_possessions(self):
        with patch.object(self.api, 'encoder', side_effect=AssertionError('Collection vide')):
            self.assertEqual(self.client.post('/recherche', json={'texte': 'incendies'}).json()['resultats'], [])
        premier = self.ajouter().json()['exemplaires'][0]
        self.ajouter('fr:test-sans-texte')
        resultat = self.client.post('/recherche', json={'texte': 'Un Pokémon qui provoque des incendies'})
        self.assertEqual(resultat.status_code, 200, resultat.text)
        self.assertEqual([x['carte_ref'] for x in resultat.json()['resultats']], ['fr:base1-4'])
        self.client.delete('/collection/exemplaires/' + premier)
        self.assertEqual(self.client.post('/recherche', json={'texte': 'incendies'}).json()['resultats'], [])
        self.assertEqual(self.client.get('/collection').json()['cartes'][0]['_id'], 'fr:test-sans-texte')


if __name__ == '__main__':
    unittest.main()
