"""Switch: modulazione solare, e pausa per porte e finestre aperte."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, KEY_ABILITATO, KEY_APERTURE
from .controller import ClimaController
from .entity import ClimaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ClimaController = hass.data[DOMAIN][entry.entry_id]
    entita: list[Entity] = []
    if controller.modulazione:
        entita.append(AbilitazioneSwitch(controller))
    if controller.aperture is not None:
        entita.append(ApertureSwitch(controller))
    async_add_entities(entita)


class AbilitazioneSwitch(ClimaEntity, SwitchEntity, RestoreEntity):
    """Spento, la modulazione non tocca piu' la zona.

    I climatizzatori restano dove sono: disabilitare il controllo non e' un
    comando di spegnimento, e' un passo indietro. La pausa per le aperture ha
    il suo interruttore e continua a funzionare.
    """

    _attr_name = "Modulazione solare"
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


class ApertureSwitch(ClimaEntity, SwitchEntity, RestoreEntity):
    """Spento, porte e finestre aperte non fermano piu' i clima.

    Le pause in corso si chiudono senza riaccendere niente: disattivare una
    sicurezza non deve accendere macchine con le finestre aperte.
    """

    _attr_name = "Pausa per aperture"
    _attr_icon = "mdi:window-open-variant"

    def __init__(self, controller: ClimaController) -> None:
        super().__init__(controller, KEY_APERTURE)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (ultimo := await self.async_get_last_state()) is not None:
            self.controller.aperture.set_abilitato(ultimo.state == "on")

    @property
    def is_on(self) -> bool:
        return self.controller.aperture.abilitato

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.controller.aperture.set_abilitato(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.aperture.set_abilitato(False)
