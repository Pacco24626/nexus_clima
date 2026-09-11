"""Sensori binari: un clima in pausa per porta o finestra aperta."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, KEY_PAUSA
from .controller import ClimaController
from .entity import ClimaEntity, nome_clima


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controller: ClimaController = hass.data[DOMAIN][entry.entry_id]
    if controller.aperture is None:
        return
    async_add_entities(
        PausaAperturaSensor(controller, clima, nome_clima(hass, clima))
        for clima in controller.aperture.aperture
    )


class PausaAperturaSensor(ClimaEntity, BinarySensorEntity):
    """Acceso finche' il clima e' fermo per un'apertura.

    Serve anche da condizione in plancia: il pulsante «Non riaccendere» ha
    senso solo mentre questo e' acceso.
    """

    _attr_icon = "mdi:window-open-variant"

    def __init__(self, controller: ClimaController, clima: str, nome: str) -> None:
        super().__init__(controller, f"{KEY_PAUSA}_{clima}")
        self._clima = clima
        self._attr_name = f"Pausa {nome}"

    @property
    def is_on(self) -> bool:
        return self.controller.aperture.in_pausa(self._clima)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Sempre strutture nuove: Home Assistant confronta gli attributi con
        # una copia superficiale dei precedenti, e un oggetto condiviso
        # modificato sul posto non risulterebbe mai cambiato.
        gestore = self.controller.aperture
        pausa = gestore.pause[self._clima]
        salvato = dict(pausa.salvato or {})
        return {
            "clima": self._clima,
            "aperture_aperte": list(gestore.aperte_di(self._clima)),
            "dal": pausa.dal.isoformat() if pausa.dal else None,
            "stato_da_ripristinare": salvato.get("hvac_mode"),
            "temperatura_da_ripristinare": salvato.get("temperature"),
            "riaccende_alla_chiusura": gestore.riaccendera(self._clima),
            "non_riaccendere": pausa.non_riaccendere,
            "riacceso_a_mano": pausa.forzato,
            "ultimo_esito": gestore.esito.get(self._clima),
        }
