"""Classe base delle entita' di una zona."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL
from .controller import ClimaController


def nome_clima(hass: HomeAssistant, entity_id: str) -> str:
    """Il nome con cui l'utente conosce il climatizzatore.

    All'avvio lo stato di un clima di un'altra integrazione puo' non esserci
    ancora: si ricade sul registro, e in ultimo sull'entity_id.
    """
    if (stato := hass.states.get(entity_id)) is not None:
        if nome := stato.attributes.get("friendly_name"):
            return str(nome)
    if (voce := er.async_get(hass).async_get(entity_id)) is not None:
        if nome := voce.name or voce.original_name:
            return str(nome)
    return entity_id.split(".", 1)[-1].replace("_", " ").capitalize()


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
