"""Controller di una zona climatica.

Quattro idee reggono questo file.

1. **Il compressore non si ferma mai per colpa nostra.** Un setpoint portato
   sotto la temperatura attuale non raffredda di piu': spegne la macchina,
   che poi deve ripartire da ferma. Un inverter rende quando gira in continuo
   a carico parziale, e tutto il resto della logica serve a tenerlo li'.

2. **Il segnale non deve muoversi quando agiamo.** Il bilancio di rete misurato
   contiene gia' il consumo del clima: se lo si usa cosi' com'e', accendere il
   clima peggiora il bilancio, che fa spegnere il clima, che migliora il
   bilancio. Si somma quindi la potenza che il clima sta assorbendo, e si
   ottiene un surplus che non cambia per effetto delle nostre decisioni.

3. **Spingere non serve se non immagazzina.** Sotto il pavimento raggiungibile
   la macchina va al massimo e la temperatura non scende: quell'energia non
   finisce in banca, e valeva di piu' ceduta alla rete.

4. **Il comando resta all'utente.** Un setpoint cambiato a mano e' un ordine,
   non un disturbo: il controller se ne accorge e si mette da parte.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_ACTION,
    ATTR_TEMPERATURE,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    STATE_OFF,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    ATTESA_CONFERMA,
    CAMPIONI_MINIMI,
    CONF_ACCOPPIATE,
    CONF_CARICA_A,
    CONF_CARICA_DA,
    CONF_CLIMI,
    CONF_COMFORT_A,
    CONF_COMFORT_DA,
    CONF_INTERVALLO,
    CONF_NOME,
    CONF_P_A_T_MAX,
    CONF_P_A_T_MIN,
    CONF_PASSO,
    CONF_PAUSA_MANUALE,
    CONF_PERMANENZA,
    CONF_PREZZO_ACQUISTO,
    CONF_PREZZO_CESSIONE,
    CONF_RETE_POSITIVA_IMPORT,
    CONF_SENSORE_ESTERNA,
    CONF_SENSORE_POTENZA,
    CONF_SENSORE_RETE,
    CONF_SENSORE_TEMP,
    CONF_T_COMFORT,
    CONF_T_MAX,
    CONF_T_MIN,
    CONF_USA_VENTOLA,
    CONF_VENTOLA_BASE,
    CONF_VENTOLA_SPINTA,
    DEFAULT_COMFORT_A,
    DEFAULT_COMFORT_DA,
    DEFAULT_INTERVALLO,
    DEFAULT_P_A_T_MAX,
    DEFAULT_P_A_T_MIN,
    DEFAULT_PASSO,
    DEFAULT_PAUSA_MANUALE,
    DEFAULT_PERMANENZA,
    DEFAULT_PREZZO_ACQUISTO,
    DEFAULT_PREZZO_CESSIONE,
    DEFAULT_T_COMFORT,
    DEFAULT_T_MAX,
    DEFAULT_T_MIN,
    DEFAULT_VENTOLA_BASE,
    DERIVA_DEBOLE,
    FINESTRA_DERIVA,
    ISTERESI,
    MARGINE_PAVIMENTO,
    MARGINE_SOTTO,
    MINUTI_PLATEAU,
    PESO_APPRENDIMENTO,
    RITENTATIVI,
    SPAZIATURA,
    STATO_CARICA,
    STATO_COMFORT,
    STATO_DISABILITATO,
    STATO_FUORI,
    STATO_MANUALE,
    STATO_NON_PRONTO,
)

_LOGGER = logging.getLogger(__name__)

INDISPONIBILI = (STATE_UNAVAILABLE, STATE_UNKNOWN, None)


@dataclass
class Decisione:
    """Cosa fare adesso, e perche'.

    Il "perche'" non e' decorativo: e' quello che permette di capire il
    comportamento senza rileggere il codice a gennaio.
    """

    stato: str
    motivo: str
    setpoint: float | None = None
    ventola: str | None = None


class ClimaController:
    """Modula una zona climatica sul surplus fotovoltaico."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        cfg = {**entry.data, **entry.options}
        self.nome: str = cfg.get(CONF_NOME, entry.title)
        self.climi: list[str] = list(cfg.get(CONF_CLIMI) or [])
        self.accoppiate: list[str] = list(cfg.get(CONF_ACCOPPIATE) or [])

        self.sensore_rete: str | None = cfg.get(CONF_SENSORE_RETE)
        self.rete_positiva_import: bool = bool(cfg.get(CONF_RETE_POSITIVA_IMPORT, True))
        self.sensore_temp: str | None = cfg.get(CONF_SENSORE_TEMP)
        self.sensore_esterna: str | None = cfg.get(CONF_SENSORE_ESTERNA)
        self.sensore_potenza: str | None = cfg.get(CONF_SENSORE_POTENZA)

        self.t_min: float = float(cfg.get(CONF_T_MIN, DEFAULT_T_MIN))
        self.t_comfort: float = float(cfg.get(CONF_T_COMFORT, DEFAULT_T_COMFORT))
        self.t_max: float = float(cfg.get(CONF_T_MAX, DEFAULT_T_MAX))

        self.p_a_t_min: float = float(cfg.get(CONF_P_A_T_MIN, DEFAULT_P_A_T_MIN))
        self.p_a_t_max: float = float(cfg.get(CONF_P_A_T_MAX, DEFAULT_P_A_T_MAX))

        self.carica_da: str | None = cfg.get(CONF_CARICA_DA)
        self.carica_a: str | None = cfg.get(CONF_CARICA_A)
        self.comfort_da: str = cfg.get(CONF_COMFORT_DA) or DEFAULT_COMFORT_DA
        self.comfort_a: str = cfg.get(CONF_COMFORT_A) or DEFAULT_COMFORT_A

        self.permanenza: int = int(cfg.get(CONF_PERMANENZA, DEFAULT_PERMANENZA))
        self.passo: float = float(cfg.get(CONF_PASSO, DEFAULT_PASSO))
        self.intervallo: int = int(cfg.get(CONF_INTERVALLO, DEFAULT_INTERVALLO))

        self.usa_ventola: bool = bool(cfg.get(CONF_USA_VENTOLA, True))
        self.ventola_base: str = cfg.get(CONF_VENTOLA_BASE) or DEFAULT_VENTOLA_BASE
        self.ventola_spinta: str | None = cfg.get(CONF_VENTOLA_SPINTA)

        self.pausa_manuale: int = int(cfg.get(CONF_PAUSA_MANUALE, DEFAULT_PAUSA_MANUALE))
        self.prezzo_acquisto: float = float(
            cfg.get(CONF_PREZZO_ACQUISTO, DEFAULT_PREZZO_ACQUISTO)
        )
        self.prezzo_cessione: float = float(
            cfg.get(CONF_PREZZO_CESSIONE, DEFAULT_PREZZO_CESSIONE)
        )

        # Stato corrente
        self.abilitato: bool = True
        self.stato: str = STATO_NON_PRONTO
        self.motivo: str = "in avvio"
        self.setpoint_obiettivo: float | None = None
        self.surplus: float | None = None
        self.ventola_corrente: str | None = None

        # Parametri appresi
        self.pavimento: float | None = None
        self.pavimento_campioni: int = 0
        self.deriva: float | None = None
        self.deriva_passiva: float | None = None
        self.deriva_passiva_campioni: int = 0

        # Contabilita' della giornata
        self.energia_clima: float = 0.0
        self.energia_surplus: float = 0.0
        self.minuti_stato: dict[str, float] = {}

        # Interno
        self._comandato: dict[str, float] = {}
        self._sto_comandando: bool = False
        self._ultimo_cambio: datetime | None = None
        self._manuale_fino: datetime | None = None
        self._storia_temp: deque[tuple[datetime, float]] = deque(maxlen=240)
        self._plateau_da: datetime | None = None
        self._ultimo_conteggio: datetime | None = None
        self._unsub: list[CALLBACK_TYPE] = []
        self._listeners: list[CALLBACK_TYPE] = []

    # -------------------------------------------------------------------------
    # Ciclo di vita
    # -------------------------------------------------------------------------
    async def async_setup(self) -> None:
        self._unsub.append(
            async_track_time_interval(
                self.hass, self._async_ciclo, timedelta(seconds=self.intervallo)
            )
        )
        self._unsub.append(
            async_track_time_change(self.hass, self._async_nuovo_giorno, hour=0, minute=0, second=10)
        )
        if self.climi:
            self._unsub.append(
                async_track_state_change_event(self.hass, self.climi, self._async_clima_cambiato)
            )

        if self.hass.is_running:
            await self._async_avvia()
        else:
            self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, self._async_avvio_ritardato
            )

    async def _async_avvio_ritardato(self, _event: Event) -> None:
        await self._async_avvia()

    async def _async_avvia(self) -> None:
        # Si parte allineati a cio' che le macchine hanno adesso, cosi' un
        # riavvio non viene scambiato per un comando manuale.
        for entity_id in self.climi:
            if (valore := self._setpoint_di(entity_id)) is not None:
                self._comandato[entity_id] = valore
        await self._async_ciclo(dt_util.now())

    async def async_shutdown(self) -> None:
        for annulla in self._unsub:
            annulla()
        self._unsub.clear()

    @callback
    def async_add_listener(self, update: CALLBACK_TYPE) -> CALLBACK_TYPE:
        self._listeners.append(update)

        @callback
        def _rimuovi() -> None:
            self._listeners.remove(update)

        return _rimuovi

    @callback
    def notify(self) -> None:
        for update in list(self._listeners):
            update()

    @callback
    def set_abilitato(self, valore: bool) -> None:
        self.abilitato = valore
        self.notify()

    @callback
    def riprendi(self) -> None:
        """Restituisce il comando al controller dopo un intervento manuale."""
        self._manuale_fino = None
        for entity_id in self.climi:
            if (valore := self._setpoint_di(entity_id)) is not None:
                self._comandato[entity_id] = valore
        self.notify()

    # -------------------------------------------------------------------------
    # Lettura dell'impianto
    # -------------------------------------------------------------------------
    def _numero(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        stato = self.hass.states.get(entity_id)
        if stato is None or stato.state in INDISPONIBILI:
            return None
        try:
            return float(stato.state)
        except (TypeError, ValueError):
            return None

    def _attributo(self, entity_id: str, chiave: str) -> Any:
        stato = self.hass.states.get(entity_id)
        if stato is None or stato.state in INDISPONIBILI:
            return None
        return stato.attributes.get(chiave)

    def _setpoint_di(self, entity_id: str) -> float | None:
        valore = self._attributo(entity_id, ATTR_TEMPERATURE)
        try:
            return float(valore) if valore is not None else None
        except (TypeError, ValueError):
            return None

    @property
    def temperatura(self) -> float | None:
        """La temperatura della zona: sonda dedicata se dichiarata, altrimenti
        quella riportata dal primo clima."""
        if (valore := self._numero(self.sensore_temp)) is not None:
            return valore
        for entity_id in self.climi:
            valore = self._attributo(entity_id, ATTR_CURRENT_TEMPERATURE)
            if valore is not None:
                try:
                    return float(valore)
                except (TypeError, ValueError):
                    continue
        return None

    @property
    def temperatura_esterna(self) -> float | None:
        return self._numero(self.sensore_esterna)

    @property
    def climi_accesi(self) -> list[str]:
        accesi = []
        for entity_id in self.climi:
            stato = self.hass.states.get(entity_id)
            if stato is not None and stato.state not in INDISPONIBILI and stato.state != STATE_OFF:
                accesi.append(entity_id)
        return accesi

    def potenza_stimata(self, setpoint: float | None = None) -> float:
        """Potenza assorbita dalla zona.

        Con un contatore dedicato e' una misura. Senza, e' l'interpolazione
        fra i due valori dichiarati agli estremi del range: grezza, ma
        sufficiente a rendere il surplus insensibile alle nostre decisioni,
        che e' l'uso per cui serve.
        """
        if (misurata := self._numero(self.sensore_potenza)) is not None:
            return misurata

        if not self.climi_accesi:
            return 0.0

        if setpoint is None:
            valori = [s for e in self.climi if (s := self._setpoint_di(e)) is not None]
            setpoint = min(valori) if valori else self.t_max

        if self.t_max <= self.t_min:
            return self.p_a_t_min

        frazione = (self.t_max - setpoint) / (self.t_max - self.t_min)
        frazione = max(0.0, min(1.0, frazione))
        return self.p_a_t_max + frazione * (self.p_a_t_min - self.p_a_t_max)

    def _import_rete(self) -> float | None:
        """Prelievo dalla rete in watt: positivo se si importa."""
        valore = self._numero(self.sensore_rete)
        if valore is None:
            return None
        return valore if self.rete_positiva_import else -valore

    # -------------------------------------------------------------------------
    # Finestre
    # -------------------------------------------------------------------------
    @staticmethod
    def _ora(testo: str | None) -> time | None:
        if not testo:
            return None
        try:
            parti = [int(p) for p in testo.split(":")]
        except ValueError:
            return None
        while len(parti) < 3:
            parti.append(0)
        return time(parti[0], parti[1], parti[2])

    def _dentro(self, adesso: time, da: str | None, a: str | None) -> bool:
        inizio, fine = self._ora(da), self._ora(a)
        if inizio is None or fine is None:
            return False
        if inizio <= fine:
            return inizio <= adesso <= fine
        # Finestra che scavalca la mezzanotte, come una zona notte.
        return adesso >= inizio or adesso <= fine

    def finestra(self, adesso: datetime) -> str:
        ora = adesso.time()
        if self._dentro(ora, self.carica_da, self.carica_a):
            return STATO_CARICA
        if self._dentro(ora, self.comfort_da, self.comfort_a):
            return STATO_COMFORT
        return STATO_FUORI

    # -------------------------------------------------------------------------
    # La decisione
    # -------------------------------------------------------------------------
    def valuta(self, adesso: datetime | None = None) -> Decisione:
        """Cosa fare adesso. Non tocca nulla: si limita a decidere.

        Tenuta pura di proposito, cosi' e' verificabile a tavolino e il motivo
        che restituisce e' l'unica spiegazione di cui c'e' bisogno.
        """
        adesso = adesso or dt_util.now()

        if not self.abilitato:
            return Decisione(STATO_DISABILITATO, "zona disabilitata")

        if self._manuale_fino is not None and adesso < self._manuale_fino:
            resta = int((self._manuale_fino - adesso).total_seconds() // 60)
            return Decisione(STATO_MANUALE, f"comando manuale, riprende fra {resta} min")

        if not self.climi_accesi:
            return Decisione(STATO_NON_PRONTO, "nessun clima acceso in questa zona")

        finestra = self.finestra(adesso)
        if finestra == STATO_FUORI:
            return Decisione(STATO_FUORI, "fuori dalle finestre dichiarate")

        temperatura = self.temperatura
        if temperatura is None:
            return Decisione(STATO_NON_PRONTO, "temperatura della zona non disponibile")

        importato = self._import_rete()
        if importato is None:
            return Decisione(STATO_NON_PRONTO, "sensore di rete non disponibile")

        # Passo 1: il surplus che non si muove quando agiamo.
        potenza = self.potenza_stimata()
        surplus = -importato + potenza
        self.surplus = surplus

        # Passo 2: dal surplus al setpoint obiettivo.
        pavimento_richiesto = self.t_min if finestra == STATO_CARICA else self.t_comfort
        corsa = self.t_max - pavimento_richiesto
        if corsa <= 0:
            obiettivo = self.t_max
        else:
            denominatore = self.p_a_t_min - self.p_a_t_max
            if denominatore <= 0:
                frazione = 0.0
            else:
                frazione = (surplus - self.p_a_t_max) / denominatore
            frazione = max(0.0, min(1.0, frazione))
            obiettivo = self.t_max - frazione * corsa

        motivo = f"surplus {surplus:.0f} W in finestra {finestra}"

        # Passo 3: il cancello di utilita' termica.
        if (
            self.pavimento is not None
            and self.pavimento_campioni >= CAMPIONI_MINIMI
            and obiettivo < self.pavimento - MARGINE_PAVIMENTO
            and temperatura <= self.pavimento + MARGINE_PAVIMENTO
        ):
            obiettivo = max(obiettivo, self.pavimento - MARGINE_PAVIMENTO)
            motivo = f"al pavimento appreso ({self.pavimento:.1f} °C), scendere non immagazzina"

        # Passo 4: la prova della derivata. Se stiamo gia' spingendo e la
        # temperatura non scende, il problema non e' il setpoint.
        if (
            self.deriva is not None
            and abs(self.deriva) < DERIVA_DEBOLE
            and obiettivo < temperatura - MARGINE_SOTTO
        ):
            motivo = f"deriva ferma a {self.deriva:+.2f} °C/h: la zona non assorbe di piu'"

        # Passo 5: non fermare mai il compressore, e rispettare gli accoppiamenti.
        obiettivo = max(obiettivo, temperatura - MARGINE_SOTTO)
        obiettivo = min(max(obiettivo, pavimento_richiesto), self.t_max)

        if (limite := self._limite_accoppiate()) is not None and obiettivo < limite:
            obiettivo = limite
            motivo = "allineato alle zone accoppiate"

        # Passo 6: isteresi, passo massimo, permanenza minima.
        attuale = min(
            (s for e in self.climi_accesi if (s := self._setpoint_di(e)) is not None),
            default=None,
        )
        if attuale is not None:
            if abs(obiettivo - attuale) < ISTERESI:
                obiettivo = attuale
            else:
                if not self._permanenza_scaduta(adesso):
                    resta = self._minuti_alla_permanenza(adesso)
                    return Decisione(
                        finestra,
                        f"{motivo}; fermo per permanenza minima ({resta} min)",
                        setpoint=attuale,
                        ventola=self._ventola_per(surplus),
                    )
                delta = max(-self.passo, min(self.passo, obiettivo - attuale))
                obiettivo = attuale + delta

        obiettivo = round(obiettivo)
        return Decisione(finestra, motivo, setpoint=float(obiettivo), ventola=self._ventola_per(surplus))

    def _limite_accoppiate(self) -> float | None:
        """Non piu' di un grado sotto le zone che condividono il volume.

        Con le porte aperte due macchine con setpoint diversi non collaborano:
        la piu' fredda lavora per tutta la casa a pieno regime, e l'altra sta
        ferma. Due macchine a carico parziale spostano lo stesso calore
        consumando meno.
        """
        valori = [s for e in self.accoppiate if (s := self._setpoint_di(e)) is not None]
        if not valori:
            return None
        return min(valori) - 1.0

    def _permanenza_scaduta(self, adesso: datetime) -> bool:
        if self._ultimo_cambio is None:
            return True
        return adesso - self._ultimo_cambio >= timedelta(minutes=self.permanenza)

    def _minuti_alla_permanenza(self, adesso: datetime) -> int:
        if self._ultimo_cambio is None:
            return 0
        resta = timedelta(minutes=self.permanenza) - (adesso - self._ultimo_cambio)
        return max(0, int(resta.total_seconds() // 60))

    def _ventola_per(self, surplus: float) -> str | None:
        """La regolazione veloce: piu' surplus, piu' portata.

        Cambiare la ventilazione non puo' fermare il compressore, quindi si
        muove liberamente e senza permanenza minima.
        """
        if not self.usa_ventola:
            return None
        if self.ventola_spinta and surplus >= self.p_a_t_min:
            return self.ventola_spinta
        return self.ventola_base

    # -------------------------------------------------------------------------
    # Applicazione
    # -------------------------------------------------------------------------
    async def _async_ciclo(self, adesso: datetime | None = None) -> None:
        adesso = adesso or dt_util.now()

        self._aggiorna_storia(adesso)
        self._aggiorna_apprendimento(adesso)
        self._aggiorna_contabilita(adesso)

        decisione = self.valuta(adesso)
        self.stato = decisione.stato
        self.motivo = decisione.motivo
        self.setpoint_obiettivo = decisione.setpoint

        if decisione.setpoint is not None:
            await self._async_applica(decisione)

        self.notify()

    async def _async_applica(self, decisione: Decisione) -> None:
        self._sto_comandando = True
        try:
            primo = True
            for entity_id in self.climi_accesi:
                if not primo:
                    await asyncio.sleep(SPAZIATURA)
                primo = False

                if decisione.ventola:
                    await self._async_ventola(entity_id, decisione.ventola)

                attuale = self._setpoint_di(entity_id)
                if attuale is None or abs(attuale - decisione.setpoint) >= 0.5:
                    await self._async_setpoint(entity_id, decisione.setpoint)
        finally:
            # Un giro di eventi perche' gli stati commentino, poi si riapre
            # il rilevamento del comando manuale.
            await asyncio.sleep(0)
            self._sto_comandando = False

    async def _async_setpoint(self, entity_id: str, valore: float) -> None:
        for tentativo in range(1, RITENTATIVI + 1):
            try:
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    SERVICE_SET_TEMPERATURE,
                    {"entity_id": entity_id, ATTR_TEMPERATURE: valore},
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("%s: comando su %s fallito: %s", self.nome, entity_id, err)
                return

            self._comandato[entity_id] = valore
            if await self._async_conferma(entity_id, valore):
                self._ultimo_cambio = dt_util.now()
                if tentativo > 1:
                    _LOGGER.info(
                        "%s: %s ha accettato il setpoint al tentativo %s",
                        self.nome, entity_id, tentativo,
                    )
                return

        _LOGGER.warning(
            "%s: %s non ha confermato il setpoint %.1f dopo %s tentativi",
            self.nome, entity_id, valore, RITENTATIVI,
        )

    async def _async_conferma(self, entity_id: str, valore: float) -> bool:
        scadenza = self.hass.loop.time() + ATTESA_CONFERMA
        while self.hass.loop.time() < scadenza:
            attuale = self._setpoint_di(entity_id)
            if attuale is not None and abs(attuale - valore) < 0.5:
                return True
            await asyncio.sleep(0.5)
        return False

    async def _async_ventola(self, entity_id: str, modalita: str) -> None:
        disponibili = self._attributo(entity_id, ATTR_FAN_MODES) or []
        if modalita not in disponibili:
            return
        if self._attributo(entity_id, ATTR_FAN_MODE) == modalita:
            return
        try:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_FAN_MODE,
                {"entity_id": entity_id, ATTR_FAN_MODE: modalita},
                blocking=True,
            )
            self.ventola_corrente = modalita
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("%s: ventilazione su %s fallita: %s", self.nome, entity_id, err)

    # -------------------------------------------------------------------------
    # Comando manuale
    # -------------------------------------------------------------------------
    async def _async_clima_cambiato(self, event: Event) -> None:
        """Un setpoint che non abbiamo scritto noi e' un ordine dell'utente."""
        if self._sto_comandando or not self.abilitato:
            return

        entity_id = event.data.get("entity_id")
        nuovo = event.data.get("new_state")
        if entity_id is None or nuovo is None or nuovo.state in INDISPONIBILI:
            return

        valore = nuovo.attributes.get(ATTR_TEMPERATURE)
        if valore is None:
            return
        try:
            valore = float(valore)
        except (TypeError, ValueError):
            return

        atteso = self._comandato.get(entity_id)
        if atteso is not None and abs(valore - atteso) < 0.5:
            return

        self._comandato[entity_id] = valore
        if self.pausa_manuale > 0:
            self._manuale_fino = dt_util.now() + timedelta(minutes=self.pausa_manuale)
        else:
            domani = dt_util.now() + timedelta(days=1)
            self._manuale_fino = domani.replace(hour=0, minute=0, second=0, microsecond=0)

        _LOGGER.info(
            "%s: setpoint di %s portato a %.1f a mano, il controllo si ferma fino alle %s",
            self.nome, entity_id, valore, self._manuale_fino.strftime("%H:%M"),
        )
        self.stato = STATO_MANUALE
        self.motivo = f"setpoint portato a {valore:.0f} °C a mano"
        self.notify()

    # -------------------------------------------------------------------------
    # Apprendimento
    # -------------------------------------------------------------------------
    def _aggiorna_storia(self, adesso: datetime) -> None:
        if (temperatura := self.temperatura) is not None:
            self._storia_temp.append((adesso, temperatura))

    def _calcola_deriva(self, adesso: datetime) -> float | None:
        """Gradi all'ora sulla finestra recente, per regressione ai minimi quadrati."""
        limite = adesso - timedelta(minutes=FINESTRA_DERIVA)
        punti = [(t, x) for t, x in self._storia_temp if t >= limite]
        if len(punti) < 3:
            return None

        base = punti[0][0]
        xs = [(t - base).total_seconds() / 3600.0 for t, _ in punti]
        ys = [x for _, x in punti]
        n = len(punti)
        media_x = sum(xs) / n
        media_y = sum(ys) / n
        numeratore = sum((x - media_x) * (y - media_y) for x, y in zip(xs, ys))
        denominatore = sum((x - media_x) ** 2 for x in xs)
        if denominatore <= 0:
            return None
        return numeratore / denominatore

    def _aggiorna_apprendimento(self, adesso: datetime) -> None:
        self.deriva = self._calcola_deriva(adesso)
        temperatura = self.temperatura
        if temperatura is None or self.deriva is None:
            self._plateau_da = None
            return

        setpoint = min(
            (s for e in self.climi_accesi if (s := self._setpoint_di(e)) is not None),
            default=None,
        )

        # Il pavimento: la macchina chiede piu' di quanto riesca a dare, e la
        # temperatura non scende piu'. E' quel valore, non il setpoint.
        spinta_piena = setpoint is not None and setpoint < temperatura - MARGINE_PAVIMENTO
        if spinta_piena and abs(self.deriva) < DERIVA_DEBOLE:
            if self._plateau_da is None:
                self._plateau_da = adesso
            elif adesso - self._plateau_da >= timedelta(minutes=MINUTI_PLATEAU):
                self._registra_pavimento(temperatura)
                self._plateau_da = adesso
        else:
            self._plateau_da = None

        # La deriva passiva: quanto tiene il freddo quando nessuno raffresca.
        if not self.climi_accesi and self.deriva is not None and self.deriva > 0:
            self.deriva_passiva = self._media(self.deriva_passiva, self.deriva)
            self.deriva_passiva_campioni += 1

    def _registra_pavimento(self, valore: float) -> None:
        self.pavimento = self._media(self.pavimento, valore)
        self.pavimento_campioni += 1
        _LOGGER.debug(
            "%s: pavimento aggiornato a %.2f °C (%d campioni)",
            self.nome, self.pavimento, self.pavimento_campioni,
        )

    @staticmethod
    def _media(precedente: float | None, nuovo: float) -> float:
        if precedente is None:
            return nuovo
        return precedente * (1 - PESO_APPRENDIMENTO) + nuovo * PESO_APPRENDIMENTO

    # -------------------------------------------------------------------------
    # Contabilita'
    # -------------------------------------------------------------------------
    def _aggiorna_contabilita(self, adesso: datetime) -> None:
        """Energia della zona e quota coperta dal fotovoltaico.

        La regola per la quota e' semplice e difendibile: se in quell'istante
        la casa non stava importando, il consumo del clima era coperto; se
        stava importando X, era coperto per quello che eccede X.
        """
        precedente = self._ultimo_conteggio
        self._ultimo_conteggio = adesso
        if precedente is None:
            return

        ore = (adesso - precedente).total_seconds() / 3600.0
        if ore <= 0 or ore > 1:
            return

        potenza = self.potenza_stimata()
        if potenza <= 0:
            return

        self.energia_clima += potenza * ore / 1000.0

        importato = self._import_rete()
        if importato is None:
            return
        coperta = potenza if importato <= 0 else max(0.0, potenza - importato)
        self.energia_surplus += coperta * ore / 1000.0

        self.minuti_stato[self.stato] = self.minuti_stato.get(self.stato, 0.0) + ore * 60.0

    @property
    def valore_differenza(self) -> float:
        """I kWh autoconsumati, valutati alla differenza fra i due prezzi.

        Non e' un risparmio rispetto a un mondo senza integrazione: e' quanto
        valgono, in piu' della cessione, i kWh che il clima ha preso dal sole.
        """
        return self.energia_surplus * (self.prezzo_acquisto - self.prezzo_cessione)

    async def _async_nuovo_giorno(self, _adesso: datetime) -> None:
        self.energia_clima = 0.0
        self.energia_surplus = 0.0
        self.minuti_stato = {}
        self.notify()
