"""Un Home Assistant finto, quanto basta per provare Nexus Clima a tavolino.

Si iniettano moduli con i soli nomi che l'integrazione importa, e un impianto
con un orologio che si manda avanti a mano: i ritardi di un minuto si provano
in un istante, e nell'ordine giusto.

Il climatizzatore finto si comporta come uno vero nei punti che contano:
- spento, perde il setpoint negli attributi, come fanno molte integrazioni;
- riacceso, riprende il setpoint che ricordava lui, non quello che vorremmo;
- ogni cambio di stato arriva agli ascoltatori come un evento di Home Assistant.
"""

from __future__ import annotations

import asyncio
import copy
import sys
import types
from datetime import datetime, timedelta, timezone

INIZIO = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)

_SLEEP_VERO = asyncio.sleep


def _consegna(azione, evento) -> None:
    """Come Home Assistant: un ascoltatore asincrono viene schedulato, non atteso."""
    risultato = azione(evento)
    if asyncio.iscoroutine(risultato):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            risultato.close()
            return
        asyncio.ensure_future(risultato)


async def cedi(volte: int = 5) -> None:
    """Lascia girare i compiti schedulati dagli ascoltatori."""
    for _ in range(volte):
        await _SLEEP_VERO(0)


def _modulo(nome: str, **attributi):
    m = types.ModuleType(nome)
    for chiave, valore in attributi.items():
        setattr(m, chiave, valore)
    sys.modules[nome] = m
    return m


class _Platform(str):
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    SENSOR = "sensor"
    SWITCH = "switch"


# --- orologio -----------------------------------------------------------------
class Orologio:
    def __init__(self) -> None:
        self.adesso = INIZIO

    def now(self) -> datetime:
        return self.adesso


OROLOGIO = Orologio()

# --- impianto -----------------------------------------------------------------
_IMPIANTO: dict = {"hass": None}


def _async_call_later(hass, secondi, azione):
    return hass.pianifica(secondi, azione)


def _async_track_state_change_event(hass, entita, azione):
    if isinstance(entita, str):
        entita = [entita]
    return hass.ascolta(list(entita), azione)


_MEMORIA: dict[str, dict] = {}


class Store:
    """Storage in memoria, condiviso fra istanze: sopravvive a un 'riavvio'."""

    def __init__(self, hass, versione, chiave) -> None:
        self.chiave = chiave

    async def async_load(self):
        return copy.deepcopy(_MEMORIA.get(self.chiave))

    def async_delay_save(self, funzione, ritardo=0) -> None:
        _MEMORIA[self.chiave] = copy.deepcopy(funzione())

    async def async_remove(self) -> None:
        _MEMORIA.pop(self.chiave, None)


def azzera_memoria() -> None:
    _MEMORIA.clear()


# --- voluptuous e selettori, per il config flow ------------------------------
class _Chiave(str):
    def __new__(cls, nome, default=None, description=None):
        oggetto = super().__new__(cls, nome)
        oggetto.default = default
        oggetto.description = description
        return oggetto


class _Optional(_Chiave):
    pass


class _Required(_Chiave):
    pass


class _Schema:
    def __init__(self, schema) -> None:
        self.schema = schema


_vol = _modulo("voluptuous", Optional=_Optional, Required=_Required, Schema=_Schema)


class _Qualunque:
    def __init__(self, *args, **kwargs) -> None:
        self.args, self.kwargs = args, kwargs


_selector = _modulo(
    "homeassistant.helpers.selector",
    EntitySelector=_Qualunque,
    EntitySelectorConfig=_Qualunque,
    NumberSelector=_Qualunque,
    NumberSelectorConfig=_Qualunque,
    NumberSelectorMode=types.SimpleNamespace(BOX="box"),
    SelectSelector=_Qualunque,
    SelectSelectorConfig=_Qualunque,
    SelectSelectorMode=types.SimpleNamespace(LIST="list"),
    TimeSelector=_Qualunque,
)


class _Flusso:
    def __init_subclass__(cls, **kwargs) -> None:
        pass


