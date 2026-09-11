"""Integrazione Nexus Clima: modula i climatizzatori sul surplus fotovoltaico.

Una voce di configurazione per zona. Zone diverse hanno profili d'uso opposti
— una camera si vive di notte, quando il fotovoltaico non produce; un salotto
di giorno — e meritano politiche diverse, non un setpoint comune.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import DOMAIN, PLATFORMS
from .controller import ClimaController
from .gestore_aperture import VERSIONE_STORAGE, chiave_storage

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura una zona."""
    controller = ClimaController(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    await controller.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_ricarica))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Scarica una zona, disarmando i suoi timer."""
    scaricato = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if scaricato:
        controller: ClimaController = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.async_shutdown()
    return scaricato


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Zona eliminata: via anche le pause per apertura che ricordava."""
    await Store(hass, VERSIONE_STORAGE, chiave_storage(entry.entry_id)).async_remove()


async def _async_ricarica(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
