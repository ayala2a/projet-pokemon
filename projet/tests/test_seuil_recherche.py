import math
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import numpy as np

from pokemon.dao import RechercheDAO
from pokemon.pertinence import CalibrationAbsente, seuil_distance

MODELE = 'Xenova/multilingual-e5-small@761b726dd34fb83930e26aab4e9ac3899aa1fa78'


class CalibrationTest(unittest.TestCase):
    def test_changement_modele_exige_recalibration(self):
        with self.assertRaises(CalibrationAbsente):
            seuil_distance('autre-modele')

    def test_collection_vide_ne_contacte_pas_postgres(self):
        with patch('pokemon.dao.connexion_postgres', side_effect=AssertionError('Connexion inutile')):
            self.assertEqual(RechercheDAO().rechercher([], [], MODELE), [])


@unittest.skipUnless(os.getenv('POKEMON_INTEGRATION') == '1', 'PostgreSQL requis')
class ClassementTest(unittest.TestCase):
    def test_filtre_propriete_seuil_doublons_et_limite(self):
        from pokemon.connexions import connexion_postgres
        # Tables TEMP de cette connexion : aucun index persistant n'est modifié.
        with connexion_postgres() as connexion:
            connexion.execute('CREATE TEMP TABLE pokemon_passages (carte_ref text, position int, texte text, modele text, embedding vector(384))')
            connexion.execute('CREATE TEMP TABLE pokemon_semantique (carte_ref text, texte text, modele text, embedding vector(384))')
            def vecteur(distance):
                return np.array([1-distance, math.sqrt(1-(1-distance)**2)] + [0.]*382, dtype=np.float32)
            seuil = seuil_distance(MODELE)
            lignes = [('non-possedee', 0, 'excellent mais absent', MODELE, vecteur(0.))]
            lignes += [('carte-' + str(i), 0, 'passage', MODELE, vecteur(seuil * (i+1)/10)) for i in range(6)]
            lignes += [('lointaine', 0, 'éloigné', MODELE, vecteur(seuil + .001)),
                       ('carte-0', 1, 'doublon', MODELE, vecteur(seuil/9))]
            with connexion.cursor() as curseur:
                curseur.executemany('INSERT INTO pokemon_passages VALUES (%s,%s,%s,%s,%s)', lignes)
            # Carte avec uniquement l'ancien index : le seuil doit aussi s'appliquer.
            connexion.execute('INSERT INTO pokemon_semantique VALUES (%s,%s,%s,%s)',
                               ('ancien-index', 'texte', MODELE, vecteur(.9)))
            @contextmanager
            def locale():
                yield connexion
            with patch('pokemon.dao.connexion_postgres', locale):
                dao = RechercheDAO()
                possedees = ['carte-' + str(i) for i in range(6)] + ['lointaine', 'ancien-index']
                resultats = dao.rechercher(vecteur(0), possedees, MODELE)
                self.assertEqual([r['carte_ref'] for r in resultats], ['carte-' + str(i) for i in range(5)])
                self.assertEqual(len(dao.rechercher(vecteur(0), ['carte-0', 'lointaine'], MODELE)), 1)
                self.assertEqual(dao.rechercher(vecteur(0), ['lointaine', 'ancien-index'], MODELE), [])
                self.assertEqual([r['carte_ref'] for r in dao.rechercher(vecteur(0), ['carte-5'], MODELE)], ['carte-5'])
