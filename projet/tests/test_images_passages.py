import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import importer
from pokemon.textes import passages_recherche


class ImagesPassagesTest(unittest.TestCase):
    def test_effet_court_indexe_independamment(self):
        carte = {'nom': 'Airmure', 'types': ['Métal'], 'texte': 'texte complet',
                 'attaques': [{'name': 'Meneur', 'effect': 'Piochez une carte.'}],
                 'description': 'Un oiseau.'}
        passages = passages_recherche(carte)
        self.assertIn('Airmure. Meneur : Piochez une carte.', passages)
        self.assertIn('Airmure. Un oiseau.', passages)
        self.assertEqual(passages_recherche({**carte, 'texte': ''}), [])

    def test_image_anglaise_et_provenance_conservees_dans_cache(self):
        with TemporaryDirectory() as dossier, patch.object(importer, 'RACINE', Path(dossier)):
            raw = {'id': 'dp4-53', 'image': None}
            def telecharger(url, fichier):
                fichier.parent.mkdir(parents=True, exist_ok=True)
                fichier.write_bytes(b'image-de-test')
            with patch.object(importer, 'obtenir_json', return_value={'id': raw['id'], 'image': 'https://source/en'}) as api, \
                 patch.object(importer, 'telecharger', side_effect=telecharger):
                resultat = importer.recuperer_illustration(raw)
                self.assertTrue(resultat['image_locale'])
                self.assertEqual(resultat['image_langue'], 'en')
                api.assert_called_once()
            with patch.object(importer, 'obtenir_json', side_effect=AssertionError('Pas de réseau')):
                self.assertEqual(importer.recuperer_illustration(raw, hors_ligne=True), resultat)

    def test_png_local_reutilise_hors_ligne(self):
        with TemporaryDirectory() as dossier, patch.object(importer, 'RACINE', Path(dossier)):
            racine = Path(dossier)
            (racine / 'images').mkdir()
            (racine / 'images/exu-A.png').write_bytes(b'png')
            (racine / 'images_meta').mkdir()
            (racine / 'images_meta/exu-A.json').write_text(json.dumps({'langue': 'en', 'source': 'https://source'}))
            with patch.object(importer, 'obtenir_json', side_effect=AssertionError('Pas de réseau')):
                meta = importer.recuperer_illustration({'id': 'exu-A'}, hors_ligne=True)
                self.assertTrue(meta['image_locale'])
                self.assertEqual(meta['image_langue'], 'en')


if __name__ == '__main__':
    unittest.main()