# --- moduli -------------------------------------------------------------------
_modulo("homeassistant")
_modulo(
    "homeassistant.const",
    Platform=_Platform,
    EVENT_HOMEASSISTANT_STARTED="started",
    STATE_OFF="off",
    STATE_UNAVAILABLE="unavailable",
    STATE_UNKNOWN="unknown",
    UnitOfEnergy=types.SimpleNamespace(KILO_WATT_HOUR="kWh"),
    UnitOfTemperature=types.SimpleNamespace(CELSIUS="°C"),
)
_modulo("homeassistant.components")
_modulo(
    "homeassistant.components.climate",
    ATTR_CURRENT_TEMPERATURE="current_temperature",
    ATTR_FAN_MODE="fan_mode",
    ATTR_FAN_MODES="fan_modes",
    ATTR_HVAC_ACTION="hvac_action",
    ATTR_TEMPERATURE="temperature",
    DOMAIN="climate",
    SERVICE_SET_FAN_MODE="set_fan_mode",
    SERVICE_SET_TEMPERATURE="set_temperature",
)
_modulo(
    "homeassistant.config_entries",
    ConfigEntry=object,
    ConfigFlow=_Flusso,
    ConfigFlowResult=dict,
    OptionsFlow=_Flusso,
)
_modulo(
    "homeassistant.core",
    CALLBACK_TYPE=object,
    Event=object,
    HomeAssistant=object,
    callback=lambda f: f,
)
_helpers = _modulo("homeassistant.helpers")
_helpers.selector = _selector
_modulo(
    "homeassistant.helpers.event",
    async_call_later=_async_call_later,
    async_track_state_change_event=_async_track_state_change_event,
    async_track_time_change=lambda *a, **k: (lambda: None),
    async_track_time_interval=lambda *a, **k: (lambda: None),
)
_modulo("homeassistant.helpers.storage", Store=Store)
_modulo("homeassistant.util", dt=types.SimpleNamespace(now=OROLOGIO.now))
_cv = _modulo(
    "homeassistant.helpers.config_validation",
    config_entry_only_config_schema=lambda dominio: None,
)
_helpers.config_validation = _cv

sys.path.insert(
    0,
    r"C:\Users\giova\Desktop\Progetto domotica\Home Assistant\nexus_clima\custom_components",
)


# --- stati, eventi, servizi ---------------------------------------------------
class Stato:
    def __init__(self, entity_id: str, state: str, attributes: dict | None = None) -> None:
        self.entity_id = entity_id
        self.state = state
        self.attributes = dict(attributes or {})


class Evento:
    def __init__(self, dati: dict) -> None:
        self.data = dati


class Stati:
    def __init__(self) -> None:
        self.mappa: dict[str, Stato] = {}

    def get(self, entity_id: str):
        return self.mappa.get(entity_id)


class ErroreServizio(Exception):
    pass


class Servizi:
    def __init__(self, hass: "Hass") -> None:
        self.hass = hass
        self.chiamate: list[tuple[str, str, dict]] = []
        self.rotti: set[str] = set()

    async def async_call(self, dominio, servizio, dati, blocking=False) -> None:
        self.chiamate.append((dominio, servizio, dict(dati)))
        if servizio in self.rotti:
            raise ErroreServizio(f"{servizio} non riuscito")
        if dominio == "climate":
            self.hass.clima_esegue(dati["entity_id"], servizio, dati)


class _Loop:
    def time(self) -> float:
        return (OROLOGIO.adesso - INIZIO).total_seconds()


