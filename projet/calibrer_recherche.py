"""Calibration explicite, en lecture seule, sur les vecteurs locaux existants.

Exécuter depuis /projet : python calibrer_recherche.py.
Les formulations de validation ne participent pas au choix du seuil.
"""
import json
from pathlib import Path

from pokemon.connexions import connexion_postgres
from pokemon.embeddings import encoder, identite_modele
from pokemon.textes import centrer_requete

REFERENCES = ['fr:ex8-26', 'fr:base3-46', 'fr:base1-4', 'fr:base1-43',
              'fr:base1-58', 'fr:base1-63']
# Vérité terrain établie à partir des descriptions et effets français de ces fiches.
JEUX = {
    'calibration': [
        ('piocher des cartes', ['fr:ex8-26']),
        ('attaque qui empoisonne', ['fr:base3-46']),
        ('un Pokémon qui provoque des incendies', ['fr:base1-4']),
        ('se téléporter pour échapper au danger', ['fr:base1-43']),
        ('provoquer des orages', ['fr:base1-58']),
        ('éviter les dégâts au prochain tour', ['fr:base1-63']),
        ('un Pokémon de type eau', ['fr:base1-63']),
        ('soigner les blessures de mon Pokémon', []),
        ('endormir le Pokémon adverse', []),
        ('récupérer un Pokémon depuis la défausse', []),
        ('une recette de gâteau au chocolat', []),
        ('réserver un billet de train', []),
    ],
    'validation': [
        ('mes cartes permettant de piocher', ['fr:ex8-26']),
        ('rendre le défenseur empoisonné', ['fr:base3-46']),
        ('fondre la roche avec un souffle brûlant', ['fr:base1-4']),
        ('sentir le danger grâce à la télépathie', ['fr:base1-43']),
        ('des Pokémon réunis déclenchent un orage', ['fr:base1-58']),
        ('prévenir tous les dégâts infligés', ['fr:base1-63']),
        ('je cherche un Pokémon aquatique', ['fr:base1-63']),
        ('restaurer les points de vie de mes alliés', []),
        ('plonger mon adversaire dans le sommeil', []),
        ('ressusciter une créature défaussée', []),
        ('comment préparer des pâtes carbonara', []),
        ('la météo de demain à Paris', []),
    ],
}


def statistiques(lignes, seuil):
    vp = sum(x['pertinent'] and x['distance'] <= seuil for x in lignes)
    fp = sum(not x['pertinent'] and x['distance'] <= seuil for x in lignes)
    fn = sum(x['pertinent'] and x['distance'] > seuil for x in lignes)
    return {'vrais_positifs': vp, 'faux_positifs': fp, 'faux_negatifs': fn,
            'precision': vp / (vp + fp) if vp + fp else 1.,
            'rappel': vp / (vp + fn) if vp + fn else 1.}


def main():
    modele = identite_modele()
    mesures = {}
    with connexion_postgres() as connexion:
        for jeu, exemples in JEUX.items():
            lignes = []
            for question, attendus in exemples:
                # Même inférence unitaire que l'API (quantification ONNX sensible au padding).
                vecteur = encoder([centrer_requete(question)], requete=True)[0]
                distances = connexion.execute('''SELECT carte_ref, min(embedding <=> %s)
                    FROM pokemon_passages WHERE carte_ref=ANY(%s) AND modele=%s
                    GROUP BY carte_ref''', (vecteur, REFERENCES, modele)).fetchall()
                if len(distances) != len(REFERENCES):
                    raise RuntimeError('Importer les six cartes témoins et leurs passages avant calibration.')
                lignes.extend({'question': question, 'carte_ref': ref, 'distance': float(distance),
                               'pertinent': ref in attendus} for ref, distance in distances)
            mesures[jeu] = lignes
    # F0.5 privilégie la précision (poids quatre fois supérieur au rappel).
    # En cas d'égalité, choisir le seuil le plus strict.
    distances = sorted({x['distance'] for x in mesures['calibration']})
    candidats = [distances[0] / 2] + [(a + b) / 2 for a, b in zip(distances, distances[1:])]
    def score(seuil):
        s = statistiques(mesures['calibration'], seuil)
        p, r = s['precision'], s['rappel']
        return 1.25 * p * r / (.25 * p + r) if r else 0
    seuil = max(candidats, key=lambda s: (score(s), -s))
    rapport = {'modele': modele, 'seuil_distance': seuil, 'references': REFERENCES,
               'methode': 'F0.5 maximal sur calibration ; égalité départagée par le seuil le plus strict.',
               'statistiques': {jeu: statistiques(lignes, seuil) for jeu, lignes in mesures.items()},
               'mesures': mesures}
    chemin = Path('/travail/pokemon/calibration_recherche.json')
    chemin.write_text(json.dumps(rapport, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in rapport.items() if k != 'mesures'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
