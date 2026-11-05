"""Interface Streamlit : utilise exclusivement l'API FastAPI."""
import html
import math
import os
from uuid import uuid4

import altair as alt
import pandas as pd
import requests
import streamlit as st

API = os.getenv('POKEMON_API_URL', 'http://localhost:8000')
st.set_page_config(page_title='Pokécollection · Le classeur', page_icon='◓', layout='wide')
st.markdown('''<style>
.stApp {background:#f6f7fb;color:#20283e;}
.block-container {padding-top:2.6rem;max-width:1480px;}
h1,h2,h3 {letter-spacing:-.035em;color:#18233b;}
[data-testid="stSidebar"] {background:#fff;border-right:1px solid #e5e8f0;}
[data-testid="stMetric"] {background:white;border:1px solid #e5e8f0;border-radius:16px;padding:18px 22px;}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {color:#536077;}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {color:#18233b!important;font-weight:700;}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong,
[data-testid="stWidgetLabel"] p {color:#20283e;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color:#536077!important;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:16px!important;}
[data-testid="stImage"] img {border-radius:12px;}
.stButton button {border-radius:10px;}
.eyebrow {font-size:12px;font-weight:700;letter-spacing:.14em;color:#b63735;margin-bottom:12px;}
.intro {color:#536077;max-width:760px;font-size:16px;margin-bottom:26px;}
.brand {font-size:23px;font-weight:800;letter-spacing:-.06em;color:#18233b;margin:5px 0 3px;}
.brand span {color:#c13832;}
.side-note {color:#536077;font-size:12px;line-height:1.7;}
.card-name {font-size:18px;font-weight:700;color:#18233b;margin-top:8px;}
.card-meta {color:#536077;font-size:12px;min-height:38px;}
.pill {display:inline-block;border:1px solid #e2e5ed;background:#f4f6fb;padding:3px 9px;border-radius:20px;font-size:11px;color:#536077;margin:5px 4px 9px 0;}
.placeholder {height:250px;background:linear-gradient(145deg,#e5e9f4,#f4f5fa);border-radius:12px;display:flex;align-items:center;justify-content:center;color:#536077;font-size:14px;text-align:center;}
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
def illustration(identifiant):
    reponse = requests.get(API + '/images/' + identifiant, timeout=10)
    return reponse.content if reponse.ok else None


def afficher_image(carte):
    try:
        contenu = illustration(carte['id']) if carte.get('image_locale') else None
    except requests.RequestException:
        contenu = None
    if contenu:
        st.image(contenu, width='stretch')
    else:
        st.markdown('<div class="placeholder">Illustration indisponible<br>La fiche reste consultable</div>', unsafe_allow_html=True)


def ouvrir(reference):
    # Un clic = une consultation. Les reruns Streamlit ne créent pas d'entrée.
    st.session_state.selection = reference
    try:
        resultat = appeler(f'/sessions/{st.session_state.session}/consultations', 'POST', json={'carte_ref': reference})
        st.session_state.historique_disponible = resultat['historique_disponible']
    except (requests.RequestException, RuntimeError):
        st.session_state.historique_disponible = False


def reinitialiser_page():
    st.session_state.page = 1


def grille(cartes, prefixe, distances=None):
    for debut in range(0, len(cartes), 4):
        colonnes = st.columns(4, gap='medium')
        for indice, carte in enumerate(cartes[debut:debut + 4], start=debut):
            with colonnes[indice % 4], st.container(border=True):
                afficher_image(carte)
                st.markdown('<div class="card-name">' + html.escape(carte['nom']) + '</div>', unsafe_allow_html=True)
                st.markdown('<div class="card-meta">' + html.escape(carte['extension']) + ' · N° ' + html.escape(carte['numero']) + '</div>', unsafe_allow_html=True)
                st.markdown(''.join('<span class="pill">' + html.escape(x) + '</span>' for x in [*carte['types'], carte['rarete']]), unsafe_allow_html=True)
                if distances is not None:
                    st.caption(f"Distance cosinus : {distances[indice]:.3f}")
                elif 'quantite' in carte:
                    st.caption(f"{carte['quantite']} exemplaire(s)")
                st.button('Voir la carte ↗', key=f'{prefixe}-{indice}', width='stretch',
                          on_click=ouvrir, args=(carte['_id'],))


if 'session' not in st.session_state:
    st.session_state.session = str(uuid4())
    st.session_state.page = 1
    st.session_state.selection = None
    st.session_state.historique_disponible = True

with st.sidebar:
    st.markdown('<div class="brand">◓ Poké<span>collection</span></div>', unsafe_allow_html=True)
    st.caption('LE CLASSEUR DE DÉMONSTRATION')
    st.divider()
    rubrique = st.radio('Explorer', ['Ma collection', 'Recherche par sens', 'Dernières consultations', 'Statistiques'], label_visibility='collapsed')
    st.divider()
    st.markdown('**Une collection, mille histoires.**')
    st.markdown('<p class="side-note">Parcourez les cartes, retrouvez un pouvoir ou redécouvrez un Pokémon. Sans compte, simplement.</p>', unsafe_allow_html=True)
    st.caption('Collection et achats simulés · Données TCGdex')
    st.link_button('À propos de TCGdex ↗', 'https://tcgdex.dev/fr/')

st.markdown('<div class="eyebrow">LE PLAISIR DE COLLECTIONNER</div>', unsafe_allow_html=True)
st.title('Votre prochain coup de cœur est ici.')
st.markdown('<div class="intro">Un classeur à explorer, des histoires à retrouver. Découvrez notre collection de cartes Pokémon en français.</div>', unsafe_allow_html=True)

try:
    stats = appeler('/statistiques')
    indicateurs = st.columns(3)
    indicateurs[0].metric('Exemplaires dans le classeur', f"{stats['exemplaires']:,}".replace(',', ' '))
    indicateurs[1].metric('Cartes différentes', stats['cartes_distinctes'])
    indicateurs[2].metric('Achats simulés', f"{stats['depenses']:,.2f} €".replace(',', ' ').replace('.', ','))
    st.caption('Les montants représentent des dépenses fictives, pas une estimation de valeur marchande.')
    if not stats['exemplaires']:
        st.info('La collection est vide. Lancez le script d’import décrit dans le fichier LISEZMOI du projet.')
        st.stop()

    if st.session_state.selection:
        carte = appeler('/cartes/' + st.session_state.selection)
        if st.button('← Revenir à l’exploration'):
            st.session_state.selection = None
            st.rerun()
        gauche, droite = st.columns([1, 2], gap='large')
        with gauche:
            afficher_image(carte)
        with droite:
            st.subheader(carte['nom'])
            st.caption(f"{carte['extension']} · N° {carte['numero']} · {carte['rarete']}")
            st.write(' · '.join(carte['types']) + (f" · {carte['pv']} PV" if carte.get('pv') else ''))
            if carte.get('description'):
                st.write(carte['description'])
            for capacite in carte.get('capacites', []):
                st.markdown('**' + capacite.get('name', 'Capacité') + '**')
                st.write(capacite.get('effect', ''))
            for attaque in carte.get('attaques', []):
                st.markdown('**' + attaque.get('name', 'Attaque') + '** — ' + str(attaque.get('damage', '')))
                st.write(attaque.get('effect', ''))
            st.markdown('**Les exemplaires de ce classeur**')
            st.dataframe(pd.DataFrame([{'État': e['etat'], 'Variante': e['variante'],
                'Achat simulé (€)': e['prix_centimes'] / 100, 'Date d’achat': e['date_achat']}
                for e in carte['exemplaires']]), hide_index=True, width='stretch')
            if not carte.get('texte'):
                st.caption('Pas de texte exploitable : cette carte est exclue de la recherche par sens.')
            if not st.session_state.historique_disponible:
                st.caption('L’historique est momentanément indisponible. La consultation reste possible.')
        st.stop()

    st.divider()
    if rubrique == 'Ma collection':
        titre, total = st.columns([3, 1])
        titre.subheader('Dans le classeur')
        filtres = appeler('/filtres')
        f1, f2, f3, f4 = st.columns([2, 1.4, 1, 1.2])
        nom = f1.text_input('Nom de la carte', placeholder='Pikachu, Dracaufeu…', on_change=reinitialiser_page)
        extensions = {'': 'Toutes les extensions', **{x['id']: x['nom'] for x in filtres['extensions']}}
        extension = f2.selectbox('Extension', list(extensions), format_func=extensions.get, on_change=reinitialiser_page)
        type_carte = f3.selectbox('Type', ['Tous les types'] + filtres['types'], on_change=reinitialiser_page)
        rarete = f4.selectbox('Rareté', ['Toutes les raretés'] + filtres['raretes'], on_change=reinitialiser_page)
        resultat = appeler('/collection', params={'nom': nom, 'extension': extension,
            'type_carte': '' if type_carte == 'Tous les types' else type_carte,
            'rarete': '' if rarete == 'Toutes les raretés' else rarete, 'page': st.session_state.page})
        total.caption(f"{resultat['total']} carte(s) correspondent")
        if not resultat['cartes']:
            st.info('Aucune carte ne correspond à ces filtres. Essayez une recherche plus large.')
        grille(resultat['cartes'], 'collection')
        pages = max(1, math.ceil(resultat['total'] / 12))
        precedent, milieu, suivant = st.columns([1, 3, 1])
        if precedent.button('← Précédent', disabled=st.session_state.page <= 1):
            st.session_state.page -= 1
            st.rerun()
        milieu.caption(f'Page {st.session_state.page} sur {pages}')
        if suivant.button('Suivant →', disabled=st.session_state.page >= pages):
            st.session_state.page += 1
            st.rerun()
    elif rubrique == 'Recherche par sens':
        st.subheader('Une idée en tête ?')
        st.write('Décrivez une capacité, un effet ou une histoire. La recherche porte sur les cartes de ce classeur.')
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
                        st.session_state.phrase = phrase
                    except (requests.RequestException, RuntimeError) as erreur:
                        st.session_state.resultats = []
                        st.warning(str(erreur))
        if st.session_state.get('resultats'):
            st.caption('Les cinq cartes les plus proches · Plus la distance cosinus est faible, plus le texte est proche. Ce n’est pas une probabilité.')
            grille([x['carte'] for x in st.session_state.resultats], 'semantique', [x['distance'] for x in st.session_state.resultats])
        elif envoyer and len(phrase.strip()) >= 2:
            st.info('Aucun résultat disponible pour le moment. Les filtres classiques restent accessibles.')
    elif rubrique == 'Dernières consultations':
        st.subheader('Vos dernières découvertes')
        st.caption('Dix consultations au maximum, de la plus récente à la plus ancienne. L’historique expire après 30 minutes d’inactivité ; les doublons sont conservés.')
        resultat = appeler(f'/sessions/{st.session_state.session}/consultations')
        if not resultat['disponible']:
            st.info('L’historique est momentanément indisponible. Vous pouvez continuer à explorer la collection.')
        elif not resultat['cartes']:
            st.info('Votre histoire commence ici : ouvrez une carte pour la retrouver dans cette liste.')
        else:
            grille(resultat['cartes'], 'historique')
    else:
        st.subheader('Le classeur en quelques chiffres')
        st.caption('Répartition des exemplaires possédés, doublons inclus.')
        gauche, droite = st.columns(2)
        for colonne, champ, titre in [(gauche, 'extensions', 'Par extension'), (droite, 'raretes', 'Par rareté')]:
            with colonne:
                st.markdown('**' + titre + '**')
                donnees = pd.DataFrame(stats[champ]).rename(columns={'_id': 'Catégorie', 'exemplaires': 'Exemplaires'})
                graphique = alt.Chart(donnees).mark_bar(color='#df6256', cornerRadiusEnd=6).encode(
                    y=alt.Y('Catégorie:N', sort='-x', title=None),
                    x=alt.X('Exemplaires:Q', title='Exemplaires'), tooltip=['Catégorie', 'Exemplaires'])
                st.altair_chart(graphique, width='stretch')
                st.dataframe(donnees, hide_index=True, width='stretch')
except (requests.RequestException, RuntimeError) as erreur:
    st.error('Le classeur est momentanément indisponible. ' + str(erreur))
    st.button('Réessayer')
