"""Parcours Streamlit : catalogue, filtres, ajout, retrait, recherche et historique.
Les exemplaires ajoutés par ce test sont retirés à la fin, même en cas d’échec.
"""
import requests
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pokemon.connexions import client_redis

API = 'http://localhost:8000'


def verifier(at):
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def bouton(at, label=None, key=None):
    return next(b for b in at.button if (b.key == key if key else b.label == label))


reference = 'fr:base1-4'
statistiques_avant = requests.get(API + '/statistiques', timeout=15).json()
avant = requests.get(API + '/cartes/' + reference, timeout=15).json()
ids_avant = {e['_id'] for e in avant['exemplaires']}
ids_ajoutes = set()
try:
    at = AppTest.from_file('/projet/tableau_de_bord.py', default_timeout=90).run()
    verifier(at)
    assert at.radio[0].value == 'Catalogue'
    assert len(at.metric) == 3
    if statistiques_avant['exemplaires'] == 0:
        assert at.metric[0].value == '0'
        assert at.metric[1].value == '0'
        for rubrique in ['Ma collection', 'Statistiques', 'Recherche par sens']:
            at.radio[0].set_value(rubrique).run()
            verifier(at)
            assert at.info
            if rubrique == 'Statistiques':
                assert not at.dataframe
            elif rubrique == 'Recherche par sens':
                assert not at.text_input
        at.radio[0].set_value('Catalogue').run()
    next(s for s in at.selectbox if s.key == 'catalogue_bloc').set_value('base').run()
    at.text_input[0].set_value('Dracaufeu').run()
    verifier(at)
    # La première carte reste sélectionnée dans le bloc Base déjà importé.
    at.checkbox[0].check().run()
    verifier(at)
    bouton(at, 'Ajouter à ma collection').click().run()
    verifier(at)
    apres = requests.get(API + '/cartes/' + reference, timeout=15).json()
    ids_ajoutes = {e['_id'] for e in apres['exemplaires']} - ids_avant
    assert len(ids_ajoutes) == 1
    identifiant = next(iter(ids_ajoutes))
    assert requests.get(API + '/statistiques', timeout=15).json()['exemplaires'] == statistiques_avant['exemplaires'] + 1
    at.radio[0].set_value('Ma collection').run()
    verifier(at)
    at.text_input[0].set_value(avant['nom']).run()
    verifier(at)
    bouton(at, key='collection-0').click().run()
    verifier(at)
    assert any(h.value == avant['nom'] for h in at.subheader)
    at.radio[0].set_value('Statistiques').run()
    verifier(at)
    assert len(at.dataframe) == 2
    at.radio[0].set_value('Recherche par sens').run()
    at.text_input[0].set_value('Un Pokémon qui provoque des incendies')
    bouton(at, 'Trouver mes cartes').click().run()
    verifier(at)
    assert len(at.session_state['resultats']) >= 1
    maximum = len(at.session_state['resultats'])
    if maximum > 1:
        curseur = next(s for s in at.slider if s.key == 'top_k_recherche')
        assert curseur.max == maximum
        curseur.set_value(1).run()
        verifier(at)
        assert len([b for b in at.button if (b.key or '').startswith('semantique-')]) == 1
        next(s for s in at.slider if s.key == 'top_k_recherche').set_value(min(10, maximum)).run()
        verifier(at)
    assert any(x['carte']['nom'] == 'Dracaufeu' for x in at.session_state['resultats'])
    at.text_input[0].set_value('comment préparer des pâtes carbonara')
    bouton(at, 'Trouver mes cartes').click().run()
    verifier(at)
    resultats = at.session_state['resultats']
    if resultats:
        assert all(r['similarite'] >= max(.841, .95 * resultats[0]['similarite']) for r in resultats)
        assert [r['similarite'] for r in resultats] == sorted(
            (r['similarite'] for r in resultats), reverse=True)
    else:
        assert any(i.value == 'Aucun résultat suffisamment pertinent dans votre collection' for i in at.info)
    at.radio[0].set_value('Dernières consultations').run()
    verifier(at)
    assert any(avant['nom'] in m.value for m in at.markdown)
    # Retirer uniquement l'exemplaire ajouté par ce test après la recherche.
    at.radio[0].set_value('Ma collection').run()
    at.text_input[0].set_value(avant['nom']).run()
    bouton(at, key='collection-0').click().run()
    bouton(at, key='retirer-' + identifiant).click().run()
    verifier(at)
    ids_ajoutes.remove(identifiant)
    assert requests.get(API + '/statistiques', timeout=15).json() == statistiques_avant
    bouton(at, '← Revenir à l’exploration').click().run()
    if statistiques_avant['exemplaires'] == 0:
        for rubrique in ['Ma collection', 'Statistiques', 'Recherche par sens']:
            at.radio[0].set_value(rubrique).run()
            verifier(at)
            assert at.metric[0].value == at.metric[1].value == '0'
            assert at.info
    assert requests.get(API + '/images/base1-4', timeout=10).status_code == 200
    print('Interface : états vides, catalogue, ajout, statistiques, recherche, historique et retour à la collection initiale OK.')
finally:
    for identifiant in ids_ajoutes:
        requests.delete(API + '/collection/exemplaires/' + identifiant, timeout=15)
    if 'at' in locals():
        client_redis().delete('pokemon:session:' + at.session_state['session'] + ':consultations')
