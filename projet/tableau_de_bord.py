"""Interface Streamlit : utilise exclusivement l'API FastAPI."""
import base64
import html
import math
import os
from uuid import uuid4
from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st

API = os.getenv('POKEMON_API_URL', 'http://localhost:8000')
st.set_page_config(page_title='Pokécollection · Le classeur', page_icon='◓', layout='wide')
st.markdown('''<style>
.stApp {background:#f6f7fb;color:#20283e;}
.block-container {padding-top:2rem;padding-bottom:3rem;max-width:1480px;}
h1,h2,h3 {letter-spacing:-.035em;color:#18233b;}
h1 {font-size:2.25rem;font-weight:750;padding-bottom:.5rem;}
h3 {font-size:1.35rem;}
[data-testid="stSidebar"] {background:#fff;border-right:1px solid #e5e8f0;}
[data-testid="stMetric"] {background:white;border:1px solid #e5e8f0;border-radius:18px;padding:16px 20px;}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {color:#536077;}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {color:#18233b!important;font-weight:700;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong,
[data-testid="stWidgetLabel"] p {color:#20283e;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#536077!important;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:16px!important;}
.st-key-filtres {background:#fff;border:1px solid #e5e8f0;border-radius:18px;padding:16px 18px;margin:12px 0;}
[class*="st-key-catalogue-carte-"] {position:relative;gap:4px;}
[class*="st-key-catalogue-selection-"] {position:absolute;top:8px;right:8px;width:28px!important;z-index:2;}
[class*="st-key-catalogue-carte-"] > * {flex-shrink:0;}
[class*="st-key-catalogue-carte-"] > [data-testid="stElementContainer"]:last-child {margin-top:auto;}
[data-testid="stImage"] img {border-radius:12px;}
[data-testid="stColumn"] [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stImage"] img {height:280px;object-fit:contain;}
.stButton button, .stFormSubmitButton button, .stLinkButton a {border-radius:12px;font-weight:600;min-height:42px;}
.stButton button:hover {border-color:#c13832;}
[data-testid="stSidebar"] [data-baseweb="radio"] {padding:10px 12px;border-radius:12px;margin:2px 0;transition:background .15s;}
[data-testid="stSidebar"] [data-baseweb="radio"]:hover {background:#f6f7fb;}
[data-testid="stSidebar"] [data-baseweb="radio"]:has(input:checked) {background:#f4f6fb;box-shadow:inset 3px 0 #c13832;}
[data-testid="stSidebar"] [data-baseweb="radio"] p {font-weight:550;}
[data-testid="stExpander"] {border-color:#e5e8f0;border-radius:12px;background:#fff;}
[data-baseweb="input"], [data-baseweb="select"] > div {border-radius:10px;}
.brand {font-size:23px;font-weight:800;letter-spacing:-.06em;color:#18233b;margin:5px 0 3px;}
.brand span {color:#c13832;}
.card-name {font-size:18px;font-weight:700;color:#18233b;margin-top:4px;}
.card-meta {color:#536077;font-size:12px;min-height:30px;}
.pill {display:inline-block;border:1px solid #e2e5ed;background:#f4f6fb;padding:3px 9px;border-radius:20px;font-size:11px;color:#536077;margin:5px 4px 9px 0;}
.placeholder {height:280px;background:linear-gradient(145deg,#e5e9f4,#f4f5fa);border-radius:12px;display:flex;align-items:center;justify-content:center;color:#536077;font-size:14px;text-align:center;}
.catalogue-illustration {height:170px;margin-bottom:4px;}
.catalogue-illustration img {display:block;width:100%;height:170px;object-fit:contain;border-radius:8px;}
.catalogue-illustration .placeholder {height:170px;font-size:12px;}
.catalogue-infos {display:flex;flex-direction:column;gap:3px;}
.catalogue-infos .card-name {font-size:16px;line-height:17px;height:34px;margin:0;}
.catalogue-infos .card-meta {font-size:11px;line-height:13px;height:26px;min-height:0;}
.catalogue-infos .card-name, .catalogue-infos .card-meta {display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.catalogue-tags {height:36px;overflow:auto;line-height:18px;}
.catalogue-tags .pill {padding:1px 6px;margin:0 3px 2px 0;font-size:10px;line-height:16px;}
.catalogue-quantite {height:16px;font-size:11px;line-height:16px;color:#536077;}
[class*="st-key-catalogue-carte-"] .stButton button {min-height:34px;padding:4px 8px;}
@media (max-width:640px) {.block-container {padding-top:1rem;} h1 {font-size:1.8rem;}}
@media (prefers-reduced-motion:reduce) {* {transition:none!important;}}
</style>''', unsafe_allow_html=True)


