"""Pausa dei climatizzatori a porta o finestra aperta: attese, ascolto, comandi.

Le decisioni stanno in aperture.py. Qui si tiene il tempo, si ascoltano i
sensori e le macchine, e si manda il minimo di comandi indispensabile.

Tre regole, in ordine di importanza:

1. **Una macchina spenta non viene mai accesa.** Si riaccende solo cio' che
   abbiamo spento noi, e com'era.
2. **L'utente vince.** Riaccesa a mano con la finestra aperta resta accesa; il
   pulsante «Non riaccendere» vince sulla riaccensione alla chiusura.
3. **Il dubbio ferma.** Un sensore che non risponde non vale come chiuso:
   nessuna riaccensione finche' non torna.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .aperture import (
    APERTA,
    CHIUSA,
    INDISPONIBILI,
    SPENTO,
    Pausa,
    acceso,
    comandi_ripristino,
    comando_pausa,
    decidi_ripristino,
    istantanea,
    stato_aperture,
    stato_in_pausa,
)
from .const import (
    ATTESA_ACCENSIONE,
    CONF_AZIONE_APERTURA,
    CONF_LIMITE_RIACCENSIONE,
    CONF_RIACCENDI,
    CONF_RITARDO_APERTURA,
    CONF_RITARDO_CHIUSURA,
    DEFAULT_AZIONE_APERTURA,
    DEFAULT_LIMITE_RIACCENSIONE,
    DEFAULT_RITARDO_APERTURA,
    DEFAULT_RITARDO_CHIUSURA,
    DOMAIN,
    SPAZIATURA,
)

_LOGGER = logging.getLogger(__name__)

VERSIONE_STORAGE = 1


def chiave_storage(entry_id: str) -> str:
    return f"{DOMAIN}.{entry_id}.aperture"


class GestoreAperture:
    """Le pause per apertura dei climatizzatori di una zona."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        nome: str,
        aperture: dict[str, list[str]],
        cfg: dict[str, Any],
        notifica: Callable[[], None],
        al_ripristino: Callable[[str, float | None], None],
    ) -> None:
        self.hass = hass
        self.nome = nome
        # Solo i climatizzatori con almeno un sensore.
        self.aperture: dict[str, list[str]] = {
            clima: list(sensori) for clima, sensori in aperture.items() if sensori
        }
        self.ritardo_apertura = int(cfg.get(CONF_RITARDO_APERTURA, DEFAULT_RITARDO_APERTURA))
        self.ritardo_chiusura = int(cfg.get(CONF_RITARDO_CHIUSURA, DEFAULT_RITARDO_CHIUSURA))
        self.azione: str = cfg.get(CONF_AZIONE_APERTURA) or DEFAULT_AZIONE_APERTURA
        self.riaccendi = bool(cfg.get(CONF_RIACCENDI, True))
        self.limite = int(cfg.get(CONF_LIMITE_RIACCENSIONE, DEFAULT_LIMITE_RIACCENSIONE))

        self.abilitato = True
        self.pause: dict[str, Pausa] = {clima: Pausa() for clima in self.aperture}
        # L'ultima cosa successa per ciascun clima, in parole: e' il "perche'"
        # che si legge nel sensore della pausa.
        self.esito: dict[str, str] = {}

        self._notifica = notifica
        self._al_ripristino = al_ripristino
        self._store: Store = Store(hass, VERSIONE_STORAGE, chiave_storage(entry_id))
        self._timer_apertura: dict[str, CALLBACK_TYPE] = {}
        self._timer_chiusura: dict[str, CALLBACK_TYPE] = {}
        self._unsub: list[CALLBACK_TYPE] = []
        self._avviato = False

    # -------------------------------------------------------------------------
    # Ciclo di vita
    # -------------------------------------------------------------------------
    async def async_avvia(self) -> None:
        """Da chiamare a Home Assistant avviato, con gli stati gia' presenti."""
        dati = await self._store.async_load() or {}
        for clima, salvata in (dati.get("pause") or {}).items():
            if clima not in self.pause:
                continue
            pausa = Pausa.da_dati(salvata)
            macchina = self.hass.states.get(clima)
            if (
                pausa.attiva
                and macchina is not None
                and macchina.state not in INDISPONIBILI
                and macchina.state != pausa.in_stato
            ):
                # Toccato mentre Home Assistant era fermo: vale quello che ha
                # fatto l'utente. Riacceso e' un ordine; spento resta spento.
                pausa = Pausa(forzato=acceso(macchina.state))
                self.esito[clima] = "cambiato a mano mentre Home Assistant era fermo"
            self.pause[clima] = pausa

        sensori = sorted({s for elenco in self.aperture.values() for s in elenco})
        if sensori:
            self._unsub.append(
                async_track_state_change_event(self.hass, sensori, self._su_sensore)
            )
        self._unsub.append(
            async_track_state_change_event(self.hass, list(self.aperture), self._su_clima)
        )
        self._avviato = True

        # Dopo un riavvio: una pausa con le finestre ormai chiuse va chiusa,
        # un clima acceso con la finestra aperta va messo in pausa.
        for clima in self.aperture:
            self._rivaluta(clima)
        self._salva()
        self._notifica()

    @callback
    def async_ferma(self) -> None:
        for annulla in self._unsub:
            annulla()
        self._unsub.clear()
        for timer in (*self._timer_apertura.values(), *self._timer_chiusura.values()):
            timer()
        self._timer_apertura.clear()
        self._timer_chiusura.clear()
        self._avviato = False

    # -------------------------------------------------------------------------
    # Lettura
    # -------------------------------------------------------------------------
    def stato_di(self, clima: str) -> str:
        stati = []
        for sensore in self.aperture.get(clima, []):
            stato = self.hass.states.get(sensore)
            stati.append(stato.state if stato is not None else None)
        return stato_aperture(stati)

    def aperte_di(self, clima: str) -> list[str]:
        return [
            sensore
            for sensore in self.aperture.get(clima, [])
            if (stato := self.hass.states.get(sensore)) is not None and stato.state == "on"
        ]

    def in_pausa(self, clima: str) -> bool:
        pausa = self.pause.get(clima)
        return pausa is not None and pausa.attiva

    def pausati(self) -> list[str]:
        return [clima for clima, pausa in self.pause.items() if pausa.attiva]

    def riaccendera(self, clima: str) -> bool:
        pausa = self.pause.get(clima)
        if pausa is None:
            return False
        return decidi_ripristino(pausa, dt_util.now(), self.riaccendi, self.limite)[0]

    # -------------------------------------------------------------------------
    # Comandi dall'utente
    # -------------------------------------------------------------------------
    @callback
    def set_abilitato(self, valore: bool) -> None:
        """Spento, le pause in corso si chiudono SENZA riaccendere nulla.

        Disattivare una sicurezza non deve avere come effetto collaterale di
        accendere macchine con le finestre aperte.
        """
        if valore == self.abilitato:
            return
        self.abilitato = valore
        if not valore:
            for clima in self.aperture:
                self._annulla_timer(clima)
                if self.pause[clima].attiva or self.pause[clima].forzato:
                    self.pause[clima] = Pausa()
                    self.esito[clima] = "pausa per aperture disattivata"
            self._salva()
        elif self._avviato:
            for clima in self.aperture:
                self._rivaluta(clima)
        self._notifica()

    @callback
    def non_riaccendere(self, clima: str) -> bool:
        pausa = self.pause.get(clima)
        if pausa is None or not pausa.attiva:
            return False
        pausa.non_riaccendere = True
        self.esito[clima] = "restera' spento alla chiusura"
        self._salva()
        self._notifica()
        return True

    # -------------------------------------------------------------------------
    # Ascolto
    # -------------------------------------------------------------------------
    @callback
    def _su_sensore(self, event: Event) -> None:
        sensore = event.data.get("entity_id")
        for clima, sensori in self.aperture.items():
            if sensore in sensori:
                self._rivaluta(clima)

    @callback
    def _su_clima(self, event: Event) -> None:
        clima = event.data.get("entity_id")
        if clima not in self.pause:
            return
        nuovo = event.data.get("new_state")
        vecchio = event.data.get("old_state")
        stato = nuovo.state if nuovo is not None else None
        stato_prima = vecchio.state if vecchio is not None else None
        if stato in INDISPONIBILI:
            return

        pausa = self.pause[clima]
        if pausa.attiva:
            if stato == pausa.in_stato:
                # Opera nostra, oppure la macchina che torna raggiungibile
                # nello stato in cui l'avevamo lasciata: se nel frattempo le
                # aperture si sono chiuse, si riprende da li'.
                if stato_prima in INDISPONIBILI:
                    self._rivaluta(clima)
                return
            if stato == SPENTO:
                # L'avevamo messa in ventilazione e l'utente l'ha spenta:
                # vuole che resti spenta.
                self.non_riaccendere(clima)
                return
            # Riaccesa a mano con l'apertura ancora aperta: e' un ordine.
            self._annulla_timer(clima)
            self.pause[clima] = Pausa(forzato=True)
            self.esito[clima] = "riacceso a mano con l'apertura aperta: resta acceso"
            _LOGGER.info("%s: %s riacceso a mano durante la pausa, lo si lascia", self.nome, clima)
            self._salva()
            self._rivaluta(clima)
            self._notifica()
            return

        if acceso(stato) and not acceso(stato_prima):
            # Acceso con l'apertura gia' aperta: vale la stessa regola, dopo
            # lo stesso ritardo.
            self._rivaluta(clima)
        elif not acceso(stato):
            self._annulla(self._timer_apertura, clima)

    # -------------------------------------------------------------------------
    # Tempo
    # -------------------------------------------------------------------------
    @callback
    def _rivaluta(self, clima: str) -> None:
        """Arma o disarma i due ritardi secondo lo stato attuale."""
        if not self.abilitato:
            return
        pausa = self.pause[clima]
        stato = self.stato_di(clima)

        if stato == APERTA:
            self._annulla(self._timer_chiusura, clima)
            if pausa.attiva or pausa.forzato:
                return
            macchina = self.hass.states.get(clima)
            if macchina is None or not acceso(macchina.state):
                return
            if clima not in self._timer_apertura:
                self._timer_apertura[clima] = async_call_later(
                    self.hass, self.ritardo_apertura, self._scade_apertura_per(clima)
                )
        elif stato == CHIUSA:
            self._annulla(self._timer_apertura, clima)
            if (pausa.attiva or pausa.forzato) and clima not in self._timer_chiusura:
                self._timer_chiusura[clima] = async_call_later(
                    self.hass, self.ritardo_chiusura, self._scade_chiusura_per(clima)
                )
        else:
            # Qualche sensore non risponde: si sospende ogni decisione.
            self._annulla_timer(clima)
            if pausa.attiva:
                self.esito[clima] = "un sensore non risponde: si aspetta"

    def _scade_apertura_per(self, clima: str):
        async def _scaduto(_adesso: datetime) -> None:
            self._timer_apertura.pop(clima, None)
            await self._async_metti_in_pausa(clima)

        return _scaduto

    def _scade_chiusura_per(self, clima: str):
        async def _scaduto(_adesso: datetime) -> None:
            self._timer_chiusura.pop(clima, None)
            await self._async_chiudi_pausa(clima)

        return _scaduto

    @callback
    def _annulla(self, timer: dict[str, CALLBACK_TYPE], clima: str) -> None:
        if (annulla := timer.pop(clima, None)) is not None:
            annulla()

    @callback
    def _annulla_timer(self, clima: str) -> None:
        self._annulla(self._timer_apertura, clima)
        self._annulla(self._timer_chiusura, clima)

    # -------------------------------------------------------------------------
    # Azioni
    # -------------------------------------------------------------------------
    async def _async_metti_in_pausa(self, clima: str) -> None:
        if not self.abilitato:
            return
        pausa = self.pause[clima]
        if pausa.attiva or pausa.forzato or self.stato_di(clima) != APERTA:
            return
        macchina = self.hass.states.get(clima)
        if macchina is None or not acceso(macchina.state):
            return

        modi = macchina.attributes.get("hvac_modes")
        destinazione = stato_in_pausa(self.azione, modi)
        # La pausa si registra PRIMA del comando: il cambio di stato che ne
        # segue deve gia' trovarla, o verrebbe letto come un gesto dell'utente.
        self.pause[clima] = Pausa(
            salvato=istantanea(macchina.state, dict(macchina.attributes)),
            dal=dt_util.now(),
            in_stato=destinazione,
        )
        if macchina.state != destinazione:
            servizio, dati = comando_pausa(destinazione, modi)
            if not await self._async_chiama(clima, servizio, dati):
                self.pause[clima] = Pausa()
                self.esito[clima] = "comando di pausa non riuscito"
                self._notifica()
                return

        aperte = ", ".join(self.aperte_di(clima)) or "apertura"
        self.esito[clima] = f"in pausa: {aperte} aperta"
        _LOGGER.info("%s: %s in pausa (%s aperta)", self.nome, clima, aperte)
        self._salva()
        self._notifica()

    async def _async_chiudi_pausa(self, clima: str) -> None:
        pausa = self.pause[clima]
        if self.stato_di(clima) != CHIUSA:
            return

        if not pausa.attiva:
            if pausa.forzato:
                # Tutto richiuso: il prossimo clima acceso con una finestra
                # aperta torna a seguire la regola.
                self.pause[clima] = Pausa()
                self._salva()
                self._notifica()
            return

        macchina = self.hass.states.get(clima)
        if macchina is None or macchina.state in INDISPONIBILI:
            # Si riprova quando torna raggiungibile (vedi _su_clima).
            self.esito[clima] = "clima non raggiungibile: si riaccende quando torna"
            self._notifica()
            return

        riaccendi, motivo = decidi_ripristino(pausa, dt_util.now(), self.riaccendi, self.limite)
        salvato = pausa.salvato or {}
        # La pausa si chiude PRIMA dei comandi, per la stessa ragione per cui
        # si apre prima: i cambi di stato che seguono non sono dell'utente.
        self.pause[clima] = Pausa()
        self.esito[clima] = f"aperture chiuse: {motivo}"
        self._salva()
        self._notifica()

        if not riaccendi:
            _LOGGER.info("%s: %s resta spento (%s)", self.nome, clima, motivo)
            return
        await self._async_ripristina(clima, salvato)

    async def _async_ripristina(self, clima: str, salvato: dict[str, Any]) -> None:
        self._al_ripristino(clima, salvato.get("temperature"))
        for giro in range(2):
            macchina = self.hass.states.get(clima)
            if macchina is None:
                return
            comandi = comandi_ripristino(salvato, macchina.state, dict(macchina.attributes))
            if not comandi:
                break
            for indice, (servizio, dati) in enumerate(comandi):
                if indice:
                    await asyncio.sleep(SPAZIATURA)
                if not await self._async_chiama(clima, servizio, dati):
                    return
            if giro == 0 and comandi[0][0] == "set_hvac_mode":
                await self._async_attendi_stato(clima, salvato.get("hvac_mode"))
                await asyncio.sleep(SPAZIATURA)
            else:
                break
        _LOGGER.info("%s: %s ripristinato com'era prima dell'apertura", self.nome, clima)

    async def _async_attendi_stato(self, clima: str, atteso: str | None) -> None:
        scadenza = self.hass.loop.time() + ATTESA_ACCENSIONE
        while self.hass.loop.time() < scadenza:
            macchina = self.hass.states.get(clima)
            if macchina is not None and macchina.state == atteso:
                return
            await asyncio.sleep(0.5)

    async def _async_chiama(self, clima: str, servizio: str, dati: dict[str, Any]) -> bool:
        try:
            await self.hass.services.async_call(
                "climate", servizio, {"entity_id": clima, **dati}, blocking=True
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("%s: %s su %s fallito: %s", self.nome, servizio, clima, err)
            return False
        return True

    # -------------------------------------------------------------------------
    # Memoria
    # -------------------------------------------------------------------------
    @callback
    def _salva(self) -> None:
        self._store.async_delay_save(self._dati_da_salvare, 1)

    @callback
    def _dati_da_salvare(self) -> dict[str, Any]:
        return {
            "pause": {
                clima: pausa.come_dati()
                for clima, pausa in self.pause.items()
                if pausa.attiva or pausa.forzato
            }
        }
