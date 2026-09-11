"""Costanti dell'integrazione Nexus Clima."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "nexus_clima"
MANUFACTURER = "Nexus-T"
MODEL = "Controllo termico solare"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

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

# Modulazione solare: a soglie (comfort/eco) o continua.
CONF_MODALITA = "mode"
MODALITA_SOGLIE = "thresholds"
MODALITA_CONTINUA = "continuous"
CONF_ECO_TEMP = "eco_temperature"
CONF_ECO_VENTOLA = "eco_fan"
CONF_SOGLIA_PRELIEVO = "import_threshold"
CONF_TEMPO_PRELIEVO = "import_minutes"
CONF_SOGLIA_CESSIONE = "export_threshold"
CONF_TEMPO_CESSIONE = "export_minutes"
CONF_CONSUMO_IN_PIU = "comfort_extra_power"
CONF_ATTIVA_DA = "active_from"
CONF_ATTIVA_A = "active_to"

# Porte e finestre. "Aperture" e non "finestre": in questa integrazione la
# finestra e' gia' la fascia oraria di carica o di comfort.
CONF_APERTURE = "openings"  # {climate: [binary_sensor, ...]}
CONF_RITARDO_APERTURA = "open_delay"
CONF_RITARDO_CHIUSURA = "close_delay"
CONF_AZIONE_APERTURA = "open_action"
CONF_RIACCENDI = "resume_on_close"
CONF_LIMITE_RIACCENSIONE = "resume_limit"

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

# A soglie: i valori della classica automazione comfort/eco, piu' il consumo
# che il clima aggiunge tornando al comfort (misurato l'11/09/2026 su un Daikin
# da camera: 700-950 W fra 22 e 25 °C; 600 e' prudente).
DEFAULT_MODALITA = MODALITA_SOGLIE
DEFAULT_ECO_TEMP = 25.0
DEFAULT_ECO_VENTOLA = "Auto"
DEFAULT_SOGLIA_PRELIEVO = 300
DEFAULT_TEMPO_PRELIEVO = 8
DEFAULT_SOGLIA_CESSIONE = 500
DEFAULT_TEMPO_CESSIONE = 12
DEFAULT_CONSUMO_IN_PIU = 600
DEFAULT_ATTIVA_DA = "10:00:00"
DEFAULT_ATTIVA_A = "19:00:00"

# Un minuto di apertura prima di fermare: chi passa da una porta non deve
# spegnere il clima. Mezzo minuto di chiusura prima di riaccendere: una
# finestra richiusa e subito riaperta non deve far ripartire il compressore.
DEFAULT_RITARDO_APERTURA = 60
DEFAULT_RITARDO_CHIUSURA = 30
DEFAULT_AZIONE_APERTURA = "off"
# Zero: si riaccende sempre, qualunque sia stata la durata dell'apertura.
DEFAULT_LIMITE_RIACCENSIONE = 0

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

# Una macchina che passa da un cloud impiega di piu' a riportare l'accensione
# che un setpoint: si aspetta di piu' prima di confrontare il resto.
ATTESA_ACCENSIONE = 10.0

# Dopo un ripristino, per quanto un setpoint diverso dall'ultimo comandato non
# va letto come un comando manuale: la macchina riaccesa puo' riportare per
# qualche secondo il valore che ricordava lei.
TOLLERANZA_RIPRISTINO = 60

# A soglie: dopo un nostro comando, per quanto un cambio di setpoint o di
# ventola va considerato nostro. Alcune integrazioni locali riportano lo stato
# solo al polling successivo, anche un minuto dopo.
TOLLERANZA_COMANDO = 150

# A soglie si guarda la rete piu' spesso: i tempi sono di minuti, e un ciclo
# di due minuti li allungherebbe fino a due minuti.
INTERVALLO_SOGLIE = 30

# --- Stati --------------------------------------------------------------------
STATO_CARICA = "carica"
STATO_COMFORT = "comfort"
STATO_MANUALE = "manuale"
STATO_FUORI = "fuori_finestra"
STATO_DISABILITATO = "disabilitato"
STATO_NON_PRONTO = "non_pronto"
STATO_APERTURA = "apertura"
STATO_ECO = "eco"
STATO_SENZA_MODULAZIONE = "senza_modulazione"

# --- Chiavi delle entita' -----------------------------------------------------
KEY_ABILITATO = "enabled"
KEY_STATO = "state"
KEY_PAVIMENTO = "floor"
KEY_DERIVA = "drift"
KEY_RENDICONTO = "report"
KEY_RIPRENDI = "resume"
KEY_APERTURE = "openings_enabled"
KEY_PAUSA = "opening_pause"  # + _<climate>
KEY_NON_RIACCENDERE = "keep_off"  # + _<climate>
