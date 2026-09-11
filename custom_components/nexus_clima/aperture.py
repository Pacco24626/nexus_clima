"""Pausa dei climatizzatori a porta o finestra aperta: la parte che decide.

Niente Home Assistant qui dentro, come valuta() nel controller: stessi
ingressi, stessa uscita, e si prova a tavolino. Chi aspetta, ascolta e
comanda sta in gestore_aperture.py.

Ogni climatizzatore ha la sua pausa, fatta di cinque fatti:

- salvato: com'era quando l'abbiamo fermato, per rimetterlo cosi';
- dal: da quando e' fermo, per non riaccenderlo dopo un'assenza lunga;
- in_stato: lo stato in cui l'abbiamo messo. Un cambio verso quello stato e'
  opera nostra; verso qualunque altro e' dell'utente;
- non_riaccendere: chiesto dall'utente durante la pausa. Il clima e' gia'
  spento e spegnerlo di nuovo non cambia niente: serve un comando a parte;
- forzato: l'utente l'ha riacceso con l'apertura ancora aperta. E' un ordine,
  e vale finche' tutto non si richiude.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

APERTA = "aperta"
CHIUSA = "chiusa"
IGNOTA = "ignota"

SPENTO = "off"
VENTILAZIONE = "fan_only"
INDISPONIBILI = ("unavailable", "unknown", None)

AZIONE_SPEGNI = SPENTO
AZIONE_VENTILAZIONE = VENTILAZIONE

# Cio' che descrive come l'utente aveva impostato la macchina.
_CAMPI = (
    "temperature",
    "target_temp_low",
    "target_temp_high",
    "fan_mode",
    "swing_mode",
    "preset_mode",
)


@dataclass
class Pausa:
    """La pausa di un climatizzatore. Vuota quando non c'e' niente in corso."""

    salvato: dict[str, Any] | None = None
    dal: datetime | None = None
    in_stato: str | None = None
    non_riaccendere: bool = False
    forzato: bool = False

    @property
    def attiva(self) -> bool:
        return self.dal is not None

    def come_dati(self) -> dict[str, Any]:
        """Per lo storage: la pausa deve sopravvivere a un riavvio."""
        return {
            "salvato": dict(self.salvato) if self.salvato else None,
            "dal": self.dal.isoformat() if self.dal else None,
            "in_stato": self.in_stato,
            "non_riaccendere": self.non_riaccendere,
            "forzato": self.forzato,
        }

    @classmethod
    def da_dati(cls, dati: Any) -> Pausa:
        if not isinstance(dati, dict):
            return cls()
        dal = None
        if isinstance(dati.get("dal"), str):
            try:
                dal = datetime.fromisoformat(dati["dal"])
            except ValueError:
                dal = None
        salvato = dati.get("salvato") if isinstance(dati.get("salvato"), dict) else None
        if dal is not None and salvato is None:
            # Una pausa senza lo stato da ripristinare non serve a niente.
            dal = None
        return cls(
            salvato=salvato,
            dal=dal,
            in_stato=dati.get("in_stato") if dal else None,
            non_riaccendere=bool(dati.get("non_riaccendere")) and dal is not None,
            forzato=bool(dati.get("forzato")),
        )


def stato_aperture(stati: list[str | None]) -> str:
    """Lo stato complessivo delle aperture di un ambiente.

    Aperta se almeno una e' aperta. Ignota se nessuna e' aperta ma qualcuna
    non risponde: un gateway che si riavvia rende indisponibili tutte le zone
    insieme, e non deve riaccendere i clima con le finestre spalancate.
    """
    if any(stato == "on" for stato in stati):
        return APERTA
    if any(stato != "off" for stato in stati):
        return IGNOTA
    return CHIUSA


def acceso(stato: str | None) -> bool:
    return stato not in INDISPONIBILI and stato != SPENTO


def istantanea(stato: str, attributi: dict[str, Any]) -> dict[str, Any]:
    """Com'e' impostata la macchina adesso."""
    salvato: dict[str, Any] = {"hvac_mode": stato}
    for campo in _CAMPI:
        if attributi.get(campo) is not None:
            salvato[campo] = attributi[campo]
    return salvato


def stato_in_pausa(azione: str, modi: list[str] | None) -> str:
    """Dove mettere la macchina: in ventilazione solo se la sa fare."""
    if azione == AZIONE_VENTILAZIONE and VENTILAZIONE in (modi or []):
        return VENTILAZIONE
    return SPENTO


def comando_pausa(destinazione: str, modi: list[str] | None) -> tuple[str, dict[str, Any]]:
    """Il servizio che porta la macchina nello stato di pausa.

    Lo spegnimento passa da set_hvac_mode quando la macchina elenca 'off':
    turn_off esiste solo per chi dichiara la funzione, set_hvac_mode per
    chiunque abbia lo stato.
    """
    if destinazione == SPENTO and SPENTO not in (modi or []):
        return "turn_off", {}
    return "set_hvac_mode", {"hvac_mode": destinazione}


def decidi_ripristino(
    pausa: Pausa, adesso: datetime, riaccendi: bool, limite_minuti: int
) -> tuple[bool, str]:
    """Alla chiusura: si riaccende? E se no, perche'."""
    if not pausa.attiva or not pausa.salvato:
        return False, "nessuna pausa in corso"
    if not riaccendi:
        return False, "la riaccensione alla chiusura e' disattivata"
    if pausa.non_riaccendere:
        return False, "chiesto di non riaccendere"
    if limite_minuti > 0 and adesso - pausa.dal > timedelta(minutes=limite_minuti):
        return False, f"rimasto aperto piu' di {limite_minuti} min"
    return True, "ripristinato com'era"


