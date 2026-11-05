"""Console éphémère : instrumentation des appels réels, sans journal persistant."""
import hashlib
import inspect
import itertools
import json
import re
from collections import OrderedDict, deque
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from threading import RLock
from time import monotonic, perf_counter
from uuid import UUID, uuid4

import psycopg
from pymongo.monitoring import CommandListener

_requete = ContextVar('trace_requete', default=None)
_dao = ContextVar('trace_dao', default=None)
_ordre = itertools.count(1)
_verrou = RLock()
_sessions = OrderedDict()
_secret = re.compile(r'password|passwd|secret|token|authorization|cookie|api[_-]?key|^dsn$|^uri$', re.I)


def nettoyer(valeur, profondeur=0):
    """Copie JSON bornée ; aucun objet connexion, en-tête ou vecteur complet."""
    if profondeur > 9:
        return '…'
    if valeur is None or isinstance(valeur, (bool, int, float)):
        return valeur
    if hasattr(valeur, 'shape') and hasattr(valeur, 'ravel'):
        plat = valeur.ravel()
        return {'forme': list(valeur.shape), 'dimension': int(plat.size),
                'extrait': [round(float(x), 6) for x in plat[:4]], 'abrege': True}
    if isinstance(valeur, dict):
        resultat = {str(k): '[masqué]' if _secret.search(str(k)) else nettoyer(v, profondeur + 1)
                    for k, v in list(valeur.items())[:50]}
        if len(valeur) > 50:
            resultat['champs_omis'] = len(valeur) - 50
        return resultat
    if isinstance(valeur, (list, tuple)):
        if len(valeur) > 32 and all(isinstance(x, (float, int)) for x in valeur):
            return {'dimension': len(valeur), 'extrait': list(valeur[:4]), 'abrege': True}
        extrait = [nettoyer(x, profondeur + 1) for x in valeur[:25]]
        return extrait if len(valeur) <= 25 else {'total': len(valeur), 'extrait': extrait, 'omis': len(valeur) - 25}
    texte = str(valeur)
    texte = re.sub(r'([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@', r'\1[masqué]@', texte, flags=re.I)
    texte = re.sub(r'(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[=:]\s*)[^\s,;]+', r'\1[masqué]', texte)
    texte = re.sub(r'(?i)Bearer\s+\S+|gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,}', '[masqué]', texte)
    return texte[:4000] + ('…' if len(texte) > 4000 else '')


def active():
    return _requete.get() is not None


def evenement(source, operation, *, trace=None, **details):
    trace = trace if trace is not None else _requete.get()
    if trace is None:
        return
    # Une panne de la console ne doit jamais faire échouer une action métier.
    try:
        item = {'ordre': next(_ordre), 'heure': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                'source': source, 'operation': operation, 'dao': _dao.get(), 'details': nettoyer(details)}
        poids = len(json.dumps(item, ensure_ascii=False).encode('utf-8'))
        with _verrou:
            if len(trace['evenements']) < 160 and trace['_octets'] + poids <= 128_000:
                trace['evenements'].append(item)
                trace['_octets'] += poids
            else:
                trace['evenements_omis'] += 1
    except Exception:
        pass


def identite(session, jeton):
    try:
        session = str(UUID(session or ''))
    except (ValueError, TypeError, AttributeError):
        return None
    if not re.fullmatch(r'[a-f0-9]{64}', jeton or ''):
        return None
    return hashlib.sha256((session + ':' + jeton).encode()).hexdigest()


def commencer(methode, route, parametres):
    trace = {'requete_id': str(uuid4()), 'methode': methode, 'route': route,
             'debut': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
             'statut': None, 'duree_ms': None, 'evenements': [], 'evenements_omis': 0, '_octets': 0}
    jeton = _requete.set(trace)
    evenement('HTTP', 'Début', parametres=parametres)
    return trace, jeton, perf_counter()


def terminer(cle, trace, jeton, debut, statut):
    trace['statut'] = statut
    trace['duree_ms'] = round((perf_counter() - debut) * 1000, 2)
    evenement('HTTP', 'Fin', statut=statut, duree_ms=trace['duree_ms'])
    trace['evenements'].sort(key=lambda x: x['ordre'])
    _requete.reset(jeton)
    with _verrou:
        _purger()
        _, anciens = _sessions.pop(cle, (0, deque()))
        anciens.append(trace)
        # Les images ne doivent pas chasser les opérations métier de la console.
        for images, limite in [(True, 12), (False, 40)]:
            concernes = [x for x in anciens if x['route'].startswith('/images/') == images]
            for ancien in concernes[:-limite]:
                anciens.remove(ancien)
        # Au plus 1 Mo par session et 16 sessions : mémoire bornée.
        while sum(x['_octets'] for x in anciens) > 1_000_000:
            anciens.popleft()
        _sessions[cle] = (monotonic(), anciens)
        while len(_sessions) > 16:
            _sessions.popitem(last=False)


def _purger():
    for cle, (date, _) in list(_sessions.items()):
        if monotonic() - date > 1800:
            del _sessions[cle]


def consulter(cle, inclure_images=False):
    with _verrou:
        _purger()
        _, traces = _sessions.get(cle, (0, []))
        return [{k: v for k, v in x.items() if not k.startswith('_')}
                for x in sorted(traces, key=lambda x: x['debut'], reverse=True)
                if inclure_images or not x['route'].startswith('/images/')]


def effacer(cle):
    with _verrou:
        _sessions.pop(cle, None)


