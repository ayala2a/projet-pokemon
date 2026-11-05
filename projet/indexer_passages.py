"""Préparation locale des passages ; aucun calcul lors d'un ajout à la collection."""
from pokemon.connexions import base_mongo
from pokemon.dao import RechercheDAO
from pokemon.embeddings import encoder, identite_modele
from pokemon.textes import passages_recherche


def indexer(cartes):
    dao = RechercheDAO()
    dao.preparer()
    modele = identite_modele()
    etat = dao.etat_passages()
    a_faire = [(c['_id'], passages_recherche(c)) for c in cartes]
    a_faire = [(ref, p) for ref, p in a_faire if p and etat.get(ref) != (p, modele)]
    print('Cartes dont les passages sont à préparer :', len(a_faire), flush=True)
    for debut in range(0, len(a_faire), 30):
        lot = a_faire[debut:debut + 30]
        textes = [texte for _, passages in lot for texte in passages]
        vecteurs = iter(encoder(textes))
        documents = [(ref, [(texte, modele, next(vecteurs)) for texte in passages]) for ref, passages in lot]
        dao.synchroniser_passages(documents)
        print(f'Passages : {min(debut + 30, len(a_faire))}/{len(a_faire)} cartes sauvegardées.', flush=True)


if __name__ == '__main__':
    indexer(list(base_mongo().catalogue.find({'categorie': 'Pokémon', 'texte': {'$ne': ''}})))
