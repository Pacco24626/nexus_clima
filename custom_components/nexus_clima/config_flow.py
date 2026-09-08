"""Configurazione di una zona climatica.

Alla creazione si chiede il minimo che serve per partire. Tutto il resto —
potenze, prezzi, ventilazione, tempi — sta nelle opzioni, divise in tre
sezioni: durante la stagione quei valori si cambiano spesso, e non deve
servire toccare il codice per farlo.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACCOPPIATE,
    CONF_CARICA_A,
    CONF_CARICA_DA,
    CONF_CLIMI,
    CONF_COMFORT_A,
    CONF_COMFORT_DA,
    CONF_INTERVALLO,
    CONF_NOME,
    CONF_P_A_T_MAX,
    CONF_P_A_T_MIN,
    CONF_PASSO,
    CONF_PAUSA_MANUALE,
    CONF_PERMANENZA,
    CONF_PREZZO_ACQUISTO,
    CONF_PREZZO_CESSIONE,
    CONF_RETE_POSITIVA_IMPORT,
    CONF_SENSORE_ESTERNA,
    CONF_SENSORE_POTENZA,
    CONF_SENSORE_RETE,
    CONF_SENSORE_TEMP,
    CONF_T_COMFORT,
    CONF_T_MAX,
    CONF_T_MIN,
    CONF_USA_VENTOLA,
    CONF_VENTOLA_BASE,
    CONF_VENTOLA_SPINTA,
    DEFAULT_COMFORT_A,
    DEFAULT_COMFORT_DA,
    DEFAULT_INTERVALLO,
    DEFAULT_P_A_T_MAX,
    DEFAULT_P_A_T_MIN,
    DEFAULT_PASSO,
    DEFAULT_PAUSA_MANUALE,
    DEFAULT_PERMANENZA,
    DEFAULT_PREZZO_ACQUISTO,
    DEFAULT_PREZZO_CESSIONE,
    DEFAULT_T_COMFORT,
    DEFAULT_T_MAX,
    DEFAULT_T_MIN,
    DEFAULT_VENTOLA_BASE,
    DOMAIN,
)


def _climi(multiplo: bool = True) -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="climate", multiple=multiplo)
    )


def _sensore(classe: str | None = None) -> selector.EntitySelector:
    config: dict[str, Any] = {"domain": "sensor", "multiple": False}
    if classe:
        config["device_class"] = classe
    return selector.EntitySelector(selector.EntitySelectorConfig(**config))


def _gradi(default: float) -> Any:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=14, max=32, step=0.5, unit_of_measurement="°C",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _watt() -> Any:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=6000, step=50, unit_of_measurement="W",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _schema_zona(d: dict[str, Any], nuovo: bool) -> vol.Schema:
    campi: dict[Any, Any] = {}
    if nuovo:
        campi[vol.Required(CONF_NOME, default=d.get(CONF_NOME, "Zona notte"))] = str

    campi.update(
        {
            vol.Required(CONF_CLIMI, default=d.get(CONF_CLIMI, [])): _climi(),
            vol.Optional(
                CONF_ACCOPPIATE, description={"suggested_value": d.get(CONF_ACCOPPIATE)}
            ): _climi(),
            vol.Required(
                CONF_SENSORE_RETE, description={"suggested_value": d.get(CONF_SENSORE_RETE)}
            ): _sensore("power"),
            vol.Required(
                CONF_RETE_POSITIVA_IMPORT, default=d.get(CONF_RETE_POSITIVA_IMPORT, True)
            ): bool,
            vol.Optional(
                CONF_SENSORE_TEMP, description={"suggested_value": d.get(CONF_SENSORE_TEMP)}
            ): _sensore("temperature"),
            vol.Optional(
                CONF_SENSORE_ESTERNA,
                description={"suggested_value": d.get(CONF_SENSORE_ESTERNA)},
            ): _sensore("temperature"),
            vol.Optional(
                CONF_SENSORE_POTENZA,
                description={"suggested_value": d.get(CONF_SENSORE_POTENZA)},
            ): _sensore("power"),
        }
    )
    return vol.Schema(campi)


def _schema_range(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_T_MIN, default=d.get(CONF_T_MIN, DEFAULT_T_MIN)): _gradi(DEFAULT_T_MIN),
            vol.Required(
                CONF_T_COMFORT, default=d.get(CONF_T_COMFORT, DEFAULT_T_COMFORT)
            ): _gradi(DEFAULT_T_COMFORT),
            vol.Required(CONF_T_MAX, default=d.get(CONF_T_MAX, DEFAULT_T_MAX)): _gradi(DEFAULT_T_MAX),
            vol.Optional(
                CONF_CARICA_DA, description={"suggested_value": d.get(CONF_CARICA_DA)}
            ): selector.TimeSelector(),
            vol.Optional(
                CONF_CARICA_A, description={"suggested_value": d.get(CONF_CARICA_A)}
            ): selector.TimeSelector(),
            vol.Required(
                CONF_COMFORT_DA, default=d.get(CONF_COMFORT_DA, DEFAULT_COMFORT_DA)
            ): selector.TimeSelector(),
            vol.Required(
                CONF_COMFORT_A, default=d.get(CONF_COMFORT_A, DEFAULT_COMFORT_A)
            ): selector.TimeSelector(),
        }
    )


def _schema_regolazione(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_P_A_T_MIN, default=d.get(CONF_P_A_T_MIN, DEFAULT_P_A_T_MIN)): _watt(),
            vol.Required(CONF_P_A_T_MAX, default=d.get(CONF_P_A_T_MAX, DEFAULT_P_A_T_MAX)): _watt(),
            vol.Required(
                CONF_PERMANENZA, default=d.get(CONF_PERMANENZA, DEFAULT_PERMANENZA)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5, max=180, step=5, unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_PASSO, default=d.get(CONF_PASSO, DEFAULT_PASSO)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5, max=3, step=0.5, unit_of_measurement="°C",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_INTERVALLO, default=d.get(CONF_INTERVALLO, DEFAULT_INTERVALLO)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=30, max=900, step=30, unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(CONF_USA_VENTOLA, default=d.get(CONF_USA_VENTOLA, True)): bool,
            vol.Required(
                CONF_VENTOLA_BASE, default=d.get(CONF_VENTOLA_BASE, DEFAULT_VENTOLA_BASE)
            ): str,
            vol.Optional(
                CONF_VENTOLA_SPINTA, description={"suggested_value": d.get(CONF_VENTOLA_SPINTA)}
            ): str,
            vol.Required(
                CONF_PAUSA_MANUALE, default=d.get(CONF_PAUSA_MANUALE, DEFAULT_PAUSA_MANUALE)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1440, step=15, unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_PREZZO_ACQUISTO, default=d.get(CONF_PREZZO_ACQUISTO, DEFAULT_PREZZO_ACQUISTO)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2, step=0.01, unit_of_measurement="€/kWh",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_PREZZO_CESSIONE, default=d.get(CONF_PREZZO_CESSIONE, DEFAULT_PREZZO_CESSIONE)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2, step=0.01, unit_of_measurement="€/kWh",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )


def _valida(dati: dict[str, Any]) -> dict[str, str]:
    t_min = float(dati.get(CONF_T_MIN, DEFAULT_T_MIN))
    t_comfort = float(dati.get(CONF_T_COMFORT, DEFAULT_T_COMFORT))
    t_max = float(dati.get(CONF_T_MAX, DEFAULT_T_MAX))
    if not t_min <= t_comfort <= t_max:
        return {CONF_T_COMFORT: "range_incoerente"}

    da, a = dati.get(CONF_CARICA_DA), dati.get(CONF_CARICA_A)
    if bool(da) != bool(a):
        return {CONF_CARICA_DA: "finestra_incompleta"}

    p_min = float(dati.get(CONF_P_A_T_MIN, DEFAULT_P_A_T_MIN))
    p_max = float(dati.get(CONF_P_A_T_MAX, DEFAULT_P_A_T_MAX))
    if p_min <= p_max:
        return {CONF_P_A_T_MIN: "potenze_incoerenti"}

    return {}


class NexusClimaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Creazione di una zona."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            nome = user_input[CONF_NOME]
            await self.async_set_unique_id(nome.strip().lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=nome, data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema_zona({}, True))

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> "NexusClimaOptionsFlow":
        return NexusClimaOptionsFlow()


class NexusClimaOptionsFlow(OptionsFlow):
    """Le opzioni, divise per quanto spesso si toccano."""

    @property
    def _corrente(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["zona", "range", "regolazione"]
        )

    async def async_step_zona(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._salva(user_input)
        return self.async_show_form(step_id="zona", data_schema=_schema_zona(self._corrente, False))

    async def async_step_range(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            if errori := _valida({**self._corrente, **user_input}):
                return self.async_show_form(
                    step_id="range", data_schema=_schema_range(user_input), errors=errori
                )
            return self._salva(user_input)
        return self.async_show_form(step_id="range", data_schema=_schema_range(self._corrente))

    async def async_step_regolazione(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            if errori := _valida({**self._corrente, **user_input}):
                return self.async_show_form(
                    step_id="regolazione",
                    data_schema=_schema_regolazione(user_input),
                    errors=errori,
                )
            return self._salva(user_input)
        return self.async_show_form(
            step_id="regolazione", data_schema=_schema_regolazione(self._corrente)
        )

    def _salva(self, modifiche: dict[str, Any]) -> ConfigFlowResult:
        """Le opzioni contengono sempre la configurazione completa."""
        unito = {**self._corrente, **modifiche}
        unito.pop(CONF_NOME, None)
        return self.async_create_entry(title="", data=unito)