def appeler(chemin, methode='GET', **kwargs):
    reponse = requests.request(methode, API + chemin, timeout=90 if chemin == '/recherche' else 12, **kwargs)
    if not reponse.ok:
        try:
            message = reponse.json().get('detail', 'Une erreur est survenue.')
        except ValueError:
            message = 'Le service ne répond pas correctement.'
        raise RuntimeError(str(message))
    return reponse.json()


@st.cache_data(ttl=3600, max_entries=1000, show_spinner=False)
def illustration(identifiant, langue='fr'):
    reponse = requests.get(API + '/images/' + quote(identifiant, safe=''), timeout=10)
    reponse.raise_for_status()
    return reponse.content


def afficher_image(carte, afficher_langue=True):
    try:
        contenu = illustration(carte['id'], carte.get('image_langue') or 'fr') if carte.get('image_locale') else None
    except requests.RequestException:
        contenu = None
    if contenu:
        st.image(contenu, width='stretch')
        if afficher_langue and carte.get('image_langue') == 'en':
            st.caption('Illustration EN')
    else:
        st.markdown('<div class="placeholder">Illustration indisponible</div>', unsafe_allow_html=True)


def ouvrir(reference):
    # Un clic = une consultation. Les reruns Streamlit ne créent pas d'entrée.
    st.session_state.selection = reference
    try:
        resultat = appeler(f'/sessions/{st.session_state.session}/consultations', 'POST', json={'carte_ref': reference})
        st.session_state.historique_disponible = resultat['historique_disponible']
    except (requests.RequestException, RuntimeError):
        st.session_state.historique_disponible = False


def navigation():
    st.session_state.selection = None


def page_initiale(cle):
    st.session_state[cle] = 1


def cocher(ref, cle):
    if st.session_state[cle]:
        st.session_state.cartes_choisies.add(ref)
    else:
        st.session_state.cartes_choisies.discard(ref)


def ajouter(references):
    try:
        resultat = appeler('/collection/exemplaires', 'POST', json={
            'references': references, 'requete_id': str(uuid4())})
        st.session_state.message = f"{resultat['ajoutes']} exemplaire(s) ajouté(s) à la collection."
        for ref in references:
            st.session_state.cartes_choisies.discard(ref)
            if 'choix-' + ref in st.session_state:
                st.session_state['choix-' + ref] = False
        st.session_state.pop('resultats', None)
    except (requests.RequestException, RuntimeError) as erreur:
        st.session_state.erreur_action = str(erreur)


def retirer(identifiant):
    try:
        appeler('/collection/exemplaires/' + identifiant, 'DELETE')
        st.session_state.message = 'Un exemplaire a été retiré.'
        st.session_state.pop('resultats', None)
    except (requests.RequestException, RuntimeError) as erreur:
        st.session_state.erreur_action = str(erreur)


