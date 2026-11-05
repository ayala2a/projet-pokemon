"""Seuil issu de calibrer_recherche.py, lié à une révision du modèle."""
import json
from functools import lru_cache
from pathlib import Path


class CalibrationAbsente(RuntimeError):
    pass


@lru_cache
def seuil_distance(modele):
    calibration = json.loads(Path(__file__).with_name('seuil_recherche.json').read_text(encoding='utf-8'))
    seuil = calibration['seuil_distance']
    if calibration['modele'] != modele or not 0 < seuil < 2:
        raise CalibrationAbsente('Recalibrer la recherche pour cette révision du modèle.')
    return seuil
