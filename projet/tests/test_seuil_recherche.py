"""Classement et seuil relatif, vérifiés sur des vecteurs contrôlés."""
import math
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import numpy as np

from pokemon.dao import RechercheDAO

MODELE = 'modele-test-dynamique'


def vecteur(distance):
    return np.array([1-distance, math.sqrt(max(0, 1-(1-distance)**2))] + [0.]*382,
                    dtype=np.float32)


class CollectionVideTest(unittest.TestCase):
    def test_collection_vide_ne_contacte_pas_postgres(self):
        with patch('pokemon.dao.connexion_postgres', side_effect=AssertionError('Connexion inutile')):
            self.assertEqual(RechercheDAO().rechercher([], [], MODELE), [])


@unittest.skipUnless(os.getenv('POKEMON_INTEGRATION') == '1', 'PostgreSQL requis')
class ClassementTest(unittest.TestCase):
    def setUp(self):
        from pokemon.connexions import connexion_postgres
        self.connexion = connexion_postgres()
        self.addCleanup(self.connexion.close)
        # Tables temporaires : aucun index persistant n'est modifié.
        self.connexion.execute('CREATE TEMP TABLE pokemon_passages (carte_ref text, position int, texte text, modele text, embedding vector(384))')
        self.connexion.execute('CREATE TEMP TABLE pokemon_semantique (carte_ref text, texte text, modele text, embedding vector(384))')

        @contextmanager
        def locale():
            yield self.connexion

        patcher = patch('pokemon.dao.connexion_postgres', locale)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dao = RechercheDAO()

    def inserer(self, ref, distance, position=0, ancien=False, modele=MODELE):
        if ancien:
            self.connexion.execute('INSERT INTO pokemon_semantique VALUES (%s,%s,%s,%s)',
                                   (ref, 'texte', modele, vecteur(distance)))
        else:
            self.connexion.execute('INSERT INTO pokemon_passages VALUES (%s,%s,%s,%s,%s)',
                                   (ref, position, 'passage', modele, vecteur(distance)))

    def rechercher(self, refs):
        return self.dao.rechercher(vecteur(0), refs, MODELE)

    def test_top_dix_ordre_doublons_et_propriete(self):
        self.inserer('non-possedee', 0)
        refs = ['carte-' + str(i).zfill(2) for i in range(12)]
        for i, ref in enumerate(refs):
            self.inserer(ref, .05 + i * .003)
        self.inserer(refs[0], .5, position=1)
        resultats = self.rechercher(refs)
        self.assertEqual([r['carte_ref'] for r in resultats], refs[:10])
        self.assertEqual([r['similarite'] for r in resultats],
                         sorted((r['similarite'] for r in resultats), reverse=True))
        self.assertAlmostEqual(resultats[0]['seuil_similarite'], .9025, places=6)
        # Le même classement permet K=1 et tous les résultats admissibles, au-delà de dix.
        self.assertEqual(len(self.dao.rechercher(vecteur(0), refs, MODELE, limite=1)), 1)
        tous = self.dao.rechercher(vecteur(0), refs, MODELE, limite=None)
        self.assertEqual([r['carte_ref'] for r in tous], refs)
        self.assertEqual(resultats, tous[:10])

    def test_seuil_95_pourcent_et_recalcul_selon_les_possessions(self):
        self.inserer('meilleure', .1)  # Similarité .9, minimum .855.
        self.inserer('juste-dedans', .1449)
        self.inserer('juste-dehors', .1451)
        self.inserer('ancien-index', .16, ancien=True)
        refs = ['meilleure', 'juste-dedans', 'juste-dehors', 'ancien-index']
        self.assertEqual([r['carte_ref'] for r in self.rechercher(refs)], refs[:2])
        # Le meilleur score dépend des cartes possédées, pas du catalogue entier.
        resultats = self.rechercher(['juste-dehors', 'ancien-index'])
        self.assertEqual([r['carte_ref'] for r in resultats], ['juste-dehors'])
        self.assertAlmostEqual(resultats[0]['seuil_similarite'], .841, places=6)
        # Même la meilleure candidate doit atteindre le plancher absolu.
        self.assertEqual(self.rechercher(['ancien-index']), [])

    def test_plancher_absolu_et_ancien_index(self):
        self.inserer('meilleure', .15)  # .85 * .95 < .841 : le plancher domine.
        self.inserer('juste-dedans', .1589, ancien=True)
        self.inserer('juste-dehors', .1591)
        resultats = self.rechercher(['meilleure', 'juste-dedans', 'juste-dehors'])
        self.assertEqual([r['carte_ref'] for r in resultats], ['meilleure', 'juste-dedans'])
        self.assertTrue(all(r['seuil_similarite'] == .841 for r in resultats))
        self.assertEqual(self.rechercher(['juste-dehors']), [])

    def test_egalites_departagees_par_reference(self):
        self.inserer('b', .1)
        self.inserer('a', .1)
        self.assertEqual([r['carte_ref'] for r in self.rechercher(['b', 'a'])], ['a', 'b'])

    def test_absence_de_candidat_et_similarites_non_positives(self):
        self.inserer('opposee', 2)
        self.inserer('orthogonale', 1)
        self.inserer('autre-modele', .1, modele='autre')
        self.assertEqual(self.rechercher(['absente']), [])
        self.assertEqual(self.rechercher(['opposee', 'orthogonale', 'autre-modele']), [])

    def test_console_utilise_le_meme_seuil(self):
        self.inserer('proche', .1)
        self.inserer('loin', .5)
        with patch('pokemon.dao.active', return_value=True), patch('pokemon.dao.evenement') as trace:
            resultats = self.rechercher(['proche', 'loin'])
        decisions = next(c.kwargs for c in trace.call_args_list
                         if c.args[:2] == ('pgvector', 'Candidats acceptés / rejetés'))
        self.assertAlmostEqual(decisions['seuil_similarite'], resultats[0]['seuil_similarite'])
        self.assertEqual([c['accepte'] for c in decisions['candidats']], [True, False])
