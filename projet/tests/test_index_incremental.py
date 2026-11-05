import unittest
from unittest.mock import MagicMock, patch

import importer


def carte(ref, texte):
    return {'_id': ref, 'categorie': 'Pokémon', 'texte': texte}


class IndexIncrementalTest(unittest.TestCase):
    def indexer(self, cartes, avant, apres):
        dao = MagicMock()
        dao.etat_index.side_effect = [avant, apres]
        with patch.object(importer, 'preparer_modele'), \
             patch.object(importer, 'identite_modele', return_value='modele@revision'), \
             patch.object(importer, 'RechercheDAO', return_value=dao), \
             patch.object(importer, 'encoder', return_value=['vecteur-1', 'vecteur-2']) as encodeur, \
             patch('builtins.print'):
            bilan, etat, modele = importer.indexer_cartes(cartes, hors_ligne=True)
        return dao, encodeur, bilan

    def test_ne_calcule_que_les_textes_ou_modeles_modifies_et_les_absents(self):
        cartes = [carte('a', 'inchangé'), carte('b', 'texte changé'), carte('c', 'nouveau')]
        dao, encodeur, bilan = self.indexer(cartes,
            {'a': ('inchangé', 'modele@revision'), 'b': ('ancien texte', 'modele@revision')}, {})
        encodeur.assert_called_once_with(['texte changé', 'nouveau'])
        self.assertEqual(bilan, {'vecteurs_reutilises': 1, 'vecteurs_calcules': 2})
        self.assertEqual([l[0] for l in dao.synchroniser.call_args.args[0]], ['b', 'c'])

    def test_import_repete_reutilise_tous_les_vecteurs(self):
        etat = {'a': ('texte', 'modele@revision')}
        dao, encodeur, bilan = self.indexer([carte('a', 'texte')], etat, etat)
        encodeur.assert_not_called()
        dao.synchroniser.assert_not_called()
        self.assertEqual(bilan['vecteurs_reutilises'], 1)

    def test_nouvelle_revision_et_retrait_texte_inexploitable(self):
        dao, encodeur, bilan = self.indexer([carte('a', 'texte'), carte('b', '')],
                                           {'a': ('texte', 'ancienne-revision')}, {})
        encodeur.assert_called_once_with(['texte'])
        self.assertEqual(dao.synchroniser.call_args.args, ([], ['b']))
        self.assertEqual(bilan['vecteurs_calcules'], 1)


if __name__ == '__main__':
    unittest.main()
