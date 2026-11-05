"""E5 multilingue 384D, inférence ONNX locale (aucun appel réseau à l'usage)."""
import json
import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np

MODELE = 'Xenova/multilingual-e5-small'
DOSSIER_MODELE = Path(os.getenv('POKEMON_MODEL_DIR', '/travail/pokemon/modele-e5'))


class ModeleAbsent(RuntimeError):
    pass


@lru_cache
def charger():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    if not (DOSSIER_MODELE / 'model.onnx').exists():
        raise ModeleAbsent('Préparez le modèle avec importer.py avant la recherche.')
    meta = json.loads((DOSSIER_MODELE / 'manifest.json').read_text(encoding='utf-8'))
    if meta['modele'] != MODELE:
        raise ModeleAbsent('Le modèle local ne correspond pas au modèle attendu.')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(DOSSIER_MODELE / 'model.onnx'), options,
                                  providers=['CPUExecutionProvider'])
    tokenizer = Tokenizer.from_file(str(DOSSIER_MODELE / 'tokenizer.json'))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return session, tokenizer, MODELE + '@' + meta['revision'], Lock()


def identite_modele():
    return charger()[2]


def encoder(textes, requete=False):
    session, tokenizer, _, verrou = charger()
    vecteurs = []
    # Le modèle accepte 512 tokens. Les textes longs sont découpés,
    # puis leurs représentations sont moyennées au lieu de perdre les derniers effets.
    with verrou:
        for texte in textes:
            prefixe = 'query: ' if requete else 'passage: '
            ids = tokenizer.encode(prefixe + texte, add_special_tokens=False).ids
            cls = tokenizer.token_to_id('<s>')
            sep = tokenizer.token_to_id('</s>')
            pad = tokenizer.token_to_id('<pad>')
            morceaux = [[cls] + ids[i:i + 510] + [sep] for i in range(0, max(1, len(ids)), 510)]
            representations = []
            for debut in range(0, len(morceaux), 8):
                lot = morceaux[debut:debut + 8]
                taille = max(map(len, lot))
                entree = np.array([x + [pad] * (taille - len(x)) for x in lot], dtype=np.int64)
                masque = np.array([[1] * len(x) + [0] * (taille - len(x)) for x in lot], dtype=np.int64)
                valeurs = {'input_ids': entree, 'attention_mask': masque,
                           'token_type_ids': np.zeros_like(entree)}
                sortie = session.run(None, {x.name: valeurs[x.name] for x in session.get_inputs()})[0]
                moyenne = (sortie * masque[..., None]).sum(axis=1) / masque.sum(axis=1)[:, None]
                representations.extend(moyenne)
            vecteur = np.mean(representations, axis=0)
            vecteurs.append((vecteur / max(np.linalg.norm(vecteur), 1e-12)).astype(np.float32))
    return np.array(vecteurs)
