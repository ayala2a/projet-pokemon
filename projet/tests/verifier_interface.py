"""Test du parcours Streamlit avec son moteur officiel, API locale démarrée."""
import requests
from streamlit.testing.v1 import AppTest


def verifier(at):
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error, [e.value for e in at.error]


at = AppTest.from_file('/projet/tableau_de_bord.py', default_timeout=90).run()
verifier(at)
assert len(at.metric) == 3
at.text_input[0].set_value('Dracaufeu').run()
verifier(at)
at.button[0].click().run()
verifier(at)
assert any(h.value == 'Dracaufeu' for h in at.subheader)
at.button[0].click().run()
at.radio[0].set_value('Dernières consultations').run()
verifier(at)
assert any('Dracaufeu' in m.value for m in at.markdown)
at.radio[0].set_value('Statistiques').run()
verifier(at)
assert len(at.dataframe) == 2
at.radio[0].set_value('Recherche par sens').run()
at.text_input[0].set_value('Un Pokémon qui provoque des incendies')
at.button[0].click().run()
verifier(at)
assert len(at.session_state['resultats']) == 5
assert any(x['carte']['nom'] == 'Dracaufeu' for x in at.session_state['resultats'])
reponse = requests.get('http://localhost:8000/images/base1-4', timeout=10)
assert reponse.status_code == 200
assert reponse.headers['content-type'] == 'image/webp'
print('Interface : accueil, filtre, fiche, historique, statistiques, recherche et image OK.')