def apercu_catalogue(carte):
    """Un seul bloc de mise en page pour empêcher le chevauchement des textes."""
    try:
        contenu = illustration(carte['id'], carte.get('image_langue') or 'fr') if carte.get('image_locale') else None
    except requests.RequestException:
        contenu = None
    if contenu:
        mime = 'image/png' if contenu.startswith(b'\x89PNG') else 'image/webp'
        source = 'data:' + mime + ';base64,' + base64.b64encode(contenu).decode('ascii')
        image = f'<img src="{source}" alt="{html.escape(carte["nom"], quote=True)}">'
    else:
        image = '<div class="placeholder">Illustration indisponible</div>'
    nom = html.escape(carte['nom'], quote=True)
    meta = html.escape(carte['extension'] + ' · N° ' + carte['numero'], quote=True)
    tags = ''.join('<span class="pill">' + html.escape(x) + '</span>' for x in [*carte['types'], carte['rarete']])
    quantite = carte.get('quantite', 0)
    possession = f"{quantite} exemplaire{'s' if quantite > 1 else ''} possédé{'s' if quantite > 1 else ''}" if quantite else ''
    st.markdown(f'<div class="catalogue-illustration">{image}</div>'
                f'<div class="catalogue-infos"><div class="card-name" title="{nom}">{nom}</div>'
                f'<div class="card-meta" title="{meta}">{meta}</div><div class="catalogue-tags">{tags}</div>'
                f'<div class="catalogue-quantite">{possession}</div></div>', unsafe_allow_html=True)


def grille(cartes, prefixe, distances=None, selectionnable=False, passages=None):
    for debut in range(0, len(cartes), 4):
        colonnes = st.columns(4, gap='medium')
        for indice, carte in enumerate(cartes[debut:debut + 4], start=debut):
            with colonnes[indice % 4], st.container(
                    border=True, width='stretch', height=370 if selectionnable else 'content',
                    key=f'catalogue-carte-{indice}' if selectionnable else None):
                if selectionnable:
                    cle = 'choix-' + carte['_id']
                    with st.container(horizontal=True, horizontal_alignment='right', gap=None,
                                      key=f'catalogue-selection-{indice}'):
                        st.checkbox('Sélectionner ' + carte['nom'],
                                    value=carte['_id'] in st.session_state.cartes_choisies,
                                    key=cle, label_visibility='collapsed',
                                    on_change=cocher, args=(carte['_id'], cle))
                if selectionnable:
                    apercu_catalogue(carte)
                else:
                    afficher_image(carte, afficher_langue=prefixe != 'collection')
                    st.markdown('<div class="card-name">' + html.escape(carte['nom']) + '</div>', unsafe_allow_html=True)
                    st.markdown('<div class="card-meta">' + html.escape(carte['extension']) + ' · N° ' + html.escape(carte['numero']) + '</div>', unsafe_allow_html=True)
                    st.markdown(''.join('<span class="pill">' + html.escape(x) + '</span>' for x in [*carte['types'], carte['rarete']]), unsafe_allow_html=True)
                if distances is not None:
                    st.caption(f"Distance cosinus : {distances[indice]:.3f}")
                if passages and passages[indice]:
                    st.write(passages[indice])
                if carte.get('quantite') and not selectionnable:
                    quantite = carte['quantite']
                    st.caption(f"{quantite} exemplaire{'s' if quantite > 1 else ''} possédé{'s' if quantite > 1 else ''}")
                st.button('Voir la carte', key=f'{prefixe}-{indice}', width='stretch',
                          on_click=ouvrir, args=(carte['_id'],))


