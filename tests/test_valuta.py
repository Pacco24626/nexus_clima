"""Prove a tavolino della decisione di modulazione (valuta()).

valuta() e' pura: stessi ingressi, stessa uscita, nessun effetto. Qui si
verificano i vincoli che la reggono — il compressore non si ferma per colpa
nostra, il surplus non si muove quando agiamo, l'utente vince.

    python tests/test_valuta.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from finto_ha import Entry, Esiti, nuovo_impianto  # noqa: E402

from nexus_clima import const  # noqa: E402
from nexus_clima.controller import ClimaController  # noqa: E402

CLIMA = "climate.camera"


def costruisci(rete_w, temp, setpoint, stati=None, **extra):
    """rete_w positivo = si preleva dalla rete."""
    hass = nuovo_impianto()
    hass.imposta(CLIMA, "cool", temperature=setpoint, current_temperature=temp,
                 fan_modes=["Auto", "1", "5"], fan_mode="Auto")
    hass.imposta("sensor.rete", str(rete_w))
    for entity_id, (stato, attributi) in (stati or {}).items():
        hass.imposta(entity_id, stato, **attributi)
    dati = {
        const.CONF_NOME: "Zona notte",
        const.CONF_CLIMI: [CLIMA],
        const.CONF_SENSORE_RETE: "sensor.rete",
        const.CONF_RETE_POSITIVA_IMPORT: True,
        const.CONF_T_MIN: 22.0,
        const.CONF_T_COMFORT: 25.0,
        const.CONF_T_MAX: 26.0,
        const.CONF_P_A_T_MIN: 900,
        const.CONF_P_A_T_MAX: 300,
        const.CONF_CARICA_DA: "10:00:00",
        const.CONF_CARICA_A: "17:00:00",
        const.CONF_COMFORT_DA: "22:00:00",
        const.CONF_COMFORT_A: "07:00:00",
    }
    dati.update(extra)
    return ClimaController(hass, Entry(dati, title="Zona notte"))


MEZZOGIORNO = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
SERA = datetime(2026, 9, 8, 23, 0, tzinfo=timezone.utc)
POMERIGGIO = datetime(2026, 9, 8, 19, 0, tzinfo=timezone.utc)

esiti = Esiti("VALUTA")
v = esiti.verifica

# 1. Nessun surplus: si sta al massimo.
c = costruisci(rete_w=800, temp=26.0, setpoint=26)
d = c.valuta(MEZZOGIORNO)
v("nessun surplus -> massimo", d.setpoint == 26, f"{d.stato} {d.setpoint} {c.surplus}")

# 2. Surplus pieno in carica: scende, ma di un passo alla volta.
c = costruisci(rete_w=-900, temp=26.0, setpoint=26)
d = c.valuta(MEZZOGIORNO)
v("surplus pieno -> scende di un passo", d.setpoint == 25, f"{d.setpoint} {d.motivo}")

# 3. Il compressore non si ferma mai: setpoint mai sotto temperatura - 1.
c = costruisci(rete_w=-3000, temp=24.0, setpoint=24)
d = c.valuta(MEZZOGIORNO)
v("mai sotto temperatura-1", d.setpoint >= 23, f"{d.setpoint}")

# 4. Fuori dalle fasce non si tocca nulla.
c = costruisci(rete_w=-2000, temp=25.0, setpoint=25)
d = c.valuta(POMERIGGIO)
v("fuori fascia", d.stato == const.STATO_FUORI and d.setpoint is None, d.stato)

# 5. In comfort non scende sotto il minimo di comfort.
c = costruisci(rete_w=-3000, temp=25.0, setpoint=25)
d = c.valuta(SERA)
v("comfort si ferma a 25", d.stato == const.STATO_COMFORT and d.setpoint >= 25, f"{d.setpoint}")

# 6. Cancello del pavimento: appreso 23,4 e temperatura li', non si scende.
c = costruisci(rete_w=-3000, temp=23.4, setpoint=23)
c.pavimento = 23.4
c.pavimento_campioni = 5
d = c.valuta(MEZZOGIORNO)
v("pavimento appreso frena", d.setpoint >= 23, f"{d.setpoint} {d.motivo}")

# 7. Permanenza minima: cambio appena fatto, resta fermo.
c = costruisci(rete_w=-3000, temp=26.0, setpoint=26)
c._ultimo_cambio = MEZZOGIORNO - timedelta(minutes=5)
d = c.valuta(MEZZOGIORNO)
v("permanenza minima", d.setpoint == 26 and "permanenza" in d.motivo, d.motivo)

# 8. Comando manuale: si mette da parte.
c = costruisci(rete_w=-3000, temp=26.0, setpoint=26)
c._manuale_fino = MEZZOGIORNO + timedelta(minutes=60)
d = c.valuta(MEZZOGIORNO)
v("comando manuale", d.stato == const.STATO_MANUALE, d.motivo)

# 9. Zona accoppiata piu' fredda: allineamento.
senza = costruisci(rete_w=-3000, temp=24.0, setpoint=24).valuta(MEZZOGIORNO).setpoint
c = costruisci(rete_w=-3000, temp=24.0, setpoint=24,
               stati={"climate.salotto": ("cool", {"temperature": 25, "current_temperature": 25})})
c.accoppiate = ["climate.salotto"]
d = c.valuta(MEZZOGIORNO)
v("accoppiamento alza il minimo", d.setpoint == 24 and senza == 23, f"{senza} -> {d.setpoint}")

# 10. Il surplus e' invariante: accendere non lo cambia.
c1 = costruisci(rete_w=-900, temp=26.0, setpoint=26)   # clima al massimo, 300 W
c1.valuta(MEZZOGIORNO)
c2 = costruisci(rete_w=-300, temp=26.0, setpoint=22)   # clima al minimo, 900 W
c2.valuta(MEZZOGIORNO)
v("surplus invariante", abs(c1.surplus - c2.surplus) < 1, f"{c1.surplus:.0f} / {c2.surplus:.0f}")

# 11. Sensore di rete assente: non si comanda.
c = costruisci(rete_w=-3000, temp=26.0, setpoint=26)
c.sensore_rete = "sensor.inesistente"
d = c.valuta(MEZZOGIORNO)
v("sensore mancante", d.stato == const.STATO_NON_PRONTO and d.setpoint is None, d.motivo)

# 12. Modulazione disattivata dall'interruttore.
c = costruisci(rete_w=-3000, temp=26.0, setpoint=26)
c.set_abilitato(False)
d = c.valuta(MEZZOGIORNO)
v("modulazione disattivata", d.stato == const.STATO_DISABILITATO and d.setpoint is None, d.motivo)

esiti.chiudi()
