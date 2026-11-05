"""Une relance de l'import ne doit jamais remettre la collection à zéro."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import importer


class ImportTest(unittest.TestCase):
    def test_import_cumulatif_et_collection_existante_preservee(self):
        for choix, nombre in [(['--extensions', 'test'], 7), (['--blocs', 'bloc-test'], 0)]:
            with self.subTest(choix=choix, exemplaires=nombre), TemporaryDirectory() as dossier:
                base = MagicMock()
                base.exemplaires.count_documents.return_value = nombre
                base.exemplaires.distinct.return_value = ['fr:autre-1'] if nombre else []

                def donnees(url, *args):
                    if url.endswith('/cards'):
                        return [{'id': 'test-1'}]
                    if url.endswith('/sets'):
                        return [{'id': 'test', 'name': 'Test'}]
                    if '/series/' in url:
                        return {'id': 'bloc-test', 'sets': [{'id': 'test'}]}
                    if '/sets/' in url:
                        return {'id': 'test', 'name': 'Test', 'serie': {'id': 'bloc-test', 'name': 'Bloc test'}}
                    return {'id': 'test-1', 'name': 'Test', 'category': 'Pokémon',
                            'description': 'Description', 'set': {'id': 'test', 'name': 'Test'}}

                with patch.object(importer, 'obtenir_json', side_effect=donnees), \
                     patch.object(importer, 'base_mongo', return_value=base), \
                     patch.object(importer, 'RACINE', Path(dossier)), \
                     patch('sys.argv', ['importer', *choix, '--limite', '1',
                                        '--hors-ligne', '--sans-vecteurs']), patch('builtins.print'):
                    importer.main()
                base.catalogue.bulk_write.assert_called_once()
                base.catalogue.delete_many.assert_not_called()
                base.exemplaires.bulk_write.assert_not_called()
                base.exemplaires.insert_many.assert_not_called()
                base.exemplaires.insert_one.assert_not_called()
                base.exemplaires.update_one.assert_not_called()
                base.exemplaires.delete_many.assert_not_called()
                bilan = json.loads((Path(dossier) / 'bilan_import.json').read_text())
                self.assertEqual(bilan['exemplaires'], nombre)
                self.assertEqual(bilan['blocs_importes'], ['Bloc test'])


if __name__ == '__main__':
    unittest.main()