def afficher_liste(est_catalogue):
    prefixe = 'catalogue' if est_catalogue else 'collection'
    chemin_filtres = '/catalogue/filtres' if est_catalogue else '/filtres'
    cle_page = 'page_' + prefixe
    if est_catalogue:
        perimetre = appeler('/catalogue/perimetre')
        st.caption(f"{perimetre['cartes']:,} cartes · ".replace(',', ' ') +
                   (', '.join(perimetre['blocs']) or 'Aucun bloc importé'))
        with st.expander('Extensions disponibles'):
            st.caption('Catalogue français importé localement · Certaines illustrations sont en anglais.')
            if perimetre['extensions']:
                st.dataframe(pd.DataFrame([{'Bloc': x.get('bloc') or 'Non renseigné',
                    'Extension': x['extension'], 'Cartes Pokémon': x['cartes'],
                    'Images manquantes': x.get('images_manquantes', 0),
                    'Illustrations anglaises': x.get('images_anglaises', 0),
                    'Textes exploitables': x.get('textes_exploitables', 0)} for x in perimetre['extensions']]),
                    hide_index=True, width='stretch')
            else:
                st.write('Aucune extension importée.')
    filtres = appeler(chemin_filtres)
    with st.container(key='filtres'):
        f1, f2, f3, f4, f5 = st.columns([1.6, 1, 1.3, 1, 1.2])
    rappel = {'on_change': page_initiale, 'args': (cle_page,)}
    nom = f1.text_input('Nom de la carte', placeholder='Pikachu, Dracaufeu…', key=prefixe + '_nom', **rappel)
    blocs = {'': 'Tous les blocs', **{x['id']: x['nom'] for x in filtres['blocs']}}
    bloc = f2.selectbox('Bloc', list(blocs), format_func=blocs.get, key=prefixe + '_bloc', **rappel)
    if bloc:
        filtres = appeler(chemin_filtres, params={'bloc': bloc})
    extensions = {'': 'Toutes les extensions', **{x['id']: x['nom'] for x in filtres['extensions']}}
    cle_extension = prefixe + '_extension'
    if st.session_state.get(cle_extension, '') not in extensions:
        st.session_state[cle_extension] = ''
    extension = f3.selectbox('Extension', list(extensions), format_func=extensions.get, key=cle_extension, **rappel)
    types = ['Tous les types'] + filtres['types']
    raretes = ['Toutes les raretés'] + filtres['raretes']
    for cle, options in [(prefixe + '_type', types), (prefixe + '_rarete', raretes)]:
        if st.session_state.get(cle, options[0]) not in options:
            st.session_state[cle] = options[0]
    type_carte = f4.selectbox('Type', types, key=prefixe + '_type', **rappel)
    rarete = f5.selectbox('Rareté', raretes, key=prefixe + '_rarete', **rappel)
    params = {'nom': nom, 'bloc': bloc, 'extension': extension,
              'type_carte': '' if type_carte == types[0] else type_carte,
              'rarete': '' if rarete == raretes[0] else rarete, 'page': st.session_state[cle_page]}
    resultat = appeler('/' + prefixe, params=params)
    pages = max(1, math.ceil(resultat['total'] / 12))
    if st.session_state[cle_page] > pages:
        st.session_state[cle_page] = pages
        st.rerun()
    resume, action = st.columns([2, 1], vertical_alignment='center')
    resume.caption(f"{resultat['total']} carte{'s' if resultat['total'] != 1 else ''}")
    if est_catalogue:
        choix = sorted(st.session_state.cartes_choisies)
        if choix:
            resume.caption(f"{len(choix)} sélectionnée{'s' if len(choix) > 1 else ''}")
        action.button('Ajouter à ma collection', type='primary', disabled=not choix or len(choix) > 200,
                      width='stretch', on_click=ajouter, args=(choix,))
        if len(choix) > 200:
            st.warning('Ajoutez au maximum 200 cartes à la fois.')
    if not resultat['cartes']:
        st.info('Aucune carte ne correspond à ces filtres.' if est_catalogue else
                'Aucune carte ici. Ajoutez vos premières cartes depuis le catalogue.')
    grille(resultat['cartes'], prefixe, selectionnable=est_catalogue)
    precedent, milieu, suivant = st.columns([1, 3, 1])
    if precedent.button('← Précédent', disabled=st.session_state[cle_page] <= 1):
        st.session_state[cle_page] -= 1
        st.rerun()
    milieu.caption(f'Page {st.session_state[cle_page]} sur {pages}')
    if suivant.button('Suivant →', disabled=st.session_state[cle_page] >= pages):
        st.session_state[cle_page] += 1
        st.rerun()


