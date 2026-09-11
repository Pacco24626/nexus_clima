"""Prove a tavolino della modulazione a soglie (comfort / eco).

Gli scenari sono quelli della classica automazione comfort/eco, piu' i casi
che l'automazione non gestiva: il ping-pong, il clima riacceso a meta'
prelievo, l'utente che cambia idea durante l'eco, due zone che tornano al
comfort insieme, il riavvio. Per ciascuno si guarda quali comandi arrivano
davvero ai climatizzatori.

    python tests/test_soglie.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import finto_ha  # noqa: E402
from finto_ha import OROLOGIO, Entry, Esiti, cedi, dormi, nuovo_impianto  # noqa: E402

from nexus_clima import const, controller as modulo_controller  # noqa: E402
from nexus_clima import gestore_aperture, gestore_soglie  # noqa: E402
from nexus_clima.controller import ClimaController  # noqa: E402
from nexus_clima.soglie import candidato, comandi_eco, soglia_ritorno  # noqa: E402

for modulo in (modulo_controller, gestore_aperture, gestore_soglie):
    modulo.asyncio = types.SimpleNamespace(sleep=dormi)  # type: ignore[attr-defined]

CAMERA = "climate.clima_camera"
SALOTTO = "climate.clima_salotto"
RETE = "sensor.rete"
FINESTRA = "binary_sensor.finestra_camera"

esiti = Esiti("SOGLIE")
v = esiti.verifica


def clima(hass, entity_id, stato="cool", temperatura=22, ventola="3"):
    hass.imposta(
        entity_id, stato,
        temperature=temperatura if stato != "off" else None,
        current_temperature=25,
        hvac_modes=["off", "cool", "heat", "fan_only"],
        fan_modes=["Auto", "Silence", "1", "2", "3", "4", "5"], fan_mode=ventola,
        friendly_name=entity_id.split(".")[1].replace("_", " ").title(),
    )
    hass.memoria_clima[entity_id] = temperatura


def zona(hass, climi, entry_id="camera", **opzioni):
    dati = {
        const.CONF_NOME: entry_id,
        const.CONF_CLIMI: climi,
        const.CONF_SENSORE_RETE: RETE,
        const.CONF_RETE_POSITIVA_IMPORT: True,  # qui positivo = prelievo
        const.CONF_MODALITA: const.MODALITA_SOGLIE,
    }
    dati.update(opzioni)
    return ClimaController(hass, Entry(dati, entry_id=entry_id, title=entry_id))


async def impianto(stato="cool", temperatura=22, rete=0, **opzioni):
    finto_ha.azzera_memoria()
    hass = nuovo_impianto()
    hass.imposta(RETE, str(rete))
    clima(hass, CAMERA, stato, temperatura)
    c = zona(hass, [CAMERA], **opzioni)
    await c.async_setup()
    await cedi()
    hass.services.chiamate.clear()
    return hass, c


async def minuti(hass, controllori, quanti):
    """Fa passare il tempo con il ciclo di valutazione ogni 30 secondi."""
    if not isinstance(controllori, (list, tuple)):
        controllori = [controllori]
    for _ in range(int(quanti * 2)):
        await hass.avanza(30)
        for c in controllori:
            await c._async_ciclo()
        await cedi()


def comandi(hass, entity_id=None):
    return [(servizio, {k: w for k, w in dati.items() if k != "entity_id"})
            for _, servizio, dati in hass.services.chiamate
            if entity_id is None or dati.get("entity_id") == entity_id]


def stato_clima(hass, entity_id=CAMERA):
    s = hass.states.get(entity_id)
    return s.state, s.attributes.get("temperature"), s.attributes.get("fan_mode")


ECO = [("set_temperature", {"temperature": 25.0}), ("set_fan_mode", {"fan_mode": "Auto"})]
COMFORT = [("set_temperature", {"temperature": 22.0}), ("set_fan_mode", {"fan_mode": "3"})]


async def scenari():
    # --- 1. prelievo: eco dopo il tempo, non prima ---------------------------
    hass, c = await impianto()
    hass.imposta(RETE, "400")
    await minuti(hass, c, 7.5)
    v("prelievo da 7,5 min: ancora comfort", comandi(hass) == [], comandi(hass))
    await minuti(hass, c, 1)
    v("prelievo da 8 min: eco a 25 °C e ventola Auto", comandi(hass) == ECO, comandi(hass))
    v("lo stato dice eco", c.stato == const.STATO_ECO, c.motivo)
    v("il comfort da rimettere e' quello dell'utente",
      c.soglie.eco[CAMERA].comfort_temp == 22 and c.soglie.eco[CAMERA].comfort_ventola == "3")

    # --- 2. il comando nostro non e' dell'utente ------------------------------
    v("il cambio a 25 fatto da noi non fa uscire dall'eco", CAMERA in c.soglie.eco)

    # --- 3. la correzione anti ping-pong --------------------------------------
    hass.services.chiamate.clear()
    hass.imposta(RETE, "-700")  # cedi 700: sopra 500, ma non sopra 500 + 600
    await minuti(hass, c, 30)
    v("cedi 700 W per 30 min: resta in eco (servono 1100)", comandi(hass) == [], c.motivo)
    hass.imposta(RETE, "-1200")
    await minuti(hass, c, 11.5)
    v("cedi 1200 W da 11,5 min: ancora eco", comandi(hass) == [], comandi(hass))
    await minuti(hass, c, 1)
    v("cedi 1200 W da 12 min: comfort rimesso com'era", comandi(hass) == COMFORT, comandi(hass))
    v("stato finale 22 °C ventola 3", stato_clima(hass) == ("cool", 22.0, "3"), stato_clima(hass))

    # --- 4. controllo: senza correzione torna a 600 W ---------------------------
    hass, c = await impianto(**{const.CONF_CONSUMO_IN_PIU: 0})
    hass.imposta(RETE, "400")
    await minuti(hass, c, 8.5)
    hass.services.chiamate.clear()
    hass.imposta(RETE, "-600")
    await minuti(hass, c, 12.5)
    v("controllo: con correzione a zero basta superare 500 W",
      comandi(hass) == COMFORT, comandi(hass))

    # --- 5. il conteggio riparte a ogni interruzione ----------------------------
    hass, c = await impianto()
    hass.imposta(RETE, "400")
    await minuti(hass, c, 5)
    hass.imposta(RETE, "200")
    await minuti(hass, c, 0.5)
    hass.imposta(RETE, "400")
    await minuti(hass, c, 7.5)
    v("prelievo interrotto: il conteggio riparte", comandi(hass) == [], comandi(hass))
    await minuti(hass, c, 1)
    v("e l'eco arriva 8 min dopo la ripresa", comandi(hass) == ECO, comandi(hass))

    # --- 6. clima gia' all'eco o sopra: non si tocca ----------------------------
    for temperatura in (25, 26):
        hass, c = await impianto(temperatura=temperatura)
        hass.imposta(RETE, "900")
        await minuti(hass, c, 60)
        v(f"clima a {temperatura} °C: mai toccato", comandi(hass) == [], comandi(hass))

    # --- 7. mai accendere, mai spegnere ------------------------------------------
    hass, c = await impianto(stato="off")
    hass.imposta(RETE, "900")
    await minuti(hass, c, 30)
    hass.imposta(RETE, "-3000")
    await minuti(hass, c, 30)
    v("clima spento: nessun comando, ne' in prelievo ne' in cessione",
      comandi(hass) == [] and stato_clima(hass)[0] == "off", comandi(hass))

    hass, c = await impianto(stato="heat")
    hass.imposta(RETE, "900")
    await minuti(hass, c, 30)
    v("in riscaldamento: non si tocca", comandi(hass) == [], comandi(hass))

    # --- 8. l'utente cambia idea durante l'eco --------------------------------
    hass, c = await impianto()
    hass.imposta(RETE, "400")
    await minuti(hass, c, 8.5)
    await minuti(hass, c, 5)  # oltre la tolleranza dei nostri comandi
    hass.services.chiamate.clear()
    hass.imposta(CAMERA, "cool", temperature=23)  # dal telecomando
    await minuti(hass, c, 1)
    v("setpoint cambiato durante l'eco: esce dall'eco senza comandi",
      CAMERA not in c.soglie.eco and comandi(hass) == [], comandi(hass))
    await minuti(hass, c, 7.5)
    # La ventola e' rimasta Auto dall'eco di prima: si manda solo il setpoint.
    v("e l'eco torna solo dopo un altro prelievo intero",
      comandi(hass) == [("set_temperature", {"temperature": 25.0})]
      and c.soglie.eco[CAMERA].comfort_temp == 23, comandi(hass))

    # --- 9. spento durante l'eco: resta spento ---------------------------------
    hass, c = await impianto()
    hass.imposta(RETE, "400")
    await minuti(hass, c, 8.5)
    await minuti(hass, c, 5)
    hass.services.chiamate.clear()
    hass.imposta(CAMERA, "off", temperature=None)
    hass.imposta(RETE, "-3000")
    await minuti(hass, c, 30)
    v("spento durante l'eco: nessuna riaccensione", comandi(hass) == [] and stato_clima(hass)[0] == "off")

    # --- 10. acceso a meta' di un prelievo lungo -----------------------------------
    hass, c = await impianto(stato="off")
    hass.imposta(RETE, "400")
    await minuti(hass, c, 60)
    clima(hass, CAMERA, "cool", 22)
    await minuti(hass, c, 7.5)
    v("acceso con la casa che preleva da un'ora: 8 min di comfort prima",
      comandi(hass) == [], comandi(hass))
    await minuti(hass, c, 1)
    v("poi eco", comandi(hass) == ECO, comandi(hass))

    # --- 11. fuori fascia e fine fascia -----------------------------------------
    hass, c = await impianto(**{const.CONF_ATTIVA_DA: "13:00:00", const.CONF_ATTIVA_A: "14:00:00"})
    hass.imposta(RETE, "900")
    await minuti(hass, c, 30)
    v("fuori fascia: niente", comandi(hass) == [] and c.stato == const.STATO_FUORI, c.motivo)
    await minuti(hass, c, 40)  # 13:10: in fascia da 10 min, prelievo da 70
    v("in fascia: eco", comandi(hass) == ECO, comandi(hass))
    hass.services.chiamate.clear()
    await minuti(hass, c, 55)  # 14:05
    v("a fine fascia chi e' in eco resta com'e'", comandi(hass) == [] and not c.soglie.eco)
    hass.imposta(RETE, "-3000")
    await minuti(hass, c, 30)
    v("e dopo la fascia la cessione non lo tocca", comandi(hass) == [], comandi(hass))

    # --- 12. modulazione spenta durante l'eco ------------------------------------
    hass, c = await impianto()
    hass.imposta(RETE, "400")
    await minuti(hass, c, 8.5)
    hass.services.chiamate.clear()
    c.set_abilitato(False)
    await cedi(20)
    v("modulazione spenta: torna il comfort dell'utente", comandi(hass) == COMFORT, comandi(hass))

    # --- 13. riavvio durante l'eco ---------------------------------------------------
    hass, c = await impianto()
    hass.imposta(RETE, "400")
    await minuti(hass, c, 8.5)
    await c.async_shutdown()
    c2 = zona(hass, [CAMERA])
    await c2.async_setup()
    v("l'eco sopravvive al riavvio", CAMERA in c2.soglie.eco)
    hass.services.chiamate.clear()
    hass.imposta(RETE, "-1500")
    await minuti(hass, c2, 12.5)
    v("e alla cessione torna il comfort di prima del riavvio",
      comandi(hass) == COMFORT, comandi(hass))

    hass, c = await impianto()
    hass.imposta(RETE, "400")
    await minuti(hass, c, 8.5)
    await c.async_shutdown()
    hass.states.mappa[CAMERA] = finto_ha.Stato(
        CAMERA, "cool", {**hass.states.get(CAMERA).attributes, "temperature": 21})
    c2 = zona(hass, [CAMERA])
    await c2.async_setup()
    v("cambiato a mano a HA fermo: l'eco salvato non vale piu'", CAMERA not in c2.soglie.eco)

    # --- 14. due zone tornano al comfort una alla volta ------------------------------
    finto_ha.azzera_memoria()
    hass = nuovo_impianto()
    hass.imposta(RETE, "400")
    clima(hass, CAMERA, "cool", 22)
    clima(hass, SALOTTO, "cool", 23)
    a = zona(hass, [CAMERA], entry_id="camera")
    b = zona(hass, [SALOTTO], entry_id="salotto")
    await a.async_setup()
    await b.async_setup()
    await minuti(hass, [a, b], 8.5)
    v("due zone in eco", CAMERA in a.soglie.eco and SALOTTO in b.soglie.eco)
    hass.services.chiamate.clear()
    hass.imposta(RETE, "-3000")
    await minuti(hass, [a, b], 12.5)
    prima = comandi(hass)
    v("con tanta cessione ne torna una sola", len({(s, str(d)) for s, d in prima}) == 2
      and (bool(comandi(hass, CAMERA)) != bool(comandi(hass, SALOTTO))), prima)
    await minuti(hass, [a, b], 12.5)
    v("l'altra dopo un altro tempo di cessione",
      bool(comandi(hass, CAMERA)) and bool(comandi(hass, SALOTTO)), comandi(hass))

    # --- 15. finestra aperta durante l'eco ---------------------------------------------
    finto_ha.azzera_memoria()
    hass = nuovo_impianto()
    hass.imposta(RETE, "400")
    hass.imposta(FINESTRA, "off")
    clima(hass, CAMERA, "cool", 22)
    c = zona(hass, [CAMERA], **{const.CONF_APERTURE: {CAMERA: [FINESTRA]},
                                const.CONF_RITARDO_APERTURA: 60, const.CONF_RITARDO_CHIUSURA: 30})
    await c.async_setup()
    await minuti(hass, c, 8.5)
    hass.services.chiamate.clear()
    hass.imposta(FINESTRA, "on")
    await minuti(hass, c, 2)
    v("finestra aperta durante l'eco: pausa", c.aperture.in_pausa(CAMERA) and CAMERA in c.soglie.eco)
    hass.imposta(FINESTRA, "off")
    await minuti(hass, c, 1)
    v("richiusa: torna com'era, cioe' in eco", stato_clima(hass)[:2] == ("cool", 25.0)
      and CAMERA in c.soglie.eco, (stato_clima(hass), comandi(hass)))
    hass.services.chiamate.clear()
    hass.imposta(RETE, "-1500")
    await minuti(hass, c, 12.5)
    v("e alla cessione torna al comfort vero, 22 e ventola 3",
      comandi(hass) == COMFORT, comandi(hass))


def prove_pure():
    v("candidato: raffresca sotto l'eco", candidato("cool", {"temperature": 22}, 25))
    v("non candidato: gia' all'eco", not candidato("cool", {"temperature": 25}, 25))
    v("non candidato: spento", not candidato("off", {"temperature": 22}, 25))
    v("soglia di ritorno con due clima", soglia_ritorno(500, 600, 2) == 1700)
    v("ventola sconosciuta: non si manda",
      comandi_eco({"temperature": 22, "fan_modes": ["1"], "fan_mode": "1"}, 25, "Auto")
      == [("set_temperature", {"temperature": 25})])


asyncio.run(scenari())
prove_pure()
esiti.chiudi()
