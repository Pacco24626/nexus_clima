"""Prove a tavolino della pausa per porte e finestre aperte.

Gli scenari sono quelli di tutti i giorni in una casa: la porta attraversata,
la finestra aperta per arieggiare, chi riaccende il clima con la finestra
aperta, chi esce e non vuole trovarlo acceso al rientro, il gateway
dell'allarme che si riavvia. Per ciascuno si guarda quali comandi arrivano
davvero al climatizzatore.

    python tests/test_aperture.py
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import types  # noqa: E402

import finto_ha  # noqa: E402  (prima di tutto: inietta i moduli finti)
from finto_ha import Entry, Esiti, cedi, dormi, nuovo_impianto  # noqa: E402

from nexus_clima import const, controller as modulo_controller, gestore_aperture  # noqa: E402
from nexus_clima.aperture import (  # noqa: E402
    CHIUSA,
    IGNOTA,
    APERTA,
    Pausa,
    comandi_ripristino,
    decidi_ripristino,
    stato_aperture,
)
from nexus_clima.controller import ClimaController  # noqa: E402

# Le attese fra un comando e l'altro passano sull'orologio finto. Si sostituisce
# il nome nei due moduli, non asyncio.sleep: quello serve ancora al ciclo.
gestore_aperture.asyncio = types.SimpleNamespace(sleep=dormi)  # type: ignore[assignment]
modulo_controller.asyncio = types.SimpleNamespace(sleep=dormi)  # type: ignore[assignment]

CLIMA = "climate.clima_salotto"
PORTA = "binary_sensor.porta_ingresso"
FINESTRA = "binary_sensor.finestra_cucina"

esiti = Esiti("APERTURE")
v = esiti.verifica


def impianto(stato_clima="cool", **opzioni):
    # Ogni scenario parte da una casa nuova: niente pause ereditate.
    finto_ha.azzera_memoria()
    hass = nuovo_impianto()
    hass.imposta(PORTA, "off")
    hass.imposta(FINESTRA, "off")
    hass.imposta(
        CLIMA, stato_clima,
        temperature=24 if stato_clima != "off" else None,
        current_temperature=26.5,
        hvac_modes=["off", "cool", "heat", "dry", "fan_only", "auto"],
        fan_modes=["Auto", "1", "5"], fan_mode="Auto",
        friendly_name="Clima Salotto",
    )
    hass.memoria_clima[CLIMA] = 24
    dati = {
        const.CONF_NOME: "Zona giorno",
        const.CONF_CLIMI: [CLIMA],
        const.CONF_APERTURE: {CLIMA: [PORTA, FINESTRA]},
        const.CONF_RITARDO_APERTURA: 60,
        const.CONF_RITARDO_CHIUSURA: 30,
    }
    dati.update(opzioni)
    controller = ClimaController(hass, Entry(dati))
    return hass, controller


async def avvia(controller):
    await controller.aperture.async_avvia()
    controller.hass.services.chiamate.clear()


def comandi(hass):
    return [(servizio, {k: w for k, w in dati.items() if k != "entity_id"})
            for _, servizio, dati in hass.services.chiamate]


def pausa(controller) -> Pausa:
    return controller.aperture.pause[CLIMA]


async def scenari():
    # --- 1. la porta attraversata ------------------------------------------
    hass, c = impianto()
    await avvia(c)
    hass.imposta(PORTA, "on")
    await hass.avanza(30)
    hass.imposta(PORTA, "off")
    await hass.avanza(300)
    v("porta aperta 30 s: nessun comando", comandi(hass) == [], comandi(hass))

    # --- 2. la finestra aperta per arieggiare -------------------------------
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(59)
    v("prima del ritardo non si spegne", comandi(hass) == [], comandi(hass))
    await hass.avanza(1)
    v("dopo 60 s si spegne, con un comando solo",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "off"})], comandi(hass))
    v("la pausa ricorda modalita', setpoint e ventola",
      pausa(c).salvato == {"hvac_mode": "cool", "temperature": 24, "fan_mode": "Auto"},
      pausa(c).salvato)
    hass.services.chiamate.clear()

    # il clima spento da noi non e' un gesto dell'utente
    v("lo spegnimento nostro non viene letto come manuale", not pausa(c).forzato)

    hass.imposta(FINESTRA, "off")
    await hass.avanza(29)
    v("chiusa da 29 s: ancora spento", comandi(hass) == [], comandi(hass))
    await hass.avanza(10)
    v("chiusa da 30 s: riacceso come prima",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "cool"})], comandi(hass))
    v("stato finale come prima dell'apertura",
      hass.states.get(CLIMA).state == "cool" and hass.states.get(CLIMA).attributes["temperature"] == 24)
    v("pausa chiusa", not pausa(c).attiva and not pausa(c).forzato)

    # --- 3. riacceso con un setpoint diverso da quello salvato --------------
    # La macchina ricorda 22, noi l'avevamo trovata a 24: va rimessa a 24,
    # e con il minimo di comandi.
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    hass.memoria_clima[CLIMA] = 22
    hass.services.chiamate.clear()
    hass.imposta(FINESTRA, "off")
    await hass.avanza(60)
    v("il setpoint ricordato dalla macchina viene corretto",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "cool"}),
                        ("set_temperature", {"temperature": 24})], comandi(hass))

    # --- 4. richiusa e riaperta subito ---------------------------------------
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    hass.services.chiamate.clear()
    hass.imposta(FINESTRA, "off")
    await hass.avanza(10)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(600)
    v("chiusa 10 s e riaperta: il compressore non riparte",
      comandi(hass) == [] and pausa(c).attiva, comandi(hass))

    # --- 5. «Non riaccendere» -------------------------------------------------
    hass, c = impianto()
    await avvia(c)
    hass.imposta(PORTA, "on")
    await hass.avanza(60)
    hass.services.chiamate.clear()
    v("il pulsante funziona solo durante una pausa", c.aperture.non_riaccendere(CLIMA))
    hass.imposta(PORTA, "off")
    await hass.avanza(60)
    v("con «Non riaccendere» resta spento",
      comandi(hass) == [] and hass.states.get(CLIMA).state == "off", comandi(hass))
    v("e la pausa si chiude", not pausa(c).attiva)
    v("fuori da una pausa il pulsante non fa niente", not c.aperture.non_riaccendere(CLIMA))

    # --- 6. riacceso a mano con la finestra aperta ----------------------------
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    hass.services.chiamate.clear()
    hass.imposta(CLIMA, "cool", temperature=23)  # dal telecomando
    v("riacceso a mano: la pausa lascia il posto all'ordine", pausa(c).forzato and not pausa(c).attiva)
    await hass.avanza(600)
    v("finche' resta aperta non viene rispento", comandi(hass) == [], comandi(hass))
    hass.imposta(FINESTRA, "off")
    await hass.avanza(30)
    v("richiusa: l'ordine si esaurisce", not pausa(c).forzato)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    v("alla prossima apertura la regola torna a valere",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "off"})], comandi(hass))

    # --- 7. clima spento: mai acceso ------------------------------------------
    hass, c = impianto(stato_clima="off")
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(120)
    hass.imposta(FINESTRA, "off")
    await hass.avanza(120)
    v("clima spento all'apertura: nessun comando, ne' prima ne' dopo",
      comandi(hass) == [] and hass.states.get(CLIMA).state == "off", comandi(hass))

    # --- 8. acceso con la finestra gia' aperta ---------------------------------
    hass, c = impianto(stato_clima="off")
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(600)
    hass.imposta(CLIMA, "cool", temperature=24)
    await hass.avanza(59)
    v("acceso con la finestra aperta: aspetta lo stesso ritardo", comandi(hass) == [])
    await hass.avanza(1)
    v("poi va in pausa come se la finestra si fosse appena aperta",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "off"})], comandi(hass))

    # --- 9. il gateway dell'allarme si riavvia ---------------------------------
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    hass.services.chiamate.clear()
    hass.imposta(FINESTRA, "unavailable")
    hass.imposta(PORTA, "unavailable")
    await hass.avanza(600)
    v("sensori non disponibili: nessuna riaccensione",
      comandi(hass) == [] and pausa(c).attiva, comandi(hass))
    hass.imposta(PORTA, "off")
    hass.imposta(FINESTRA, "on")
    await hass.avanza(600)
    v("tornano e la finestra e' ancora aperta: resta in pausa", comandi(hass) == [])
    hass.imposta(FINESTRA, "off")
    await hass.avanza(30)
    v("chiusa davvero: si riaccende",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "cool"})], comandi(hass))

    # --- 10. uscito di casa lasciando la finestra aperta ----------------------
    hass, c = impianto(**{const.CONF_LIMITE_RIACCENSIONE: 60})
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    hass.services.chiamate.clear()
    await hass.avanza(2 * 3600)
    hass.imposta(FINESTRA, "off")
    await hass.avanza(60)
    v("aperta 2 h con limite 60 min: al rientro resta spento", comandi(hass) == [], comandi(hass))

    # --- 11. riavvio di Home Assistant durante una pausa ----------------------
    finto_ha.azzera_memoria()
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    c.aperture.async_ferma()
    # "Riavvio": un gestore nuovo con lo stesso storage, e intanto la finestra
    # e' stata chiusa mentre Home Assistant era giu'.
    hass.states.mappa[FINESTRA] = finto_ha.Stato(FINESTRA, "off")
    c2 = ClimaController(hass, Entry(c.entry.data))
    await c2.aperture.async_avvia()
    hass.services.chiamate.clear()
    v("la pausa sopravvive al riavvio", c2.aperture.in_pausa(CLIMA))
    await hass.avanza(30)
    v("e alla ripartenza il clima si riaccende com'era",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "cool"})], comandi(hass))

    # Riacceso a mano mentre Home Assistant era fermo: la pausa salvata non
    # deve piu' valere, ne' rispegnerlo con la finestra ancora aperta.
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    c.aperture.async_ferma()
    hass.states.mappa[CLIMA] = finto_ha.Stato(
        CLIMA, "cool", {**hass.states.get(CLIMA).attributes, "temperature": 25})
    c2 = ClimaController(hass, Entry(c.entry.data))
    await c2.aperture.async_avvia()
    hass.services.chiamate.clear()
    await hass.avanza(600)
    v("riacceso a mano a HA fermo: resta acceso",
      comandi(hass) == [] and c2.aperture.pause[CLIMA].forzato, comandi(hass))

    # --- 12. modalita' ventilazione ----------------------------------------------
    hass, c = impianto(**{const.CONF_AZIONE_APERTURA: "fan_only"})
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    v("in ventilazione se la macchina la sa fare",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "fan_only"})], comandi(hass))
    v("in ventilazione il clima esce dalla modulazione", c.climi_accesi == [], c.climi_accesi)
    hass.imposta(CLIMA, "off")  # spento dall'utente durante la pausa
    v("spento a mano durante la ventilazione = non riaccendere", pausa(c).non_riaccendere)
    hass.services.chiamate.clear()
    hass.imposta(FINESTRA, "off")
    await hass.avanza(60)
    v("e alla chiusura resta spento", comandi(hass) == [], comandi(hass))

    hass, c = impianto(**{const.CONF_AZIONE_APERTURA: "fan_only"})
    hass.imposta(CLIMA, "cool", hvac_modes=["off", "cool", "heat"])
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    v("senza ventilazione disponibile si spegne",
      comandi(hass) == [("set_hvac_mode", {"hvac_mode": "off"})], comandi(hass))

    # --- 13. interruttore spento durante una pausa ------------------------------
    hass, c = impianto()
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    hass.services.chiamate.clear()
    c.aperture.set_abilitato(False)
    hass.imposta(FINESTRA, "off")
    await hass.avanza(120)
    v("disattivata durante una pausa: niente si riaccende da solo",
      comandi(hass) == [] and not pausa(c).attiva, comandi(hass))

    # --- 14. comando di pausa rifiutato -----------------------------------------
    hass, c = impianto()
    await avvia(c)
    hass.services.rotti.add("set_hvac_mode")
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    v("comando rifiutato: nessuna pausa registrata", not pausa(c).attiva)

    # --- 15. la zona e la modulazione ------------------------------------------
    hass, c = impianto(**{const.CONF_SENSORE_RETE: "sensor.rete"})
    hass.imposta("sensor.rete", "-500")
    await avvia(c)
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    d = c.valuta(finto_ha.OROLOGIO.adesso)
    v("tutti i clima in pausa: lo stato della zona lo dice",
      d.stato == const.STATO_APERTURA and d.setpoint is None, (d.stato, d.motivo))

    hass, c = impianto()
    await avvia(c)
    d = c.valuta(finto_ha.OROLOGIO.adesso)
    v("senza sensore di rete la zona non modula",
      d.stato == const.STATO_SENZA_MODULAZIONE and d.setpoint is None, (d.stato, d.motivo))

    # --- 16. il ripristino non e' un comando manuale -----------------------------
    hass, c = impianto(**{const.CONF_SENSORE_RETE: "sensor.rete"})
    hass.imposta("sensor.rete", "-500")
    await c.async_setup()
    await cedi()
    hass.imposta(FINESTRA, "on")
    await hass.avanza(60)
    pausa_salvata = pausa(c).salvato["temperature"]
    hass.memoria_clima[CLIMA] = 22
    hass.services.chiamate.clear()
    hass.imposta(FINESTRA, "off")
    await hass.avanza(30)
    await cedi()
    # I cambi di setpoint del ripristino (22 ricordato dalla macchina, poi il
    # nostro) arrivano al controller come eventi, come in Home Assistant.
    v("il ripristino corregge il setpoint ricordato dalla macchina",
      ("set_temperature", {"temperature": pausa_salvata}) in comandi(hass), comandi(hass))
    v("setpoint del ripristino non letto come manuale", c._manuale_fino is None, c.motivo)

    # Controllo: un cambio a tolleranza scaduta E' un comando manuale. Se
    # questa riga fallisse, quella sopra non dimostrerebbe niente.
    await hass.avanza(const.TOLLERANZA_RIPRISTINO + 1)
    hass.imposta(CLIMA, "cool", temperature=21)
    await cedi()
    v("controllo: dopo la tolleranza un setpoint diverso e' manuale", c._manuale_fino is not None)


def prove_pure():
    v("una finestra aperta basta", stato_aperture(["off", "on"]) == APERTA)
    v("tutte chiuse", stato_aperture(["off", "off"]) == CHIUSA)
    v("chiusa + non disponibile = ignota", stato_aperture(["off", "unavailable"]) == IGNOTA)
    v("aperta vince su non disponibile", stato_aperture(["on", "unavailable"]) == APERTA)

    p = Pausa(salvato={"hvac_mode": "cool"}, dal=finto_ha.INIZIO, in_stato="off")
    oltre = finto_ha.INIZIO + finto_ha.timedelta(minutes=61)
    v("limite zero: sempre", decidi_ripristino(p, oltre, True, 0)[0])
    v("oltre il limite: no", not decidi_ripristino(p, oltre, True, 60)[0])
    v("riaccensione disattivata: no", not decidi_ripristino(p, finto_ha.INIZIO, False, 0)[0])

    salvato = {"hvac_mode": "cool", "temperature": 24, "fan_mode": "5", "swing_mode": "Su"}
    v("prima la modalita', da sola",
      comandi_ripristino(salvato, "off", {}) == [("set_hvac_mode", {"hvac_mode": "cool"})])
    attributi = {"temperature": 24, "fan_mode": "Auto", "fan_modes": ["Auto", "5"],
                 "swing_mode": "Su", "swing_modes": ["Su", "Giu"]}
    v("poi solo cio' che differisce",
      comandi_ripristino(salvato, "cool", attributi) == [("set_fan_mode", {"fan_mode": "5"})])
    v("una ventola che la macchina non conosce non si manda",
      comandi_ripristino({"hvac_mode": "cool", "fan_mode": "Turbo"}, "cool",
                         {"fan_modes": ["Auto"]}) == [])

    dati = Pausa.da_dati(p.come_dati())
    v("la pausa si salva e si rilegge uguale", dati == p, dati)
    v("dati rovinati: pausa vuota", not Pausa.da_dati({"dal": "ieri"}).attiva)


def prove_config_flow():
    from nexus_clima import config_flow as cf

    class _H:
        states = finto_ha.Stati()

    h = _H()
    h.states.mappa["climate.a"] = finto_ha.Stato("climate.a", "off", {"friendly_name": "Clima"})
    h.states.mappa["climate.b"] = finto_ha.Stato("climate.b", "off", {"friendly_name": "Clima"})
    etichette = cf._etichette_climi(h, ["climate.a", "climate.b"])
    v("due clima con lo stesso nome restano distinti", len(set(etichette.values())) == 2, etichette)

    dati = cf._aperture_da({"Clima": ["binary_sensor.x"], "Clima (climate.b)": [],
                            const.CONF_RITARDO_APERTURA: 300}, etichette)
    v("un clima senza sensori sparisce dalla configurazione",
      dati[const.CONF_APERTURE] == {"climate.a": ["binary_sensor.x"]}, dati)

    v("zona senza rete e senza aperture: errore",
      cf._valida_scopo({const.CONF_CLIMI: ["climate.a"], const.CONF_APERTURE: {}}) != {})
    v("zona con sole aperture: valida",
      cf._valida_scopo({const.CONF_CLIMI: ["climate.a"],
                        const.CONF_APERTURE: {"climate.a": ["binary_sensor.x"]}}) == {})

    corrente = {const.CONF_CLIMI: ["climate.a"], const.CONF_SENSORE_RETE: "sensor.rete"}
    schema = cf._schema_zona(corrente, False)
    unito = cf._unito(corrente, {const.CONF_CLIMI: ["climate.a"]}, schema)
    v("un campo facoltativo svuotato si toglie davvero",
      const.CONF_SENSORE_RETE not in unito, unito)


asyncio.run(scenari())
prove_pure()
prove_config_flow()
esiti.chiudi()