def afficher_fiche(afficher_langue=True):
    carte = appeler('/cartes/' + quote(st.session_state.selection, safe=''))
    if st.button('← Revenir à l’exploration'):
        st.session_state.selection = None
        st.rerun()
    gauche, droite = st.columns([1, 2], gap='large')
    with gauche:
        afficher_image(carte, afficher_langue=afficher_langue)
    with droite:
        st.subheader(carte['nom'])
        st.caption(f"{carte.get('bloc', 'Non renseigné')} · {carte['extension']} · N° {carte['numero']} · {carte['rarete']}")
        st.write(' · '.join(carte['types']) + (f" · {carte['pv']} PV" if carte.get('pv') else ''))
        if carte.get('description'):
            st.write(carte['description'])
        for capacite in carte.get('capacites', []):
            st.markdown('**' + capacite.get('name', 'Capacité') + '**')
            st.write(capacite.get('effect', ''))
        for attaque in carte.get('attaques', []):
            st.markdown('**' + attaque.get('name', 'Attaque') + '** — ' + str(attaque.get('damage', '')))
            st.write(attaque.get('effect', ''))
        st.button('Ajouter un exemplaire', type='primary', on_click=ajouter, args=([carte['_id']],))
        st.markdown(f"**Ma collection : {len(carte['exemplaires'])} exemplaire(s)**")
        for numero, e in enumerate(carte['exemplaires'], 1):
            with st.expander(f"Exemplaire {numero}" + (' · ' + e['etat'] if e.get('etat') else '')):
                with st.form('informations-' + e['_id']):
                    etat = st.text_input('État (facultatif)', value=e.get('etat') or '', max_chars=40)
                    variante = st.text_input('Variante (facultative)', value=e.get('variante') or '', max_chars=60)
                    prix = st.number_input('Prix d’achat en € (facultatif)', min_value=0.0, max_value=99999999.99,
                                           value=e['prix_centimes'] / 100 if e.get('prix_centimes') is not None else None,
                                           step=0.01, format='%.2f')
                    if st.form_submit_button('Enregistrer les informations'):
                        appeler('/collection/exemplaires/' + e['_id'], 'PATCH',
                                json={'etat': etat.strip() or None, 'variante': variante.strip() or None, 'prix_achat': prix})
                        st.session_state.message = 'Informations enregistrées.'
                        st.rerun()
                st.button('Retirer cet exemplaire', key='retirer-' + e['_id'], on_click=retirer, args=(e['_id'],))
        if not carte.get('texte'):
            st.caption('Recherche par sens indisponible pour cette carte.')
        if not st.session_state.historique_disponible:
            st.caption('L’historique est momentanément indisponible. La consultation reste possible.')


for cle, valeur in {'session': str(uuid4()), 'selection': None, 'historique_disponible': True,
                    'cartes_choisies': set(), 'page_catalogue': 1, 'page_collection': 1}.items():
    if cle not in st.session_state:
        st.session_state[cle] = valeur

with st.sidebar:
    st.markdown('<div class="brand">◓ Poké<span>collection</span></div>', unsafe_allow_html=True)
    st.divider()
    rubrique = st.radio('Explorer', ['Catalogue', 'Ma collection', 'Recherche par sens', 'Dernières consultations', 'Statistiques'],
                        key='navigation', on_change=navigation, label_visibility='collapsed')
    st.divider()
    st.caption('Votre collection, sans compte.')
    st.link_button('Données TCGdex ↗', 'https://tcgdex.dev/fr/')

st.title('Détail de la carte' if st.session_state.selection else rubrique)
if st.session_state.get('message'):
    st.success(st.session_state.pop('message'))
if st.session_state.get('erreur_action'):
    st.error(st.session_state.pop('erreur_action'))

