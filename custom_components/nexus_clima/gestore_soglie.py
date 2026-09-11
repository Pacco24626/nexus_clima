"""Modulazione a soglie: tempi, ascolto, comandi.

Le decisioni elementari stanno in soglie.py. Qui si misura da quanto dura un
prelievo o una cessione, si riconosce chi ha toccato un clima, e si mandano i
soli comandi indispensabili.

Chi ha toccato un clima:
- un cambio verso l'eco, subito dopo un nostro comando, e' nostro;
- qualunque altro cambio mentre il clima e' in eco e' dell'utente: da li' in
  poi il suo nuovo setpoint e' il comfort, e l'eco torna solo dopo un altro
  prelievo lungo quanto previsto;
- un clima appena acceso o appena reimpostato ha davanti tutto il tempo di
  prelievo, anche se la casa preleva gia' da un'ora: prima si rispetta la
  scelta dell'utente, poi si risparmia.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, Event, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .aperture import INDISPONIBILI, acceso
from .const import (
    CONF_ATTIVA_A,
    CONF_ATTIVA_DA,
    CONF_CONSUMO_IN_PIU,
    CONF_ECO_TEMP,
    CONF_ECO_VENTOLA,
    CONF_SOGLIA_CESSIONE,
    CONF_SOGLIA_PRELIEVO,
    CONF_TEMPO_CESSIONE,
    CONF_TEMPO_PRELIEVO,
    DEFAULT_ATTIVA_A,
    DEFAULT_ATTIVA_DA,
    DEFAULT_CONSUMO_IN_PIU,
    DEFAULT_ECO_TEMP,
    DEFAULT_ECO_VENTOLA,
    DEFAULT_SOGLIA_CESSIONE,
    DEFAULT_SOGLIA_PRELIEVO,
    DEFAULT_TEMPO_CESSIONE,
    DEFAULT_TEMPO_PRELIEVO,
    DOMAIN,
    SPAZIATURA,
    STATO_COMFORT,
    STATO_ECO,
    STATO_FUORI,
    STATO_NON_PRONTO,
    TOLLERANZA_COMANDO,
)
from .soglie import (
    Eco,
    candidato,
    come_lasciato,
    comandi_comfort,
    comandi_eco,
    minuti_mancanti,
    soglia_ritorno,
    trascorso,
)

if TYPE_CHECKING:
    from .controller import ClimaController

_LOGGER = logging.getLogger(__name__)

VERSIONE_STORAGE = 1
# Condiviso fra le zone: l'ultimo ritorno al comfort, per farle tornare una
# alla volta. Tornassero tutte insieme, il surplus che ne basta per una le
# riporterebbe tutte in eco.
CHIAVE_CONDIVISA = f"{DOMAIN}_soglie"


def chiave_storage(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}.soglie"


class GestoreSoglie:
    """Comfort o eco per i clima di una zona, secondo lo scambio con la rete."""

    def __init__(self, controller: ClimaController, cfg: dict[str, Any]) -> None:
        self.c = controller
        self.hass = controller.hass
        self.eco_temp = float(cfg.get(CONF_ECO_TEMP, DEFAULT_ECO_TEMP))
        ventola = cfg.get(CONF_ECO_VENTOLA, DEFAULT_ECO_VENTOLA)
        # Vuota: in eco la ventilazione non si tocca.
        self.eco_ventola: str | None = (str(ventola).strip() or None) if ventola else None
        self.soglia_prelievo = float(cfg.get(CONF_SOGLIA_PRELIEVO, DEFAULT_SOGLIA_PRELIEVO))
        self.tempo_prelievo = float(cfg.get(CONF_TEMPO_PRELIEVO, DEFAULT_TEMPO_PRELIEVO))
        self.soglia_cessione = float(cfg.get(CONF_SOGLIA_CESSIONE, DEFAULT_SOGLIA_CESSIONE))
        self.tempo_cessione = float(cfg.get(CONF_TEMPO_CESSIONE, DEFAULT_TEMPO_CESSIONE))
        self.consumo_in_piu = float(cfg.get(CONF_CONSUMO_IN_PIU, DEFAULT_CONSUMO_IN_PIU))
        self.attiva_da: str = cfg.get(CONF_ATTIVA_DA) or DEFAULT_ATTIVA_DA
        self.attiva_a: str = cfg.get(CONF_ATTIVA_A) or DEFAULT_ATTIVA_A

        self.eco: dict[str, Eco] = {}
        self.prelievo_da: datetime | None = None
        self.cessione_da: datetime | None = None
        self.ultimo_scambio: float | None = None  # positivo = prelievo

        # Da quando ciascun clima e' com'e' per scelta dell'utente: acceso o
        # reimpostato. L'eco non arriva prima di un tempo di prelievo intero.
        self._scelto_da: dict[str, datetime] = {}
        self._nostro_fino: dict[str, datetime] = {}
        self._store: Store = Store(self.hass, VERSIONE_STORAGE, chiave_storage(controller.entry.entry_id))
        self._unsub: list[CALLBACK_TYPE] = []
        self._in_azione = False

    # -------------------------------------------------------------------------
    # Ciclo di vita
    # -------------------------------------------------------------------------
    async def async_avvia(self) -> None:
        dati = await self._store.async_load() or {}
        for clima, salvato in (dati.get("eco") or {}).items():
            if clima not in self.c.climi or (eco := Eco.da_dati(salvato)) is None:
                continue
            macchina = self.hass.states.get(clima)
            # Toccato mentre Home Assistant era fermo: vale l'utente.
            if macchina is not None and macchina.state not in INDISPONIBILI:
                if macchina.state != "cool" or not come_lasciato(
                    dict(macchina.attributes), self.eco_temp, self.eco_ventola
                ):
                    continue
            self.eco[clima] = eco

        if self.c.sensore_rete:
            self._unsub.append(
                async_track_state_change_event(self.hass, [self.c.sensore_rete], self._su_rete)
            )
        if self.c.climi:
            self._unsub.append(
                async_track_state_change_event(self.hass, self.c.climi, self._su_clima)
            )
        self._aggiorna_tempi(dt_util.now())
        self._salva()

    @callback
    def async_ferma(self) -> None:
        for annulla in self._unsub:
            annulla()
        self._unsub.clear()

    # -------------------------------------------------------------------------
    # Lettura
    # -------------------------------------------------------------------------
    def in_eco(self) -> list[str]:
        """I clima in eco che contano adesso: non quelli fermi per un'apertura."""
        return [clima for clima in self.eco if not self._in_pausa(clima)]

    def soglia_ritorno(self) -> float:
        return soglia_ritorno(self.soglia_cessione, self.consumo_in_piu, len(self.in_eco()))

    def in_fascia(self, adesso: datetime) -> bool:
        return self.c._dentro(adesso.time(), self.attiva_da, self.attiva_a)

    def _in_pausa(self, clima: str) -> bool:
        return self.c.aperture is not None and self.c.aperture.in_pausa(clima)

    @property
    def _condiviso(self) -> dict[str, Any]:
        return self.hass.data.setdefault(CHIAVE_CONDIVISA, {"ultimo_ritorno": None})

    # -------------------------------------------------------------------------
    # Ascolto
    # -------------------------------------------------------------------------
    @callback
    def _su_rete(self, _event: Event) -> None:
        self._aggiorna_tempi(dt_util.now())

    @callback
    def _aggiorna_tempi(self, adesso: datetime) -> None:
        """Da quanto dura il prelievo, e da quanto la cessione che basta.

        Come il "per X minuti" di un'automazione: basta un campione sotto la
        soglia perche' il conteggio riparta.
        """
        scambio = self.c._import_rete()
        self.ultimo_scambio = scambio
        if scambio is None:
            self.prelievo_da = self.cessione_da = None
            return
        if scambio > self.soglia_prelievo:
            self.prelievo_da = self.prelievo_da or adesso
        else:
            self.prelievo_da = None
        if self.in_eco() and -scambio > self.soglia_ritorno():
            self.cessione_da = self.cessione_da or adesso
        else:
            self.cessione_da = None

    def _nostro(self, clima: str, adesso: datetime) -> bool:
        if (fino := self._nostro_fino.get(clima)) is not None and adesso < fino:
            return True
        # Anche un ripristino dopo un'apertura e' nostro, non dell'utente.
        fino = self.c._ignora_manuale.get(clima)
        return fino is not None and adesso < fino

    @callback
    def _su_clima(self, event: Event) -> None:
        clima = event.data.get("entity_id")
        nuovo = event.data.get("new_state")
        vecchio = event.data.get("old_state")
        if clima not in self.c.climi or nuovo is None or nuovo.state in INDISPONIBILI:
            return
        if self._in_pausa(clima):
            return
        adesso = dt_util.now()
        attributi = dict(nuovo.attributes)

        if clima in self.eco:
            if self._nostro(clima, adesso):
                return
            if nuovo.state == "cool" and come_lasciato(attributi, self.eco_temp, self.eco_ventola):
                return
            # L'utente l'ha spento, o gli ha cambiato setpoint, ventola o
            # modalita': da adesso il comfort e' il suo.
            del self.eco[clima]
            self._scelto_da[clima] = adesso
            _LOGGER.info("%s: %s toccato durante l'eco, lo si lascia come l'ha messo", self.c.nome, clima)
            self._salva()
            self.c.notify()
            return

        if self._nostro(clima, adesso):
            return
        prima = vecchio.state if vecchio is not None else None
        if acceso(nuovo.state) and not acceso(prima):
            self._scelto_da[clima] = adesso
        elif vecchio is not None and (
            vecchio.attributes.get("temperature") != attributi.get("temperature")
            or vecchio.attributes.get("fan_mode") != attributi.get("fan_mode")
            or prima != nuovo.state
        ):
            self._scelto_da[clima] = adesso

    # -------------------------------------------------------------------------
    # La decisione
    # -------------------------------------------------------------------------
    async def async_valuta(self, adesso: datetime) -> tuple[str, str]:
        """Decide e agisce. Restituisce stato e motivo per il sensore."""
        self._aggiorna_tempi(adesso)
        if self._in_azione:
            return self.c.stato, self.c.motivo

        if not self.in_fascia(adesso):
            if self.eco:
                # Fine fascia: si smette di gestire. Chi e' in eco resta
                # com'e', come faceva l'automazione a fasce orarie; da qui in
                # poi comanda l'utente.
                _LOGGER.info("%s: fine fascia, %s restano come sono", self.c.nome, ", ".join(self.eco))
                self.eco.clear()
                self._salva()
            return STATO_FUORI, f"fuori dalla fascia {self.attiva_da[:5]}–{self.attiva_a[:5]}"

        scambio = self.ultimo_scambio
        if scambio is None:
            return STATO_NON_PRONTO, "sensore di rete non disponibile"

        ora = f"prelevi {scambio:.0f} W" if scambio > 0 else f"cedi {-scambio:.0f} W"

        # 1. Chi e' in eco torna al comfort, se la cessione basta da abbastanza.
        in_eco = self.in_eco()
        if in_eco and self.cessione_da is not None:
            inizio = self.cessione_da
            ultimo = self._condiviso.get("ultimo_ritorno")
            if ultimo is not None and ultimo > inizio:
                inizio = ultimo
            if trascorso(inizio, adesso, self.tempo_cessione):
                await self._async_torna_comfort(in_eco, adesso)
                self._condiviso["ultimo_ritorno"] = adesso
                self.cessione_da = None
                return STATO_COMFORT, f"{ora} da {self.tempo_cessione:.0f} min: comfort ripristinato"

        # 2. Chi e' in comfort va in eco, se il prelievo dura da abbastanza.
        candidati = []
        for clima in self.c.climi:
            if clima in self.eco or self._in_pausa(clima):
                continue
            macchina = self.hass.states.get(clima)
            if macchina is not None and candidato(macchina.state, dict(macchina.attributes), self.eco_temp):
                candidati.append(clima)

        pronti: list[str] = []
        attese: list[int] = []
        if self.prelievo_da is not None:
            for clima in candidati:
                inizio = self.prelievo_da
                scelto = self._scelto_da.get(clima)
                if scelto is not None and scelto > inizio:
                    inizio = scelto
                if trascorso(inizio, adesso, self.tempo_prelievo):
                    pronti.append(clima)
                else:
                    attese.append(minuti_mancanti(inizio, adesso, self.tempo_prelievo))
        if pronti:
            await self._async_metti_in_eco(pronti, adesso)
            return STATO_ECO, (
                f"prelievo oltre {self.soglia_prelievo:.0f} W da {self.tempo_prelievo:.0f} min: eco"
            )

        # 3. Nessuna azione: si dice perche'.
        if self.in_eco():
            serve = self.soglia_ritorno()
            if self.cessione_da is not None:
                inizio = max(self.cessione_da, self._condiviso.get("ultimo_ritorno") or self.cessione_da)
                resta = minuti_mancanti(inizio, adesso, self.tempo_cessione)
                return STATO_ECO, f"{ora}, ne servono {serve:.0f}: comfort fra {resta} min"
            return STATO_ECO, (
                f"{ora}; per tornare al comfort bisogna cedere oltre {serve:.0f} W "
                f"({self.soglia_cessione:.0f} + {self.consumo_in_piu:.0f} per clima) "
                f"per {self.tempo_cessione:.0f} min"
            )
        if not candidati:
            return STATO_COMFORT, (
                f"nessun clima acceso in raffrescamento sotto i {self.eco_temp:.0f} °C: niente da fare"
            )
        if attese:
            return STATO_COMFORT, f"{ora}: eco fra {min(attese)} min"
        return STATO_COMFORT, f"{ora}: l'eco scatta oltre {self.soglia_prelievo:.0f} W di prelievo"

    # -------------------------------------------------------------------------
    # Azioni
    # -------------------------------------------------------------------------
    async def _async_metti_in_eco(self, climi: list[str], adesso: datetime) -> None:
        self._in_azione = True
        try:
            for indice, clima in enumerate(climi):
                macchina = self.hass.states.get(clima)
                if macchina is None:
                    continue
                attributi = dict(macchina.attributes)
                # Registrato PRIMA dei comandi: i cambi di stato che seguono
                # devono gia' trovarlo.
                self.eco[clima] = Eco(
                    comfort_temp=float(attributi["temperature"]),
                    comfort_ventola=attributi.get("fan_mode"),
                    dal=adesso,
                )
                self._nostro_fino[clima] = adesso + timedelta(seconds=TOLLERANZA_COMANDO)
                if indice:
                    await asyncio.sleep(SPAZIATURA)
                await self._async_esegui(clima, comandi_eco(attributi, self.eco_temp, self.eco_ventola))
                _LOGGER.info(
                    "%s: %s in eco (%.0f °C), il comfort era %.0f °C",
                    self.c.nome, clima, self.eco_temp, self.eco[clima].comfort_temp,
                )
        finally:
            self._in_azione = False
            self._salva()

    async def _async_torna_comfort(self, climi: list[str], adesso: datetime) -> None:
        self._in_azione = True
        try:
            for indice, clima in enumerate(climi):
                eco = self.eco.pop(clima, None)
                macchina = self.hass.states.get(clima)
                # Mai accendere: un clima spento nel frattempo resta spento.
                if eco is None or macchina is None or not acceso(macchina.state):
                    continue
                self._nostro_fino[clima] = adesso + timedelta(seconds=TOLLERANZA_COMANDO)
                if indice:
                    await asyncio.sleep(SPAZIATURA)
                await self._async_esegui(clima, comandi_comfort(eco, dict(macchina.attributes)))
                _LOGGER.info("%s: %s tornato al comfort (%.0f °C)", self.c.nome, clima, eco.comfort_temp)
        finally:
            self._in_azione = False
            self._salva()

    async def async_disattiva(self) -> None:
        """Modulazione spenta: chi e' in eco torna al comfort che aveva."""
        in_eco = self.in_eco()
        if in_eco:
            await self._async_torna_comfort(in_eco, dt_util.now())
        self.eco.clear()
        self._salva()
        self.c.notify()

    async def _async_esegui(self, clima: str, comandi: list[tuple[str, dict[str, Any]]]) -> None:
        for indice, (servizio, dati) in enumerate(comandi):
            if indice:
                await asyncio.sleep(SPAZIATURA)
            try:
                await self.hass.services.async_call(
                    "climate", servizio, {"entity_id": clima, **dati}, blocking=True
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("%s: %s su %s fallito: %s", self.c.nome, servizio, clima, err)
                return

    # -------------------------------------------------------------------------
    # Memoria
    # -------------------------------------------------------------------------
    @callback
    def _salva(self) -> None:
        self._store.async_delay_save(
            lambda: {"eco": {clima: eco.come_dati() for clima, eco in self.eco.items()}}, 1
        )

    def dettagli(self) -> dict[str, Any]:
        """Per gli attributi del sensore di stato. Sempre strutture nuove."""
        return {
            "modalita": "soglie",
            "in_eco": list(self.eco),
            "comfort_da_ripristinare": {
                clima: eco.comfort_temp for clima, eco in self.eco.items()
            },
            "scambio_w": None if self.ultimo_scambio is None else round(self.ultimo_scambio),
            "soglia_ritorno_w": round(self.soglia_ritorno()),
            "fascia": f"{self.attiva_da[:5]}–{self.attiva_a[:5]}",
        }
