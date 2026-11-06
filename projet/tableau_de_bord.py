"""Interface Streamlit : utilise exclusivement l'API FastAPI."""
import base64
import html
import json
import math
import os
import secrets
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
[class*="st-key-collection-carte-"] {position:relative;}
[class*="st-key-collection-selection-"] {position:absolute;top:8px;right:8px;width:28px!important;z-index:2;}
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
[class*="st-key-exemplaire-"] [data-baseweb="input"] {background:#f4f6fb;border:1px solid #e5e8f0;border-radius:10px;}
[class*="st-key-exemplaire-"] [data-baseweb="input"] input {color:#20283e;}
[class*="st-key-exemplaire-"] [data-testid="stExpander"] {border:0;background:transparent;}
@media (max-width:640px) {.block-container {padding-top:1rem;} h1 {font-size:1.8rem;}}
@media (prefers-reduced-motion:reduce) {* {transition:none!important;}}
</style>''', unsafe_allow_html=True)


def entetes_console():
    return {'X-Poke-Session': st.session_state.session,
            'X-Poke-Trace-Token': st.session_state.console_jeton,
            'X-Poke-Debug': '1' if st.session_state.get('mode_developpeur') else '0'}


def appeler(chemin, methode='GET', **kwargs):
    reponse = requests.request(methode, API + chemin, headers=entetes_console(),
                              timeout=90 if chemin == '/recherche' else 12, **kwargs)
    if not reponse.ok:
        try:
            message = reponse.json().get('detail', 'Une erreur est survenue.')
        except ValueError:
            message = 'Le service ne répond pas correctement.'
        raise RuntimeError(str(message))
    return reponse.json()


@st.cache_data(ttl=3600, max_entries=1000, show_spinner=False)
def illustration_cache(identifiant, langue='fr'):
    # Un cache hit n'exécute aucun appel backend : aucune trace n'est inventée.
    return charger_illustration(identifiant)


def charger_illustration(identifiant):
    reponse = requests.get(API + '/images/' + quote(identifiant, safe=''),
                          headers=entetes_console(), timeout=10)
    reponse.raise_for_status()
    return reponse.content


def illustration(identifiant, langue='fr'):
    # La console montre les lectures d'images réelles, même si le cache d'une
    # autre session est déjà chaud. Les fichiers restent servis localement.
    if st.session_state.get('mode_developpeur'):
        return charger_illustration(identifiant)
    return illustration_cache(identifiant, langue)


def operations_console(evenements):
    """Rapprocher uniquement les événements portant le même identifiant backend."""
    groupes = {}
    for item in evenements:
        details = item['details']
        identifiant = details.get('operation_id') or details.get('appel_id')
        cle = (item['source'], identifiant) if identifiant else ('evenement', item['ordre'])
        if cle not in groupes:
            groupes[cle] = {**item, 'details': {}}
        groupes[cle]['details'].update(details)
        if item.get('dao'):
            groupes[cle]['dao'] = item['dao']
    return list(groupes.values())


def afficher_operation_console(item):
    source, details = item['source'], item['details']
    nom = item.get('dao') or details.get('methode_dao')
    with st.container(border=True):
        st.markdown(f"**{source} · {item['operation']}**")
        duree = details.get('duree_ms')
        st.caption(f"{item['heure'][11:23]} UTC" + (f' · {nom}' if nom else '') +
                   (f' · {duree:.2f} ms' if duree is not None else ''))
        if source == 'MongoDB':
            commande = details.get('commande')
            if commande is not None:
                # Retirer les métadonnées de protocole, garder filtres, pipelines et écritures.
                utile = {k: v for k, v in commande.items()
                         if k not in {'$clusterTime', '$db', 'lsid', 'txnNumber'}}
                st.code(json.dumps(utile, ensure_ascii=False, indent=2), language='json')
            if 'writeConcern' in details:
                st.json({'base': details.get('base'), 'writeConcern': details['writeConcern']}, expanded=True)
            if 'resultat' in details:
                st.markdown('**Résultat MongoDB**')
                st.json(details['resultat'], expanded=True)
        elif source == 'PostgreSQL':
            if 'sql' in details:
                st.code(details['sql'].strip(), language='sql')
            if 'parametres' in details:
                st.markdown('**Paramètres**')
                st.json(details['parametres'], expanded=True)
            if 'statut' in details:
                st.caption(f"{details['statut']} · {details.get('lignes', '—')} ligne(s)")
            if 'resultat' in details:
                st.markdown('**Résultat PostgreSQL**')
                st.json(details['resultat'], expanded=True)
        elif source == 'pgvector':
            st.json({k: v for k, v in details.items() if k != 'candidats'}, expanded=True)
            if 'candidats' in details:
                candidats = details['candidats']
                lignes = candidats.get('extrait', []) if isinstance(candidats, dict) else candidats
                if lignes:
                    st.dataframe([{'Carte': c['carte_ref'], 'Passage comparé': c.get('passage_compare'),
                                   'Distance': c['distance'], 'Similarité': c['similarite'],
                                   'Seuil de similarité': details['seuil_similarite'],
                                   'Décision': 'Accepté' if c['accepte'] else 'Rejeté',
                                   'Motif': c['raison']} for c in lignes],
                                 hide_index=True, width='stretch',
                                 column_config={'Distance': st.column_config.NumberColumn(format='%.6f'),
                                                'Similarité': st.column_config.NumberColumn(format='%.6f'),
                                                'Seuil de similarité': st.column_config.NumberColumn(format='%.6f'),
                                                'Passage comparé': st.column_config.TextColumn(width='large')})
                else:
                    st.caption('Aucun candidat observé.')
                if isinstance(candidats, dict):
                    st.caption(f"Extrait de {candidats['total']} candidats · {candidats['omis']} omis de l’affichage")
        elif source == 'Redis':
            if 'cle' in details:
                st.code(details['cle'], language=None)
            if 'commandes' in details:
                st.markdown('**Commandes exécutées**')
                st.json(details['commandes'], expanded=True)
            if 'contenu_liste' in details:
                st.markdown('**Contenu observé de la liste**')
                st.json(details['contenu_liste'], expanded=True)
            st.json({k: v for k, v in details.items() if k not in {'cle', 'commandes', 'contenu_liste'}}, expanded=True)
        if 'erreur' in details:
            st.json({k: details[k] for k in ('erreur', 'message') if k in details}, expanded=True)


@st.fragment
def console_developpeur():
    st.divider()
    st.subheader('Console développeur')
    st.caption('Opérations réelles des bases · Cette session · Les plus récentes en premier')
    try:
        afficher_images = st.checkbox('Afficher les appels /images/…', key='console_images', value=False)
        gauche, droite = st.columns([1, 1])
        if gauche.button('Effacer la console', key='effacer_console'):
            appeler('/debug/traces', 'DELETE')
        droite.button('Actualiser les traces', key='actualiser_console')
        requetes = appeler('/debug/traces', params={'inclure_images': afficher_images})['requetes']
    except (requests.RequestException, RuntimeError) as erreur:
        st.warning('Console indisponible : ' + str(erreur))
        return
    if not requetes:
        st.info('La console est vide. Les prochaines actions apparaîtront ici.')
        return
    st.caption(f'{len(requetes)} requêtes · Conservation temporaire et bornée · Durées HTTP jusqu’aux en-têtes de réponse')
    for requete in sorted(requetes, key=lambda r: r['debut'], reverse=True):
        heure = requete['debut'][11:23]
        titre = f"{heure} · {requete['methode']} {requete['route']} · {requete['statut']} · {requete['duree_ms']:.1f} ms"
        with st.expander(titre):
            st.caption('Identifiant de requête')
            st.code(requete['requete_id'], language=None)
            groupes = operations_console(requete['evenements'])
            appels = [g for g in groupes if g['source'] == 'DAO']
            if appels:
                st.markdown('**Méthodes DAO appelées**')
                for appel in appels:
                    duree = appel['details'].get('duree_ms')
                    st.caption(appel['operation'] + (f' · {duree:.2f} ms' if duree is not None else ''))
            bases = [g for g in groupes if g['source'] in {'MongoDB', 'PostgreSQL', 'pgvector', 'Redis'}]
            for item in bases:
                if item['source'] == 'pgvector' and item['operation'] == 'Paramètres de recherche' and any(
                        g['source'] == 'pgvector' and 'candidats' in g['details'] for g in bases):
                    continue  # Modèle, références et seuil figurent aussi dans les décisions.
                if item['source'] == 'Redis' and 'commandes' not in item['details'] and 'erreur' not in item['details']:
                    continue  # État déjà présent dans le résultat réel du pipeline.
                afficher_operation_console(item)
            if not bases:
                st.caption('Aucun appel aux bases observé pour cette requête.')
            with st.expander('Détails HTTP et DAO'):
                st.json({'methode': requete['methode'], 'route': requete['route'],
                         'statut': requete['statut'], 'duree_ms': requete['duree_ms']}, expanded=True)
                for item in groupes:
                    if item['source'] in {'HTTP', 'DAO', 'Embeddings'}:
                        st.caption(f"{item['source']} · {item['operation']}")
                        st.json(item['details'], expanded=False)
            if requete['evenements_omis']:
                st.caption(f"{requete['evenements_omis']} événements omis : limite de mémoire atteinte.")


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


def cocher(ref, cle, ensemble='cartes_choisies'):
    if st.session_state[cle]:
        st.session_state[ensemble].add(ref)
    else:
        st.session_state[ensemble].discard(ref)


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


def deselectionner_collection():
    for reference in st.session_state.collection_choisies:
        cle = 'suppression-' + reference
        if cle in st.session_state:
            st.session_state[cle] = False
    st.session_state.collection_choisies.clear()


def supprimer_selection(identifiants):
    try:
        resultat = appeler('/collection/exemplaires/supprimer', 'POST', json={'identifiants': identifiants})
        nombre = resultat['supprimes']
        st.session_state.message = f"{nombre} exemplaire{'s' if nombre != 1 else ''} supprimé{'s' if nombre != 1 else ''}."
        deselectionner_collection()
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
                    key=f'{prefixe}-carte-{indice}' if selectionnable or prefixe == 'collection' else None):
                if selectionnable or prefixe == 'collection':
                    ensemble = 'cartes_choisies' if selectionnable else 'collection_choisies'
                    cle = ('choix-' if selectionnable else 'suppression-') + carte['_id']
                    with st.container(horizontal=True, horizontal_alignment='right', gap=None,
                                      key=f'{prefixe}-selection-{indice}'):
                        st.checkbox('Sélectionner ' + carte['nom'],
                                    value=carte['_id'] in st.session_state[ensemble],
                                    key=cle, label_visibility='collapsed',
                                    on_change=cocher, args=(carte['_id'], cle, ensemble))
                if selectionnable:
                    apercu_catalogue(carte)
                else:
                    afficher_image(carte, afficher_langue=prefixe != 'collection')
                    st.markdown('<div class="card-name">' + html.escape(carte['nom']) + '</div>', unsafe_allow_html=True)
                    st.markdown('<div class="card-meta">' + html.escape(carte['extension']) + ' · N° ' + html.escape(carte['numero']) + '</div>', unsafe_allow_html=True)
                    st.markdown(''.join('<span class="pill">' + html.escape(x) + '</span>' for x in [*carte['types'], carte['rarete']]), unsafe_allow_html=True)
                if distances is not None:
                    st.caption(f"N° {indice + 1} · Similarité cosinus : {1 - distances[indice]:.3f}")
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
    else:
        choix = sorted(st.session_state.collection_choisies)
        selection = {'identifiants': [], 'cartes': 0, 'exemplaires': 0}
        if choix and len(choix) <= 200:
            selection = appeler('/collection/selection', 'POST', json={'references': choix})
            resume.caption(f"{selection['cartes']} carte(s) sélectionnée(s) · {selection['exemplaires']} exemplaire(s)")
        nombre = selection['exemplaires']
        libelle = f"Supprimer {nombre} exemplaire{'s' if nombre != 1 else ''}" if nombre else 'Supprimer la sélection'
        action.button(libelle, icon=':material/delete:', type='primary',
                      width='stretch', disabled=not selection['identifiants'] or selection['exemplaires'] > 10000,
                      on_click=supprimer_selection, args=(selection['identifiants'],))
        if choix:
            st.caption('Tous les exemplaires des cartes cochées seront retirés de la collection, y compris sur les autres pages.')
            st.button('Désélectionner', on_click=deselectionner_collection)
        if len(choix) > 200 or selection['exemplaires'] > 10000:
            st.warning('Sélectionnez au maximum 200 cartes et 10 000 exemplaires à la fois.')
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
        st.divider()
        quantite = len(carte['exemplaires'])
        compteur, ajout = st.columns([1, 1], vertical_alignment='center')
        compteur.markdown(f"**{quantite} exemplaire{'s' if quantite != 1 else ''} dans ma collection**")
        ajout.button('Ajouter un exemplaire', type='primary', width='stretch',
                     on_click=ajouter, args=([carte['_id']],))
        for numero, e in enumerate(carte['exemplaires'], 1):
            with st.container(border=True, key='exemplaire-' + e['_id']):
                resume, suppression = st.columns([3, 1], vertical_alignment='center')
                resume.markdown(f'**Exemplaire {numero}**')
                details = [v for v in [e.get('etat'), e.get('variante')] if v]
                if e.get('prix_centimes') is not None:
                    details.append(f"{e['prix_centimes'] / 100:.2f} €".replace('.', ','))
                if details:
                    resume.caption(' · '.join(details))
                suppression.button('Retirer', icon=':material/delete:', key='retirer-' + e['_id'],
                                   help='Retirer uniquement cet exemplaire de la collection',
                                   on_click=retirer, args=(e['_id'],), width='stretch')
                with st.expander('Modifier les informations'):
                    with st.form('informations-' + e['_id'], border=False):
                        champs = st.columns([1, 1, 1])
                        etat = champs[0].text_input('État', value=e.get('etat') or '',
                                                   placeholder='Excellent…', max_chars=40)
                        variante = champs[1].text_input('Variante', value=e.get('variante') or '',
                                                       placeholder='Holo…', max_chars=60)
                        prix = champs[2].number_input('Prix d’achat (€)', min_value=0.0, max_value=99999999.99,
                                                      value=e['prix_centimes'] / 100 if e.get('prix_centimes') is not None else None,
                                                      step=0.01, format='%.2f', placeholder='Non renseigné')
                        if st.form_submit_button('Enregistrer', type='primary'):
                            appeler('/collection/exemplaires/' + e['_id'], 'PATCH',
                                    json={'etat': etat.strip() or None, 'variante': variante.strip() or None, 'prix_achat': prix})
                            st.session_state.message = 'Informations enregistrées.'
                            st.rerun()
        if not carte.get('texte'):
            st.caption('Recherche par sens indisponible pour cette carte.')
        if not st.session_state.historique_disponible:
            st.caption('L’historique est momentanément indisponible. La consultation reste possible.')


for cle, valeur in {'session': str(uuid4()), 'selection': None, 'historique_disponible': True,
                    'cartes_choisies': set(), 'page_catalogue': 1, 'page_collection': 1,
                    'collection_choisies': set(),
                    'console_jeton': secrets.token_hex(32)}.items():
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
    st.toggle('Mode développeur', key='mode_developpeur')

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
        st.caption('Choisissez le top K parmi les cartes dont la similarité atteint au moins 95 % du meilleur score et 0,841. Les résultats sont classés du plus proche au moins proche ; ce score n’est pas une probabilité.')
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
                            st.session_state.resultats = appeler('/recherche', 'POST',
                                                                json={'texte': phrase, 'top_k': None})['resultats']
                        except (requests.RequestException, RuntimeError) as erreur:
                            st.session_state.resultats = []
                            st.warning(str(erreur))
            if st.session_state.get('resultats'):
                maximum = len(st.session_state.resultats)
                st.session_state.top_k_recherche = min(maximum, max(1, st.session_state.get('top_k_recherche', 10)))
                if maximum > 1:
                    top_k = st.slider('Top K — nombre de résultats', min_value=1, max_value=maximum,
                                      step=1, key='top_k_recherche',
                                      help='Le maximum correspond à toutes les cartes qui passent le seuil dynamique. Changer K ne relance pas la recherche.')
                else:
                    top_k = 1
                    st.caption('Top K : 1 — une seule carte passe le seuil dynamique.')
                resultats_affiches = st.session_state.resultats[:top_k]
                seuil = st.session_state.resultats[0].get('seuil_similarite')
                st.caption(f"{top_k} résultat(s) affiché(s) sur {maximum} admissible(s)" +
                           (f" · Seuil dynamique de similarité : {seuil:.3f}" if seuil is not None else ''))
                grille([x['carte'] for x in resultats_affiches], 'semantique',
                       [x['distance'] for x in resultats_affiches],
                       passages=[x.get('passage', '') for x in resultats_affiches])
            elif envoyer and len(phrase.strip()) >= 2:
                st.info('Aucun résultat suffisamment pertinent dans votre collection')
    elif rubrique == 'Dernières consultations':
        st.caption('Vos 10 dernières cartes consultées · Effacées après 30 min d’inactivité')
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

if st.session_state.get('mode_developpeur'):
    console_developpeur()
