"""Bottoni: riprendere la modulazione, e non riaccendere dopo un'apertura."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_NON_RIACCENDERE, KEY_RIPRENDI
from .controller import ClimaController
from .entity import ClimaEntity, nome_clima

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ClimaController = hass.data[DOMAIN][entry.entry_id]
    entita: list[Entity] = []
    if controller.modulazione:
        entita.append(RiprendiButton(controller))
    if controller.aperture is not None:
        entita.extend(
            NonRiaccendereButton(controller, clima, nome_clima(hass, clima))
            for clima in controller.aperture.aperture
        )
    async_add_entities(entita)


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


class NonRiaccendereButton(ClimaEntity, ButtonEntity):
    """Durante una pausa per apertura: alla chiusura il clima resta spento.

    E' l'unico modo di dirlo. Il clima e' gia' spento, e spegnerlo di nuovo
    dal telecomando o dalla plancia non cambia il suo stato: non c'e' niente
    che l'integrazione possa leggere come «volevo proprio spegnerlo».
    """

    _attr_icon = "mdi:air-conditioner-off"

    def __init__(self, controller: ClimaController, clima: str, nome: str) -> None:
        super().__init__(controller, f"{KEY_NON_RIACCENDERE}_{clima}")
        self._clima = clima
        self._attr_name = f"Non riaccendere {nome}"

    async def async_press(self) -> None:
        if not self.controller.aperture.non_riaccendere(self._clima):
            _LOGGER.info(
                "%s: nessuna pausa in corso per %s, niente da annullare",
                self.controller.nome, self._clima,
            )
