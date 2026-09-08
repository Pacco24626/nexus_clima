"""Classe base delle entita' di una zona."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL
from .controller import ClimaController


class ClimaEntity(Entity):
    """Entita' agganciata al controller della zona."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: ClimaController, chiave: str) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{chiave}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name=controller.nome,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))
