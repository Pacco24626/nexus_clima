# Nexus Clima

Modula i climatizzatori sul surplus fotovoltaico, tenendo il compressore
sempre acceso al carico che il sole riesce a pagare.

Una voce di configurazione per zona: zone diverse hanno profili d'uso opposti
— una camera si vive di notte, quando il fotovoltaico non produce; un salotto
di giorno — e meritano politiche diverse, non un setpoint comune.

## Perche' non basta accendere e spegnere

L'automazione che tutti scrivono commuta il setpoint fra un valore "comfort"
quando c'e' sole e uno "eco" quando si preleva dalla rete. Sembra ragionevole
e fa una cosa diversa da quella che sembra.

Quando il setpoint sale da 22 a 25 e la stanza e' a 23,4, la stanza e' **gia'
sotto** il nuovo obiettivo: il compressore non rallenta, si ferma. E resta
fermo per ore, finche' la temperatura non risale a 25. Poi riparte, e riparte
al massimo. E' il ciclo peggiore per un inverter, che rende quando gira in
continuo a carico parziale.

Nexus Clima non commuta fra due stati: sposta il setpoint di un grado alla
volta, non lo porta mai sotto la temperatura attuale, e per la regolazione
veloce usa la **ventilazione**, che si puo' muovere liberamente senza mai
rischiare di fermare la macchina.

## Come decide

Sei passi, rieseguiti a ogni valutazione. Lo stato pubblicato porta sempre con
se' il **motivo**, che e' l'unica spiegazione di cui c'e' bisogno quando il
comportamento sorprende.

**1. Il surplus che non si muove quando agiamo.** Il bilancio di rete misurato
contiene gia' il consumo del clima: usarlo cosi' com'e' produce un anello che
oscilla, perche' accendere peggiora la misura che ha fatto accendere. Si somma
quindi la potenza che il clima sta assorbendo.

```
surplus = −prelievo_dalla_rete + potenza_del_clima
```

**2. Dal surplus al setpoint.** Interpolazione fra il massimo e il minimo
dichiarati, misurata sulla potenza che ciascuno richiede — in watt, non in
gradi.

```
frazione = clamp((surplus − p_al_massimo) / (p_al_minimo − p_al_massimo), 0, 1)
obiettivo = massimo − frazione × (massimo − minimo)
```

**3. Il cancello di utilita' termica.** Sotto il pavimento appreso la macchina
va a piena spinta e la temperatura non scende: quell'energia non finisce in
banca, e valeva di piu' ceduta alla rete. Il setpoint si ferma.

**4. La prova della derivata.** Se il surplus e' abbondante ma la temperatura
non scende, il problema non e' il setpoint: la zona non assorbe di piu'.

**5. Mai fermare il compressore.** Il setpoint non scende oltre un grado sotto
la temperatura attuale, e resta allineato alle zone accoppiate.

**6. Isteresi, passo massimo, permanenza minima.** Mezzo grado di isteresi, un
grado per passo, e mezz'ora di permanenza: con una deriva dell'ordine di 0,25
gradi l'ora, cambiare piu' spesso significa inseguire il rumore della rete
invece della temperatura della stanza.

## Finestre di carica e di comfort

Ogni zona dichiara due finestre.

Nella **finestra di carica** il controllo puo' scendere fino al minimo: e' il
momento in cui la zona e' vuota e l'energia e' gratis. Nella **finestra di
comfort** si ferma al minimo di comfort, piu' alto. Fuori da entrambe non
tocca nulla.

Per una zona notte in una casa con fotovoltaico, la configurazione tipica e':

| | carica | comfort | range |
|---|---|---|---|
| Zona notte | 10:00 – 17:00 | 22:00 – 07:00 | 22 – 26 °C |
| Zona giorno | — | 10:00 – 22:00 | 24 – 26 °C |

## Il comando resta all'utente

Un setpoint cambiato a mano e' un ordine, non un disturbo. Il controller se ne
accorge, entra in stato `manuale` e smette di comandare per il tempo
configurato — o fino alla mezzanotte successiva. Il bottone **Riprendi il
controllo** chiude la pausa in anticipo.

E' il motivo per cui non serve una finestra oraria che spenga tutto la sera.

## Cosa impara

| Parametro | Che cosa dice |
|---|---|
| Pavimento raggiungibile | Dove la temperatura si ferma davvero, a piena spinta. Non e' il minimo dichiarato. |
| Deriva | Quanto sta salendo o scendendo la temperatura, in gradi all'ora. |
| Deriva passiva | Quanto tiene il freddo accumulato quando nessuno raffresca. |

I valori appresi non possono mai portare il setpoint fuori dal range
dichiarato, e finche' i campioni sono pochi valgono i valori di
configurazione. Ogni sensore espone quanti campioni lo sostengono.

## Il rendiconto

Dire «oggi hai risparmiato tot kWh» richiede un controfattuale — cosa sarebbe
successo senza il controllo — che non e' misurabile.

Quello che l'integrazione conta e' invece vero e basta: i kWh consumati dalla
zona e la quota coperta dal fotovoltaico, con la regola che se in
quell'istante la casa non stava importando il consumo era coperto, e se stava
importando X era coperto per quello che eccede X.

Da li' l'unica aritmetica difendibile e' la differenza fra i due prezzi:

```
quei kWh, ceduti, avrebbero reso   energia_da_surplus × prezzo_di_cessione
consumati hanno evitato            energia_da_surplus × prezzo_di_acquisto
```

Senza un contatore dedicato ai climatizzatori la potenza e' **stimata** dai
valori dichiarati, e l'attributo `misurata` del sensore lo dice. Una pinza sul
circuito dei climi e' l'investimento che rende attendibile tutto il resto.

## Entita' create per ogni zona

| Entita' | A che serve |
|---|---|
| `sensor` Stato | Cosa sta facendo e perche'; negli attributi surplus, setpoint obiettivo, minuti per stato |
| `sensor` Pavimento raggiungibile | Il minimo reale della zona, appreso |
| `sensor` Deriva | Gradi all'ora, con la deriva passiva negli attributi |
| `sensor` Energia della zona | kWh di oggi, quota da surplus e valore in euro |
| `switch` Abilitato | Sospende il controllo senza spegnere i climatizzatori |
| `button` Riprendi il controllo | Chiude in anticipo la pausa manuale |

## Installazione

Da HACS come repository personalizzato (`Pacco24626/nexus_clima`, categoria
Integrazione), poi **Impostazioni → Dispositivi e servizi → Aggiungi
integrazione → Nexus Clima**. Una voce per zona.

## Licenza

Apache License 2.0 — Copyright 2026 Automatic Systems.
