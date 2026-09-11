"""Sensori: stato del controllo, parametri appresi, rendiconto.

Il sensore di stato porta negli attributi il *motivo* della decisione. E' la
differenza fra un'automazione che si puo' correggere e una che si puo' solo
subire: a gennaio, davanti a un comportamento strano, il motivo dice perche'.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CAMPIONI_MINIMI,
    DOMAIN,
    KEY_DERIVA,
    KEY_PAVIMENTO,
    KEY_RENDICONTO,
    KEY_STATO,
)
from .controller import ClimaController
from .entity import ClimaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ClimaController = hass.data[DOMAIN][entry.entry_id]
    entita: list[SensorEntity] = [StatoSensor(controller)]
    # Senza sensore di rete la zona serve solo per le aperture: deriva e
    # rendiconto riguardano la modulazione e non avrebbero senso. Il pavimento
    # e' un concetto della sola modulazione continua.
    if controller.modulazione:
        entita.extend([DerivaSensor(controller), RendicontoSensor(controller)])
        if controller.soglie is None:
            entita.append(PavimentoSensor(controller))
    async_add_entities(entita)


class StatoSensor(ClimaEntity, SensorEntity):
    """Cosa sta facendo il controllo, e perche'."""

    _attr_name = "Stato"
    _attr_icon = "mdi:sun-thermometer-outline"

    def __init__(self, controller: ClimaController) -> None:
        super().__init__(controller, KEY_STATO)

    @property
    def native_value(self) -> str:
        return self.controller.stato

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.controller
        if c.soglie is not None:
            return {
                "motivo": c.motivo,
                **c.soglie.dettagli(),
                "temperatura": c.temperatura,
                "climi_accesi": c.climi_accesi,
                "in_pausa_per_apertura": c.aperture.pausati() if c.aperture is not None else [],
                "minuti_per_stato": {k: round(v) for k, v in c.minuti_stato.items()},
            }
        return {
            "motivo": c.motivo,
            "modalita": "continua",
            "setpoint_obiettivo": c.setpoint_obiettivo,
            "temperatura": c.temperatura,
            "temperatura_esterna": c.temperatura_esterna,
            "surplus_w": None if c.surplus is None else round(c.surplus),
            "potenza_stimata_w": round(c.potenza_stimata()),
            "ventilazione": c.ventola_corrente,
            "climi_accesi": c.climi_accesi,
            "in_pausa_per_apertura": c.aperture.pausati() if c.aperture is not None else [],
            "minuti_per_stato": {k: round(v) for k, v in c.minuti_stato.items()},
        }


class PavimentoSensor(ClimaEntity, SensorEntity):
    """Il minimo che la zona riesce davvero a tenere.

    Non e' il setpoint minimo dichiarato: e' dove la temperatura si ferma con
    la macchina a piena spinta. Sotto quel valore chiedere di piu' non
    raffresca, consuma soltanto.
    """

    _attr_name = "Pavimento raggiungibile"
    _attr_icon = "mdi:arrow-collapse-down"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, controller: ClimaController) -> None:
        super().__init__(controller, KEY_PAVIMENTO)

    @property
    def native_value(self) -> float | None:
        return self.controller.pavimento

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.controller
        return {
            "campioni": c.pavimento_campioni,
            "in_uso": c.pavimento_campioni >= CAMPIONI_MINIMI,
            "campioni_minimi": CAMPIONI_MINIMI,
        }


class DerivaSensor(ClimaEntity, SensorEntity):
    """Quanto sta salendo o scendendo la temperatura, in gradi all'ora."""

    _attr_name = "Deriva"
    _attr_icon = "mdi:chart-line-variant"
    _attr_native_unit_of_measurement = "°C/h"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, controller: ClimaController) -> None:
        super().__init__(controller, KEY_DERIVA)

    @property
    def native_value(self) -> float | None:
        return self.controller.deriva

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.controller
        return {
            "deriva_passiva": c.deriva_passiva,
            "campioni_passiva": c.deriva_passiva_campioni,
        }


class RendicontoSensor(ClimaEntity, SensorEntity):
    """Energia della zona e quota presa dal sole.

    Lo stato sono i kWh consumati oggi. Il valore in euro negli attributi non
    e' un risparmio rispetto a un mondo senza integrazione — quello non e'
    misurabile — ma quanto valgono in piu' della cessione i kWh autoconsumati.
    """

    _attr_name = "Energia della zona"
    _attr_icon = "mdi:solar-power-variant"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2

    def __init__(self, controller: ClimaController) -> None:
        super().__init__(controller, KEY_RENDICONTO)

    @property
    def native_value(self) -> float:
        return round(self.controller.energia_clima, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        c = self.controller
        quota = 0.0
        if c.energia_clima > 0:
            quota = round(100 * c.energia_surplus / c.energia_clima)
        return {
            "energia_da_surplus_kwh": round(c.energia_surplus, 3),
            "quota_da_surplus_pct": quota,
            "se_ceduti_eur": round(c.energia_surplus * c.prezzo_cessione, 2),
            "acquisto_evitato_eur": round(c.energia_surplus * c.prezzo_acquisto, 2),
            "differenza_eur": round(c.valore_differenza, 2),
            "misurata": c.sensore_potenza is not None,
        }
