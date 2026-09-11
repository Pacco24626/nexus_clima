"""Prova di fumo delle entita': si creano come farebbe Home Assistant e se ne
leggono stato e attributi, durante una pausa e fuori.

Serve a trovare nomi sbagliati e attributi rotti prima che li trovi un utente
con il log pieno di eccezioni.

    python tests/test_entita.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import finto_ha  # noqa: E402
from finto_ha import Entry, Esiti, dormi, nuovo_impianto  # noqa: E402


def _modulo(nome, **attributi):
    m = types.ModuleType(nome)
    for chiave, valore in attributi.items():
        setattr(m, chiave, valore)
    sys.modules[nome] = m
    return m


class _Entita:
    hass = None

    async def async_added_to_hass(self):
        pass

    def async_on_remove(self, funzione):
        pass

    def async_write_ha_state(self):
        pass


class _Restore(_Entita):
    async def async_get_last_state(self):
        return None


def _base(nome):
    return type(nome, (_Entita,), {})


_modulo("homeassistant.helpers.entity", Entity=_Entita)
_modulo("homeassistant.helpers.device_registry", DeviceInfo=dict)
_modulo("homeassistant.helpers.entity_registry",
        async_get=lambda hass: types.SimpleNamespace(async_get=lambda eid: None))
_modulo("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
_modulo("homeassistant.helpers.restore_state", RestoreEntity=_Restore)
_modulo("homeassistant.components.binary_sensor", BinarySensorEntity=_base("BinarySensorEntity"))
_modulo("homeassistant.components.button", ButtonEntity=_base("ButtonEntity"))
_modulo("homeassistant.components.switch", SwitchEntity=_base("SwitchEntity"))
_modulo(
    "homeassistant.components.sensor",
    SensorEntity=_base("SensorEntity"),
    SensorDeviceClass=types.SimpleNamespace(TEMPERATURE="temperature", ENERGY="energy"),
    SensorStateClass=types.SimpleNamespace(MEASUREMENT="measurement", TOTAL_INCREASING="ti"),
)

from nexus_clima import (  # noqa: E402
    binary_sensor,
    button,
    const,
    controller as modulo_controller,
    gestore_aperture,
    sensor,
    switch,
)
from nexus_clima.controller import ClimaController  # noqa: E402

gestore_aperture.asyncio = types.SimpleNamespace(sleep=dormi)
modulo_controller.asyncio = types.SimpleNamespace(sleep=dormi)

CLIMA = "climate.clima_salotto"
FINESTRA = "binary_sensor.finestra_cucina"

esiti = Esiti("ENTITA")
v = esiti.verifica


async def crea(modulo, hass, entry):
    create = []
    await modulo.async_setup_entry(hass, entry, lambda entita: create.extend(entita))
    return create


def leggi(entita):
    """Tutto cio' che Home Assistant leggerebbe per scrivere lo stato."""
    letto = {"nome": getattr(entita, "_attr_name", None)}
    for campo in ("is_on", "native_value", "extra_state_attributes"):
        if hasattr(type(entita), campo):
            letto[campo] = getattr(entita, campo)
    return letto


async def prova():
    for con_rete, modalita in ((False, None), (True, const.MODALITA_SOGLIE), (True, const.MODALITA_CONTINUA)):
        finto_ha.azzera_memoria()
        hass = nuovo_impianto()
        hass.imposta(FINESTRA, "off")
        hass.imposta(CLIMA, "cool", temperature=24, current_temperature=26,
                     hvac_modes=["off", "cool"], friendly_name="Clima Salotto")
        hass.imposta("sensor.rete", "-400")
        dati = {
            const.CONF_NOME: "Zona giorno",
            const.CONF_CLIMI: [CLIMA],
            const.CONF_APERTURE: {CLIMA: [FINESTRA]},
        }
        if con_rete:
            dati[const.CONF_SENSORE_RETE] = "sensor.rete"
            dati[const.CONF_MODALITA] = modalita
        entry = Entry(dati)
        c = ClimaController(hass, entry)
        hass.data = {const.DOMAIN: {entry.entry_id: c}}
        await c.aperture.async_avvia()

        tutte = []
        for modulo in (binary_sensor, button, sensor, switch):
            tutte += await crea(modulo, hass, entry)
        nomi = sorted(e._attr_name for e in tutte)
        etichetta = f"rete, {modalita}" if con_rete else "senza rete"

        attese = {"Pausa Clima Salotto", "Non riaccendere Clima Salotto", "Stato",
                  "Pausa per aperture"}
        if con_rete:
            attese |= {"Modulazione solare", "Deriva", "Energia della zona"}
        if modalita == const.MODALITA_CONTINUA:
            attese |= {"Riprendi il controllo", "Pavimento raggiungibile"}
        v(f"{etichetta}: le entita' giuste", set(nomi) == attese, nomi)

        prima = [leggi(e) for e in tutte]
        hass.imposta(FINESTRA, "on")
        await hass.avanza(const.DEFAULT_RITARDO_APERTURA)
        durante = [leggi(e) for e in tutte]

        pausa = next(e for e in tutte if e._attr_name.startswith("Pausa Clima"))
        v(f"{etichetta}: il sensore della pausa si accende", pausa.is_on and not prima[0].get("is_on", False))
        attr = pausa.extra_state_attributes
        v(f"{etichetta}: attributi della pausa leggibili",
          attr["aperture_aperte"] == [FINESTRA] and attr["stato_da_ripristinare"] == "cool"
          and attr["riaccende_alla_chiusura"] is True, attr)

        pulsante = next(e for e in tutte if e._attr_name.startswith("Non riaccendere"))
        await pulsante.async_press()
        v(f"{etichetta}: il pulsante imposta «non riaccendere»",
          pausa.extra_state_attributes["non_riaccendere"] is True
          and pausa.extra_state_attributes["riaccende_alla_chiusura"] is False)

        stato = next(e for e in tutte if e._attr_name == "Stato")
        v(f"{etichetta}: lo stato della zona elenca il clima in pausa",
          stato.extra_state_attributes["in_pausa_per_apertura"] == [CLIMA],
          stato.extra_state_attributes)

        interruttore = next(e for e in tutte if e._attr_name == "Pausa per aperture")
        await interruttore.async_turn_off()
        v(f"{etichetta}: l'interruttore spegne le pause", not interruttore.is_on and not pausa.is_on)
        v(f"{etichetta}: nessuna lettura ha sollevato eccezioni", len(durante) == len(prima))


asyncio.run(prova())
esiti.chiudi()