def _diverso(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) >= 0.1
    return a != b


def comandi_ripristino(
    salvato: dict[str, Any], stato: str | None, attributi: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    """I comandi che mancano per tornare com'era, e solo quelli.

    Prima la modalita', da sola: finche' la macchina non l'ha presa, i suoi
    attributi descrivono ancora la macchina spenta e confrontarli non ha senso.
    Chi chiama rimanda la funzione dopo la conferma, e allora arriva il resto.

    Solo cio' che differisce, perche' molte macchine riaccese ricordano da
    sole setpoint e ventola, e alcune passano da un cloud con un tetto di
    chiamate al giorno.
    """
    modalita = salvato.get("hvac_mode")
    if modalita and stato != modalita:
        return [("set_hvac_mode", {"hvac_mode": modalita})]

    comandi: list[tuple[str, dict[str, Any]]] = []

    preset = salvato.get("preset_mode")
    if (
        preset is not None
        and preset in (attributi.get("preset_modes") or [])
        and _diverso(preset, attributi.get("preset_mode"))
    ):
        comandi.append(("set_preset_mode", {"preset_mode": preset}))

    temperatura = salvato.get("temperature")
    basso, alto = salvato.get("target_temp_low"), salvato.get("target_temp_high")
    if temperatura is not None:
        attuale = attributi.get("temperature")
        if attuale is None or _diverso(temperatura, attuale):
            comandi.append(("set_temperature", {"temperature": temperatura}))
    elif basso is not None and alto is not None:
        if _diverso(basso, attributi.get("target_temp_low")) or _diverso(
            alto, attributi.get("target_temp_high")
        ):
            comandi.append(
                ("set_temperature", {"target_temp_low": basso, "target_temp_high": alto})
            )

    for campo, elenco, servizio in (
        ("fan_mode", "fan_modes", "set_fan_mode"),
        ("swing_mode", "swing_modes", "set_swing_mode"),
    ):
        valore = salvato.get(campo)
        if (
            valore is not None
            and valore in (attributi.get(elenco) or [])
            and _diverso(valore, attributi.get(campo))
        ):
            comandi.append((servizio, {campo: valore}))

    return comandi
