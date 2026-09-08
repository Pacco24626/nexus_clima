"""Costanti dell'integrazione Nexus Clima."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "nexus_clima"
MANUFACTURER = "Nexus-T"
MODEL = "Controllo termico solare"

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

# --- Configurazione della zona ------------------------------------------------
CONF_NOME = "name"
CONF_CLIMI = "climates"
CONF_ACCOPPIATE = "coupled"

# Sensori
CONF_SENSORE_RETE = "grid_sensor"
CONF_RETE_POSITIVA_IMPORT = "grid_positive_is_import"
CONF_SENSORE_TEMP = "temp_sensor"
CONF_SENSORE_ESTERNA = "outdoor_sensor"
CONF_SENSORE_POTENZA = "power_sensor"

# Range di lavoro
CONF_T_MIN = "temp_min"
CONF_T_COMFORT = "temp_comfort_min"
CONF_T_MAX = "temp_max"

# Potenza assorbita agli estremi del range, per mappare il surplus
CONF_P_A_T_MIN = "power_at_temp_min"
CONF_P_A_T_MAX = "power_at_temp_max"

# Finestre
CONF_CARICA_DA = "charge_from"
CONF_CARICA_A = "charge_to"
CONF_COMFORT_DA = "comfort_from"
CONF_COMFORT_A = "comfort_to"

# Movimento
CONF_PERMANENZA = "min_dwell"
CONF_PASSO = "max_step"
CONF_INTERVALLO = "interval"

# Ventilazione
CONF_USA_VENTOLA = "use_fan"
CONF_VENTOLA_BASE = "fan_normal"
CONF_VENTOLA_SPINTA = "fan_boost"

# Comando manuale
CONF_PAUSA_MANUALE = "manual_hold"

# Prezzi, per il rendiconto
CONF_PREZZO_ACQUISTO = "buy_price"
CONF_PREZZO_CESSIONE = "sell_price"

# --- Valori predefiniti -------------------------------------------------------
DEFAULT_T_MIN = 22.0
DEFAULT_T_COMFORT = 25.0
DEFAULT_T_MAX = 26.0

# Stimati di partenza: vengono sostituiti dai valori appresi quando ci sono
# abbastanza campioni, e restano il riferimento finche' non ce ne sono.
DEFAULT_P_A_T_MIN = 900
DEFAULT_P_A_T_MAX = 300

DEFAULT_COMFORT_DA = "00:00:00"
DEFAULT_COMFORT_A = "23:59:00"

# Mezz'ora. Con una deriva dell'ordine di 0,25 gradi l'ora, cambiare piu'
# spesso non ha giustificazione fisica: si insegue il rumore della rete,
# non la temperatura della stanza.
DEFAULT_PERMANENZA = 30
DEFAULT_PASSO = 1.0
DEFAULT_INTERVALLO = 120

DEFAULT_VENTOLA_BASE = "Auto"
DEFAULT_PAUSA_MANUALE = 180

DEFAULT_PREZZO_ACQUISTO = 0.25
DEFAULT_PREZZO_CESSIONE = 0.08

# --- Regolazione --------------------------------------------------------------
# Mezzo grado di isteresi sulla mappatura: sotto questa soglia il setpoint non
# si muove, altrimenti balla fra due gradi adiacenti sul rumore del bilancio.
ISTERESI = 0.5

# Il setpoint non scende mai piu' di un grado sotto la temperatura attuale.
# Scendere di piu' non raffredda di piu': ferma il compressore, che poi deve
# ripartire da fermo. E' il difetto centrale che questa integrazione corregge.
MARGINE_SOTTO = 1.0

# Quanto sopra il pavimento appreso si considera "non immagazzina piu' nulla".
MARGINE_PAVIMENTO = 0.3

# Deriva sotto la quale la macchina non sta piu' convertendo energia in freddo
# immagazzinato, in gradi all'ora.
DERIVA_DEBOLE = 0.15

# Minuti di plateau a piena spinta prima di registrare un pavimento.
MINUTI_PLATEAU = 20

# Peso del campione nuovo nella media esponenziale dei parametri appresi.
PESO_APPRENDIMENTO = 0.25

# Campioni sotto i quali il valore appreso non viene usato per decidere.
CAMPIONI_MINIMI = 3

# Finestra su cui si calcola la deriva, in minuti.
FINESTRA_DERIVA = 45

# Attesa della conferma dopo un comando, e ritentativi.
ATTESA_CONFERMA = 5.0
RITENTATIVI = 3
SPAZIATURA = 2.0

# --- Stati --------------------------------------------------------------------
STATO_CARICA = "carica"
STATO_COMFORT = "comfort"
STATO_MANUALE = "manuale"
STATO_FUORI = "fuori_finestra"
STATO_DISABILITATO = "disabilitato"
STATO_NON_PRONTO = "non_pronto"

# --- Chiavi delle entita' -----------------------------------------------------
KEY_ABILITATO = "enabled"
KEY_STATO = "state"
KEY_PAVIMENTO = "floor"
KEY_DERIVA = "drift"
KEY_RENDICONTO = "report"
KEY_RIPRENDI = "resume"
