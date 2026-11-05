"""Normalisation partagée par l'import et les tests, sans accès aux bases."""
import re
from urllib.parse import unquote


def nettoyer(valeur):
    return re.sub(r'\s+', ' ', valeur).strip() if isinstance(valeur, str) else ''


def centrer_requete(texte):
    """Retirer les introductions génériques qui dominent sinon les courts effets.

    Les mots décrivant le besoin sont conservés ; pas de dictionnaire de réponses
    ou de reclassement lexical après la distance cosinus.
    """
    texte = nettoyer(texte)
    cible = re.sub(r'^(?:je cherche|je recherche|montre-moi|trouve-moi)\s+', '', texte, flags=re.I)
    cible = re.sub(r'^(?:un|une|des|les|mes)\s+(?:pokémon|pokemon|cartes?)\s+(?:qui\s+)?',
                   '', cible, flags=re.I)
    return cible.strip() if len(cible.strip()) >= 2 else texte


def texte_recherche(carte):
    description = nettoyer(carte.get('description'))
    effets = [nettoyer(item.get('effect')) for famille in ('attacks', 'abilities')
              for item in (carte.get(famille) or []) if isinstance(item, dict)]
    # Un nom ou un type seuls ne constituent pas un texte sémantique utile.
    if not any([description, *effets]):
        return ''
    parties = [nettoyer(carte.get('name')), 'Types : ' + ', '.join(carte.get('types') or []), description]
    for famille in ('abilities', 'attacks'):
        for item in carte.get(famille) or []:
            parties.append(' '.join(filter(None, [nettoyer(item.get('name')), nettoyer(item.get('effect'))])))
    return '\n'.join(p for p in parties if p)


def normaliser(carte):
    extension = carte.get('set') or {}
    return {
        '_id': 'fr:' + carte['id'], 'id': carte['id'], 'nom': carte['name'],
        'numero': unquote(str(carte.get('localId', ''))), 'categorie': carte.get('category', ''),
        'extension_id': extension.get('id', ''), 'extension': extension.get('name', 'Inconnue'),
        'bloc_id': (extension.get('serie') or {}).get('id', 'inconnu'),
        'bloc': (extension.get('serie') or {}).get('name', 'Non renseigné'),
        'rarete': carte.get('rarity') or 'Non renseignée', 'types': carte.get('types') or [],
        'description': nettoyer(carte.get('description')), 'pv': carte.get('hp'),
        'attaques': carte.get('attacks') or [], 'capacites': carte.get('abilities') or [],
        'image_source': carte.get('image'), 'texte': texte_recherche(carte),
        'variantes': [label for champ, label in [('normal', 'Normale'), ('holo', 'Holo'),
                                                ('reverse', 'Reverse')]
                      if (carte.get('variants') or {}).get(champ)] or ['Normale'],
    }


def passages_recherche(carte):
    """Éviter qu'un effet court soit noyé dans toute la fiche de la carte."""
    if not carte.get('texte'):
        return []
    nom = carte['nom']
    passages = [nom + '. Types : ' + ', '.join(carte.get('types') or [])]
    if nettoyer(carte.get('description')):
        passages.append(nom + '. ' + nettoyer(carte['description']))
    for famille in ['capacites', 'attaques']:
        for element in carte.get(famille) or []:
            effet = nettoyer(element.get('effect'))
            if effet:
                passages.append(nom + '. ' + nettoyer(element.get('name')) + ' : ' + effet)
    return list(dict.fromkeys(passages))