def tracer_dao(classe):
    def decorer(fonction):
        signature = inspect.signature(fonction)
        @wraps(fonction)
        def appel(self, *args, **kwargs):
            if not active():
                return fonction(self, *args, **kwargs)
            nom = type(self).__name__ + '.' + fonction.__name__
            appel_id = str(uuid4())
            jeton = _dao.set(nom)
            debut = perf_counter()
            try:
                arguments = dict(signature.bind(self, *args, **kwargs).arguments)
                arguments.pop('self', None)
                evenement('DAO', nom, phase='début', appel_id=appel_id, arguments=arguments)
                resultat = fonction(self, *args, **kwargs)
                evenement('DAO', nom, phase='fin', appel_id=appel_id,
                          duree_ms=round((perf_counter()-debut)*1000, 2), resultat=resultat)
                return resultat
            except Exception as erreur:
                evenement('DAO', nom, phase='erreur', appel_id=appel_id,
                          duree_ms=round((perf_counter()-debut)*1000, 2), erreur=type(erreur).__name__, message=str(erreur))
                raise
            finally:
                _dao.reset(jeton)
        return appel
    for nom, fonction in list(vars(classe).items()):
        if not nom.startswith('_') and inspect.isfunction(fonction):
            setattr(classe, nom, decorer(fonction))
    return classe


class EcouteMongo(CommandListener):
    def __init__(self):
        self.attente = {}
        self.verrou = RLock()

    def started(self, event):
        trace = _requete.get()
        if trace is None:
            return
        operation_id = str(uuid4())
        with self.verrou:
            self.attente[(event.connection_id, event.request_id)] = (trace, _dao.get(), operation_id)
        evenement('MongoDB', event.command_name, phase='début', base=event.database_name,
                  operation_id=operation_id,
                  commande=dict(event.command), writeConcern=event.command.get('writeConcern',
                  'Non transmis : défaut serveur (lecture ou commande sans writeConcern explicite)'))

    def _fin(self, event, **details):
        with self.verrou:
            trace_dao = self.attente.pop((event.connection_id, event.request_id), None)
        if trace_dao:
            trace, dao, operation_id = trace_dao
            evenement('MongoDB', event.command_name, trace=trace, phase='fin', methode_dao=dao,
                      operation_id=operation_id,
                      duree_ms=round(event.duration_micros/1000, 2), **details)

    def succeeded(self, event):
        self._fin(event, resultat=dict(event.reply))

    def failed(self, event):
        self._fin(event, erreur=event.failure)


class CurseurTrace(psycopg.Cursor):
    def execute(self, query, params=None, *args, **kwargs):
        if not active():
            return super().execute(query, params, *args, **kwargs)
        debut = perf_counter()
        self._trace_operation = str(uuid4())
        self._trace_debut = debut
        evenement('PostgreSQL', 'SQL paramétré', operation_id=self._trace_operation, sql=str(query), parametres=params)
        try:
            resultat = super().execute(query, params, *args, **kwargs)
            evenement('PostgreSQL', 'SQL exécuté', statut=self.statusmessage, lignes=self.rowcount,
                      operation_id=self._trace_operation,
                      duree_ms=round((perf_counter()-debut)*1000, 2))
            return resultat
        except Exception as erreur:
            evenement('PostgreSQL', 'Erreur SQL', operation_id=self._trace_operation,
                      duree_ms=round((perf_counter()-debut)*1000, 2), erreur=type(erreur).__name__, message=str(erreur))
            raise

    def fetchall(self):
        resultat = super().fetchall()
        if active():
            debut = getattr(self, '_trace_debut', None)
            evenement('PostgreSQL', 'Résultats', operation_id=getattr(self, '_trace_operation', None),
                      duree_ms=round((perf_counter()-debut)*1000, 2) if debut is not None else None,
                      lignes=len(resultat), resultat=resultat)
        return resultat

    def fetchone(self):
        resultat = super().fetchone()
        if active():
            debut = getattr(self, '_trace_debut', None)
            evenement('PostgreSQL', 'Résultat', operation_id=getattr(self, '_trace_operation', None),
                      duree_ms=round((perf_counter()-debut)*1000, 2) if debut is not None else None, resultat=resultat)
        return resultat


def executer_redis(pipe, cle):
    commandes = [list(arguments) for arguments, _ in pipe.command_stack] if active() else None
    debut = perf_counter()
    try:
        resultat = pipe.execute()
        etat = {}
        if commandes is not None:
            for commande, valeur in zip(commandes, resultat):
                nom = commande[0].decode() if isinstance(commande[0], bytes) else str(commande[0])
                if nom.upper() in {'LRANGE', 'LLEN', 'TTL'}:
                    etat[{'LRANGE': 'contenu_liste', 'LLEN': 'longueur', 'TTL': 'ttl_secondes'}[nom.upper()]] = valeur
        evenement('Redis', 'MULTI / EXEC' if pipe.transaction else 'Pipeline', cle=cle,
                  commandes=commandes, resultats=resultat, duree_ms=round((perf_counter()-debut)*1000, 2), **etat)
        return resultat
    except Exception as erreur:
        evenement('Redis', 'Erreur', cle=cle, commandes=commandes, erreur=type(erreur).__name__, message=str(erreur))
        raise


def lire_liste_redis(client, cle):
    if not active():
        return client.lrange(cle, 0, 9)
    debut = perf_counter()
    try:
        references = client.lrange(cle, 0, 9)
        evenement('Redis', 'LRANGE', cle=cle, commandes=[['LRANGE', cle, 0, 9]],
                  contenu_liste=references, resultat=references, duree_ms=round((perf_counter()-debut)*1000, 2))
        return references
    except Exception as erreur:
        evenement('Redis', 'Erreur LRANGE', cle=cle, commandes=[['LRANGE', cle, 0, 9]],
                  duree_ms=round((perf_counter()-debut)*1000, 2), erreur=type(erreur).__name__, message=str(erreur))
        raise
