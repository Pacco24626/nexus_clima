"""Configurazione di una zona climatica.

Alla creazione si chiede il minimo che serve per partire: i climatizzatori, e
poi le porte e finestre di ciascuno. Tutto il resto — potenze, prezzi,
ventilazione, tempi — sta nelle opzioni, divise per sezione: durante la
stagione quei valori si cambiano spesso, e non deve servire toccare il codice
per farlo.

Il sensore di rete e' facoltativo. Senza, la zona non modula sul fotovoltaico
e gestisce solo le aperture; ma almeno una delle due cose deve farla.
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

from .aperture import AZIONE_SPEGNI, AZIONE_VENTILAZIONE
from .const import (
    CONF_ACCOPPIATE,
    CONF_APERTURE,
    CONF_AZIONE_APERTURA,
    CONF_CARICA_A,
    CONF_CARICA_DA,
    CONF_CLIMI,
    CONF_COMFORT_A,
    CONF_COMFORT_DA,
    CONF_ATTIVA_A,
    CONF_ATTIVA_DA,
    CONF_CONSUMO_IN_PIU,
    CONF_ECO_TEMP,
    CONF_ECO_VENTOLA,
    CONF_INTERVALLO,
    CONF_LIMITE_RIACCENSIONE,
    CONF_MODALITA,
    CONF_NOME,
    CONF_SOGLIA_CESSIONE,
    CONF_SOGLIA_PRELIEVO,
    CONF_TEMPO_CESSIONE,
    CONF_TEMPO_PRELIEVO,
    DEFAULT_ATTIVA_A,
    DEFAULT_ATTIVA_DA,
    DEFAULT_CONSUMO_IN_PIU,
    DEFAULT_ECO_TEMP,
    DEFAULT_ECO_VENTOLA,
    DEFAULT_MODALITA,
    DEFAULT_SOGLIA_CESSIONE,
    DEFAULT_SOGLIA_PRELIEVO,
    DEFAULT_TEMPO_CESSIONE,
    DEFAULT_TEMPO_PRELIEVO,
    MODALITA_CONTINUA,
    MODALITA_SOGLIE,
    CONF_P_A_T_MAX,
    CONF_P_A_T_MIN,
    CONF_PASSO,
    CONF_PAUSA_MANUALE,
    CONF_PERMANENZA,
    CONF_PREZZO_ACQUISTO,
    CONF_PREZZO_CESSIONE,
    CONF_RETE_POSITIVA_IMPORT,
    CONF_RIACCENDI,
    CONF_RITARDO_APERTURA,
    CONF_RITARDO_CHIUSURA,
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
    DEFAULT_AZIONE_APERTURA,
    DEFAULT_COMFORT_A,
    DEFAULT_COMFORT_DA,
    DEFAULT_INTERVALLO,
    DEFAULT_LIMITE_RIACCENSIONE,
    DEFAULT_P_A_T_MAX,
    DEFAULT_P_A_T_MIN,
    DEFAULT_PASSO,
    DEFAULT_PAUSA_MANUALE,
    DEFAULT_PERMANENZA,
    DEFAULT_PREZZO_ACQUISTO,
    DEFAULT_PREZZO_CESSIONE,
    DEFAULT_RITARDO_APERTURA,
    DEFAULT_RITARDO_CHIUSURA,
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
            vol.Optional(
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


def _schema_soglie(d: dict[str, Any]) -> vol.Schema:
    """La modulazione solare: modalita', e i parametri di quella a soglie."""

    def _numero(minimo: float, massimo: float, passo: float, unita: str) -> selector.NumberSelector:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=minimo, max=massimo, step=passo, unit_of_measurement=unita,
                mode=selector.NumberSelectorMode.BOX,
            )
        )

    return vol.Schema(
        {
            vol.Required(CONF_MODALITA, default=d.get(CONF_MODALITA, DEFAULT_MODALITA)): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[MODALITA_SOGLIE, MODALITA_CONTINUA],
                        translation_key="modalita",
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            ),
            vol.Required(CONF_ECO_TEMP, default=d.get(CONF_ECO_TEMP, DEFAULT_ECO_TEMP)): _numero(
                16, 30, 0.5, "°C"
            ),
            vol.Optional(
                CONF_ECO_VENTOLA,
                description={"suggested_value": d.get(CONF_ECO_VENTOLA, DEFAULT_ECO_VENTOLA)},
            ): str,
            vol.Required(
                CONF_SOGLIA_PRELIEVO, default=d.get(CONF_SOGLIA_PRELIEVO, DEFAULT_SOGLIA_PRELIEVO)
            ): _numero(0, 6000, 50, "W"),
            vol.Required(
                CONF_TEMPO_PRELIEVO, default=d.get(CONF_TEMPO_PRELIEVO, DEFAULT_TEMPO_PRELIEVO)
            ): _numero(0, 120, 1, "min"),
            vol.Required(
                CONF_SOGLIA_CESSIONE, default=d.get(CONF_SOGLIA_CESSIONE, DEFAULT_SOGLIA_CESSIONE)
            ): _numero(0, 6000, 50, "W"),
            vol.Required(
                CONF_TEMPO_CESSIONE, default=d.get(CONF_TEMPO_CESSIONE, DEFAULT_TEMPO_CESSIONE)
            ): _numero(0, 120, 1, "min"),
            vol.Required(
                CONF_CONSUMO_IN_PIU, default=d.get(CONF_CONSUMO_IN_PIU, DEFAULT_CONSUMO_IN_PIU)
            ): _numero(0, 3000, 50, "W"),
            vol.Required(
                CONF_ATTIVA_DA, default=d.get(CONF_ATTIVA_DA, DEFAULT_ATTIVA_DA)
            ): selector.TimeSelector(),
            vol.Required(
                CONF_ATTIVA_A, default=d.get(CONF_ATTIVA_A, DEFAULT_ATTIVA_A)
            ): selector.TimeSelector(),
        }
    )


