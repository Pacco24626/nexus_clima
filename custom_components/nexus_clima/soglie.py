"""Modulazione a soglie: la parte che decide.

Il modello e' quello che l'utente conosce gia': comfort o eco.

- Il **comfort** non lo decide l'integrazione: e' il setpoint e la ventola che
  l'utente ha impostato sul clima.
- L'**eco** e' una temperatura e una ventilazione scelte nelle opzioni.
- Si passa in eco quando si preleva dalla rete oltre una soglia per un certo
  tempo; si torna al comfort quando si cede oltre un'altra soglia per un altro
  tempo, rimettendo esattamente cio' che c'era.

Mai accendere, mai spegnere: si tocca solo un clima che l'utente ha acceso in
raffrescamento con un setpoint piu' basso dell'eco.

Una correzione rispetto all'automazione classica: per tornare al comfort la
cessione deve coprire anche il consumo in piu' del clima al comfort. Senza,
se il margine fra le due soglie e' piu' stretto di quel consumo, il ritorno al
comfort fa scattare da solo il ritorno in eco, e il clima fa il ping-pong.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

RAFFRESCAMENTO = "cool"


@dataclass
class Eco:
    """Un clima messo in eco, con il comfort da rimettere."""

    comfort_temp: float
    comfort_ventola: str | None
    dal: datetime

    def come_dati(self) -> dict[str, Any]:
        return {
            "comfort_temp": self.comfort_temp,
            "comfort_ventola": self.comfort_ventola,
            "dal": self.dal.isoformat(),
        }

    @classmethod
    def da_dati(cls, dati: Any) -> Eco | None:
        if not isinstance(dati, dict):
            return None
        try:
            return cls(
                comfort_temp=float(dati["comfort_temp"]),
                comfort_ventola=dati.get("comfort_ventola"),
                dal=datetime.fromisoformat(dati["dal"]),
            )
        except (KeyError, TypeError, ValueError):
            return None


def _numero(valore: Any) -> float | None:
    try:
        return float(valore) if valore is not None else None
    except (TypeError, ValueError):
        return None


def candidato(stato: str | None, attributi: dict[str, Any], eco_temp: float) -> bool:
    """Un clima su cui l'eco ha senso: acceso in raffrescamento, piu' freddo dell'eco.

    Uno impostato gia' all'eco o sopra non si tocca: portarlo all'eco vorrebbe
    dire raffrescare di piu', non di meno.
    """
    if stato != RAFFRESCAMENTO:
        return False
    setpoint = _numero(attributi.get("temperature"))
    return setpoint is not None and setpoint <= eco_temp - 0.5


def come_lasciato(attributi: dict[str, Any], eco_temp: float, eco_ventola: str | None) -> bool:
    """Il clima e' ancora come l'abbiamo messo in eco? Se no, l'ha toccato l'utente."""
    setpoint = _numero(attributi.get("temperature"))
    if setpoint is None or abs(setpoint - eco_temp) >= 0.5:
        return False
    if eco_ventola and eco_ventola in (attributi.get("fan_modes") or []):
        return attributi.get("fan_mode") == eco_ventola
    return True


def comandi_eco(
    attributi: dict[str, Any], eco_temp: float, eco_ventola: str | None
) -> list[tuple[str, dict[str, Any]]]:
    """Cio' che serve per portare il clima in eco, e solo quello."""
    comandi: list[tuple[str, dict[str, Any]]] = []
    setpoint = _numero(attributi.get("temperature"))
    if setpoint is None or abs(setpoint - eco_temp) >= 0.5:
        comandi.append(("set_temperature", {"temperature": eco_temp}))
    if (
        eco_ventola
        and eco_ventola in (attributi.get("fan_modes") or [])
        and attributi.get("fan_mode") != eco_ventola
    ):
        comandi.append(("set_fan_mode", {"fan_mode": eco_ventola}))
    return comandi


def comandi_comfort(eco: Eco, attributi: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Cio' che serve per rimettere il comfort che c'era."""
    comandi: list[tuple[str, dict[str, Any]]] = []
    setpoint = _numero(attributi.get("temperature"))
    if setpoint is None or abs(setpoint - eco.comfort_temp) >= 0.5:
        comandi.append(("set_temperature", {"temperature": eco.comfort_temp}))
    if (
        eco.comfort_ventola
        and eco.comfort_ventola in (attributi.get("fan_modes") or [])
        and attributi.get("fan_mode") != eco.comfort_ventola
    ):
        comandi.append(("set_fan_mode", {"fan_mode": eco.comfort_ventola}))
    return comandi


def soglia_ritorno(soglia_cessione: float, consumo_in_piu: float, climi_in_eco: int) -> float:
    """La cessione che serve per tornare al comfort senza farsi scattare da soli."""
    return soglia_cessione + consumo_in_piu * climi_in_eco


def trascorso(da: datetime | None, adesso: datetime, minuti: float) -> bool:
    return da is not None and adesso - da >= timedelta(minutes=minuti)


def minuti_mancanti(da: datetime | None, adesso: datetime, minuti: float) -> int:
    if da is None:
        return int(minuti)
    resta = timedelta(minutes=minuti) - (adesso - da)
    return max(0, int(-(-resta.total_seconds() // 60)))
