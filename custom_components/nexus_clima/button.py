"""Bottone: restituisce il comando al controller dopo un intervento manuale."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_RIPRENDI
from .controller import ClimaController
from .entity import ClimaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ClimaController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RiprendiButton(controller)])


class RiprendiButton(ClimaEntity, ButtonEntity):
    """Chiude in anticipo la pausa aperta da un comando manuale.

    Senza questo si aspetterebbe la scadenza: comodo quando si e' alzato il
    setpoint per mezz'ora e si vuole tornare in automatico subito.
    """

    _attr_name = "Riprendi il controllo"
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, controller: ClimaController) -> None:
        super().__init__(controller, KEY_RIPRENDI)

    async def async_press(self) -> None:
        self.controller.riprendi()