# I campi fissi del passo delle aperture. Gli altri campi di quel passo sono
# uno per climatizzatore, e cambiano con la zona.
_CAMPI_APERTURE = (
    CONF_RITARDO_APERTURA,
    CONF_RITARDO_CHIUSURA,
    CONF_AZIONE_APERTURA,
    CONF_RIACCENDI,
    CONF_LIMITE_RIACCENSIONE,
)


def _etichette_climi(hass: Any, climi: list[str]) -> dict[str, str]:
    """Etichetta del campo -> climatizzatore.

    Il campo prende il nome del clima: per campi che dipendono dalla
    configurazione non ci sono traduzioni possibili, e un entity_id come
    etichetta e' leggibile solo da chi l'ha scritto.
    """
    etichette: dict[str, str] = {}
    for clima in climi:
        stato = hass.states.get(clima)
        nome = clima
        if stato is not None and stato.attributes.get("friendly_name"):
            nome = str(stato.attributes["friendly_name"])
        if nome in etichette or nome in _CAMPI_APERTURE:
            nome = f"{nome} ({clima})"
        etichette[nome] = clima
    return etichette


def _schema_aperture(etichette: dict[str, str], d: dict[str, Any]) -> vol.Schema:
    correnti = d.get(CONF_APERTURE) or {}
    campi: dict[Any, Any] = {}
    for etichetta, clima in etichette.items():
        campi[
            vol.Optional(etichetta, description={"suggested_value": correnti.get(clima) or []})
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
        )

    def _secondi(massimo: int) -> selector.NumberSelector:
        return selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=massimo, step=5, unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        )

    campi.update(
        {
            vol.Required(
                CONF_RITARDO_APERTURA,
                default=d.get(CONF_RITARDO_APERTURA, DEFAULT_RITARDO_APERTURA),
            ): _secondi(3600),
            vol.Required(
                CONF_RITARDO_CHIUSURA,
                default=d.get(CONF_RITARDO_CHIUSURA, DEFAULT_RITARDO_CHIUSURA),
            ): _secondi(3600),
            vol.Required(
                CONF_AZIONE_APERTURA,
                default=d.get(CONF_AZIONE_APERTURA, DEFAULT_AZIONE_APERTURA),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[AZIONE_SPEGNI, AZIONE_VENTILAZIONE],
                    translation_key="azione_apertura",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(CONF_RIACCENDI, default=d.get(CONF_RIACCENDI, True)): bool,
            vol.Required(
                CONF_LIMITE_RIACCENSIONE,
                default=d.get(CONF_LIMITE_RIACCENSIONE, DEFAULT_LIMITE_RIACCENSIONE),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=1440, step=15, unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
        }
    )
    return vol.Schema(campi)


def _aperture_da(user_input: dict[str, Any], etichette: dict[str, str]) -> dict[str, Any]:
    """Dal modulo alla configurazione: i campi per clima diventano un dizionario.

    Si ricostruisce da zero: un clima a cui si sono tolti tutti i sensori deve
    sparire, non restare con quelli di prima.
    """
    aperture = {
        etichette[chiave]: list(valore)
        for chiave, valore in user_input.items()
        if chiave in etichette and valore
    }
    resto = {chiave: valore for chiave, valore in user_input.items() if chiave not in etichette}
    return {**resto, CONF_APERTURE: aperture}


def _valida_scopo(dati: dict[str, Any]) -> dict[str, str]:
    """Una zona deve fare almeno una cosa: modulare, o fermare a finestra aperta."""
    aperture = {
        clima: sensori
        for clima, sensori in (dati.get(CONF_APERTURE) or {}).items()
        if clima in (dati.get(CONF_CLIMI) or []) and sensori
    }
    if not dati.get(CONF_SENSORE_RETE) and not aperture:
        return {"base": "niente_da_fare"}
    return {}


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



def _unito(corrente: dict[str, Any], modifiche: dict[str, Any], schema: vol.Schema) -> dict[str, Any]:
    """La configurazione dopo un passo delle opzioni.

    Un campo facoltativo svuotato nel modulo non arriva affatto: se ci si
    limitasse a sovrapporre, il valore vecchio resterebbe e non ci sarebbe modo
    di togliere, per esempio, il sensore di rete o la finestra di carica.
    """
    unito = {**corrente, **modifiche}
    for chiave in schema.schema:
        if isinstance(chiave, vol.Optional) and str(chiave) not in modifiche:
            unito.pop(str(chiave), None)
    return unito


class NexusClimaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Creazione di una zona: climatizzatori e sensori, poi porte e finestre."""

    VERSION = 1

    def __init__(self) -> None:
        self._zona: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            nome = user_input[CONF_NOME]
            await self.async_set_unique_id(nome.strip().lower())
            self._abort_if_unique_id_configured()
            self._zona = dict(user_input)
            return await self.async_step_aperture()

        return self.async_show_form(step_id="user", data_schema=_schema_zona({}, True))

    async def async_step_aperture(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        etichette = _etichette_climi(self.hass, self._zona.get(CONF_CLIMI) or [])
        if user_input is not None:
            dati = {**self._zona, **_aperture_da(user_input, etichette)}
            if errori := _valida_scopo(dati):
                return self.async_show_form(
                    step_id="aperture", data_schema=_schema_aperture(etichette, dati), errors=errori
                )
            self._zona = dati
            # Senza sensore di rete la modulazione non c'e': niente da chiedere.
            if not dati.get(CONF_SENSORE_RETE):
                return self.async_create_entry(title=dati[CONF_NOME], data=dati)
            return await self.async_step_soglie()

        return self.async_show_form(
            step_id="aperture", data_schema=_schema_aperture(etichette, self._zona)
        )

    async def async_step_soglie(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            dati = {**self._zona, **user_input}
            return self.async_create_entry(title=dati[CONF_NOME], data=dati)
        return self.async_show_form(step_id="soglie", data_schema=_schema_soglie(self._zona))

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
            step_id="init",
            menu_options=["zona", "aperture", "soglie", "range", "regolazione"],
        )

    async def async_step_soglie(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        schema = _schema_soglie(self._corrente)
        if user_input is not None:
            return self._salva(_unito(self._corrente, user_input, schema))
        return self.async_show_form(step_id="soglie", data_schema=schema)

    async def async_step_zona(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        schema = _schema_zona(self._corrente, False)
        if user_input is not None:
            unito = _unito(self._corrente, user_input, schema)
            if errori := _valida_scopo(unito):
                return self.async_show_form(
                    step_id="zona", data_schema=_schema_zona(unito, False), errors=errori
                )
            return self._salva(unito)
        return self.async_show_form(step_id="zona", data_schema=schema)

    async def async_step_aperture(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        etichette = _etichette_climi(self.hass, self._corrente.get(CONF_CLIMI) or [])
        if user_input is not None:
            unito = {**self._corrente, **_aperture_da(user_input, etichette)}
            if errori := _valida_scopo(unito):
                return self.async_show_form(
                    step_id="aperture", data_schema=_schema_aperture(etichette, unito), errors=errori
                )
            return self._salva(unito)
        return self.async_show_form(
            step_id="aperture", data_schema=_schema_aperture(etichette, self._corrente)
        )

    async def async_step_range(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        schema = _schema_range(self._corrente)
        if user_input is not None:
            unito = _unito(self._corrente, user_input, schema)
            if errori := _valida(unito):
                return self.async_show_form(
                    step_id="range", data_schema=_schema_range(unito), errors=errori
                )
            return self._salva(unito)
        return self.async_show_form(step_id="range", data_schema=schema)

    async def async_step_regolazione(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        schema = _schema_regolazione(self._corrente)
        if user_input is not None:
            unito = _unito(self._corrente, user_input, schema)
            if errori := _valida(unito):
                return self.async_show_form(
                    step_id="regolazione", data_schema=_schema_regolazione(unito), errors=errori
                )
            return self._salva(unito)
        return self.async_show_form(step_id="regolazione", data_schema=schema)

    def _salva(self, unito: dict[str, Any]) -> ConfigFlowResult:
        """Le opzioni contengono sempre la configurazione completa."""
        unito = dict(unito)
        unito.pop(CONF_NOME, None)
        return self.async_create_entry(title="", data=unito)