class Hass:
    def __init__(self) -> None:
        self.states = Stati()
        self.services = Servizi(self)
        self.loop = _Loop()
        self.is_running = True
        self.data: dict = {}
        self.compiti: list = []
        self._timer: list[list] = []  # [scadenza, numero, azione, attivo]
        self._numero = 0
        self._ascoltatori: dict[str, list] = {}
        # Cio' che ogni clima "ricorda" da spento: il setpoint che riprende.
        self.memoria_clima: dict[str, float] = {}
        _IMPIANTO["hass"] = self

    def async_create_task(self, coroutine):
        compito = asyncio.ensure_future(coroutine)
        self.compiti.append(compito)
        return compito

    # stati
    def imposta(self, entity_id: str, stato: str, **attributi) -> None:
        vecchio = self.states.get(entity_id)
        base = dict(vecchio.attributes) if vecchio else {}
        base.update(attributi)
        nuovo = Stato(entity_id, stato, base)
        self.states.mappa[entity_id] = nuovo
        for azione in list(self._ascoltatori.get(entity_id, [])):
            _consegna(azione, Evento({"entity_id": entity_id, "old_state": vecchio, "new_state": nuovo}))

    def ascolta(self, entita: list[str], azione):
        for entity_id in entita:
            self._ascoltatori.setdefault(entity_id, []).append(azione)

        def _annulla() -> None:
            for entity_id in entita:
                if azione in self._ascoltatori.get(entity_id, []):
                    self._ascoltatori[entity_id].remove(azione)

        return _annulla

    # il climatizzatore finto
    def clima_esegue(self, entity_id: str, servizio: str, dati: dict) -> None:
        attuale = self.states.get(entity_id)
        attributi = dict(attuale.attributes)
        stato = attuale.state
        if servizio == "turn_off" or (servizio == "set_hvac_mode" and dati["hvac_mode"] == "off"):
            if attributi.get("temperature") is not None:
                self.memoria_clima[entity_id] = attributi["temperature"]
            attributi["temperature"] = None
            stato = "off"
        elif servizio == "set_hvac_mode":
            if stato == "off":
                attributi["temperature"] = self.memoria_clima.get(entity_id)
            stato = dati["hvac_mode"]
        elif servizio == "set_temperature":
            attributi["temperature"] = dati["temperature"]
        elif servizio in ("set_fan_mode", "set_swing_mode", "set_preset_mode"):
            campo = servizio.removeprefix("set_")
            attributi[campo] = dati[campo]
        self.states.mappa[entity_id] = Stato(entity_id, stato, attributi)
        for azione in list(self._ascoltatori.get(entity_id, [])):
            _consegna(azione, Evento({"entity_id": entity_id, "old_state": attuale,
                                      "new_state": self.states.mappa[entity_id]}))

    # tempo
    def pianifica(self, secondi: float, azione):
        self._numero += 1
        voce = [OROLOGIO.adesso + timedelta(seconds=secondi), self._numero, azione, True]
        self._timer.append(voce)

        def _annulla() -> None:
            voce[3] = False

        return _annulla

    async def avanza(self, secondi: float) -> None:
        """Manda avanti l'orologio eseguendo i ritardi scaduti, in ordine."""
        fine = OROLOGIO.adesso + timedelta(seconds=secondi)
        while True:
            pronti = sorted(
                (v for v in self._timer if v[3] and v[0] <= fine), key=lambda v: (v[0], v[1])
            )
            if not pronti:
                break
            voce = pronti[0]
            voce[3] = False
            OROLOGIO.adesso = max(OROLOGIO.adesso, voce[0])
            risultato = voce[2](OROLOGIO.adesso)
            if asyncio.iscoroutine(risultato):
                await risultato
        OROLOGIO.adesso = max(OROLOGIO.adesso, fine)


async def dormi(secondi: float) -> None:
    """Sostituto di asyncio.sleep: fa passare il tempo finto, non quello vero."""
    OROLOGIO.adesso += timedelta(seconds=secondi)
    await _SLEEP_VERO(0)


def nuovo_impianto() -> Hass:
    OROLOGIO.adesso = INIZIO
    return Hass()


class Entry:
    def __init__(self, dati: dict, entry_id: str = "prova", title: str = "Zona giorno") -> None:
        self.entry_id = entry_id
        self.title = title
        self.data = dati
        self.options: dict = {}


class Esiti:
    def __init__(self, titolo: str) -> None:
        self.titolo = titolo
        self.voci: list[tuple[str, bool, str]] = []

    def verifica(self, nome: str, condizione, dettaglio: str = "") -> None:
        self.voci.append((nome, bool(condizione), dettaglio))

    def chiudi(self) -> None:
        larghezza = max(len(n) for n, _, _ in self.voci)
        falliti = [v for v in self.voci if not v[1]]
        for nome, ok, dettaglio in self.voci:
            riga = f"{'ok  ' if ok else 'FALLITO'} {nome.ljust(larghezza)}"
            if not ok and dettaglio:
                riga += f"   {dettaglio}"
            print(riga)
        print()
        if falliti:
            print(f"{self.titolo}: {len(falliti)} controlli falliti su {len(self.voci)}")
            sys.exit(1)
        print(f"{self.titolo}: TUTTI I CONTROLLI SUPERATI ({len(self.voci)})")