try:
    stats = appeler('/statistiques')
    indicateurs = st.columns(3)
    indicateurs[0].metric('Exemplaires', f"{stats['exemplaires']:,}".replace(',', ' '))
    indicateurs[1].metric('Cartes distinctes', stats['cartes_distinctes'])
    indicateurs[2].metric('Total des achats', f"{stats['depenses']:,.2f} €".replace(',', ' ').replace('.', ','),
                          help=f"Prix renseigné pour {stats['achats_renseignes']} exemplaire(s). Ce total ne représente pas la valeur marchande.")
    if st.session_state.selection:
        afficher_fiche(afficher_langue=rubrique not in ['Catalogue', 'Ma collection'])
    elif rubrique in ['Catalogue', 'Ma collection']:
        afficher_liste(rubrique == 'Catalogue')
    elif rubrique == 'Recherche par sens':
        st.caption('Trouvez une carte de votre collection à partir de ses effets ou de sa description.')
        if not stats['exemplaires']:
            st.info('Ajoutez des cartes depuis le catalogue pour rechercher dans votre collection.')
        else:
            with st.form('recherche'):
                phrase = st.text_input('Que cherchez-vous ?', placeholder='Un Pokémon qui provoque des incendies', max_chars=500)
                envoyer = st.form_submit_button('Trouver mes cartes', type='primary')
            if envoyer:
                if len(phrase.strip()) < 2:
                    st.warning('Saisissez quelques mots pour lancer la recherche.')
                else:
                    with st.spinner('À la recherche des cartes les plus proches…'):
                        try:
                            st.session_state.resultats = appeler('/recherche', 'POST', json={'texte': phrase})['resultats']
                        except (requests.RequestException, RuntimeError) as erreur:
                            st.session_state.resultats = []
                            st.warning(str(erreur))
            if st.session_state.get('resultats'):
                st.caption(f"{len(st.session_state.resultats)} résultat(s)")
                grille([x['carte'] for x in st.session_state.resultats], 'semantique',
                       [x['distance'] for x in st.session_state.resultats],
                       passages=[x.get('passage', '') for x in st.session_state.resultats])
            elif envoyer and len(phrase.strip()) >= 2:
                st.info('Aucun résultat suffisamment pertinent dans votre collection')
    elif rubrique == 'Dernières consultations':
        st.caption('Vos 10 dernières consultations · Effacées après 30 min d’inactivité')
        resultat = appeler(f'/sessions/{st.session_state.session}/consultations')
        if not resultat['disponible']:
            st.info('L’historique est momentanément indisponible. Le catalogue et la collection restent accessibles.')
        elif not resultat['cartes']:
            st.info('Les cartes que vous ouvrez apparaîtront ici.')
        else:
            grille(resultat['cartes'], 'historique')
    else:
        st.subheader('Répartition de la collection')
        if not stats['exemplaires']:
            st.info('Ajoutez votre première carte depuis le catalogue.')
        else:
            gauche, droite = st.columns(2)
            for colonne, champ, titre in [(gauche, 'extensions', 'Par extension'), (droite, 'raretes', 'Par rareté')]:
                with colonne:
                    st.markdown('**' + titre + '**')
                    donnees = pd.DataFrame(stats[champ]).rename(columns={'_id': 'Catégorie', 'exemplaires': 'Exemplaires'})
                    graphique = alt.Chart(donnees).mark_bar(color='#df6256', cornerRadiusEnd=6).encode(
                        y=alt.Y('Catégorie:N', sort='-x', title=None),
                        x=alt.X('Exemplaires:Q', title='Exemplaires'), tooltip=['Catégorie', 'Exemplaires'])
                    st.altair_chart(graphique, width='stretch')
                    with st.expander('Voir les données'):
                        st.dataframe(donnees, hide_index=True, width='stretch')
except (requests.RequestException, RuntimeError) as erreur:
    st.error('Le service est momentanément indisponible. ' + str(erreur))
    st.button('Réessayer')
