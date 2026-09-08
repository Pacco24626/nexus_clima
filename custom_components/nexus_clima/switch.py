"""Switch: abilitazione della zona."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, KEY_ABILITATO
from .controller import ClimaController
from .entity import ClimaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ClimaController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AbilitazioneSwitch(controller)])


class AbilitazioneSwitch(ClimaEntity, SwitchEntity, RestoreEntity):
    """Spento, la zona non viene piu' toccata.

    I climatizzatori restano dove sono: disabilitare il controllo non e' un
    comando di spegnimento, e' un passo indietro.
    """

    _attr_name = "Abilitato"
    _attr_icon = "mdi:sun-snowflake-variant"

    def __init__(self, controller: ClimaController) -> None:
        super().__init__(controller, KEY_ABILITATO)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (ultimo := await self.async_get_last_state()) is not None:
            self.controller.set_abilitato(ultimo.state == "on")

    @property
    def is_on(self) -> bool:
        return self.controller.abilitato

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.controller.set_abilitato(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.set_abilitato(False)
