# NED Energy Forecast

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/BravoNLD/NED-forecast.svg)](https://github.com/BravoNLD/NED-forecast/releases)
[![License](https://img.shields.io/github/license/BravoNLD/NED-forecast.svg)](LICENSE)

Een Home Assistant integratie voor het ophalen van Nederlandse energie forecast data van ned.nl.

## Functies

- 📊 Real-time forecast data voor Nederlandse energie productie
- 🌬️ Wind op land en zee productie
- ☀️ Zonne-energie productie
- ⚡ Totaal elektriciteitsverbruik
- 🌱 Totaal duurzame energie productie
- 📈 Dekkingspercentage duurzame energie

## Installatie

### Via HACS (aanbevolen)

1. Open HACS in Home Assistant
2. Ga naar "Integrations"
3. Klik op de drie puntjes rechtsboven
4. Selecteer "Custom repositories"
5. Voeg deze URL toe: `https://github.com/BravoNLD/NED-forecast`
6. Selecteer categorie: "Integration"
7. Klik op "Add"
8. Zoek naar "NED Energy Forecast"
9. Klik op "Download"
10. Herstart Home Assistant

### Handmatige installatie

1. Download de laatste release
2. Kopieer de map `custom_components/ned_energy_forecast` naar je `config/custom_components/` map
3. Herstart Home Assistant

## Configuratie

1. Registreer je op ned.nl
2. Maak een API key aan om toegang tot de data te krijgen
3. Sla de API key op (eenmalig zichtbaar!)
4. Ga naar Settings → Devices & Services
5. Klik op "+ Add Integration"
6. Zoek naar "NED Energy Forecast"
7. Volg de configuratie stappen
8. Vul API key in
9. Vul gewenste forecast periode in (max 144 uur vooruit)

## Sensoren

De integratie maakt de volgende sensoren aan:

- `sensor.ned_forecast_wind_onshore` - Wind op land (MW)
- `sensor.ned_forecast_wind_offshore` - Wind op zee (MW)
- `sensor.ned_forecast_solar` - Zonne-energie (MW)
- `sensor.ned_forecast_consumption` - Elektriciteitsverbruik (MW)
- `sensor.ned_forecast_total_renewable` - Totaal duurzaam (MW)
- `sensor.ned_forecast_coverage_percentage` - Dekkingspercentage (%)

Elke sensor bevat een `forecast` attribuut met voorspellingen voor de komende 144-168 uur.

## Support

Heb je een vraag op probleem?
- Open een issue
- Bekijk de discussie

## Credits

Data-bron: NED.nl 
[![Datasource](https://ned.nl/themes/custom/nedt/logo.svg)](https://ned.nl/nl)

## Licentie:

MIT License - zie LICENSE voor details

## Voorbeeld Lovelace ApexCharts kaart

Met onderstaande Lovelace-config kun je de duurzame energie forecast visualiseren in Home Assistant met de [apexcharts-card](https://github.com/RomRider/apexcharts-card).

**Vereisten:**
- Installeer de [ApexCharts Card](https://github.com/RomRider/apexcharts-card) via HACS

<img width="924" height="408" alt="Screenshot_apexchart_graph_including_price_forecast" src="https://github.com/user-attachments/assets/4f5f0550-2da0-40ed-ad9b-f385b36203f6" />

**Configuratie:**

```yaml
type: custom:apexcharts-card
graph_span: 144h
span:
  start: day
header:
  show: true
  title: Epex prijs en duurzame energie forecast
  show_states: false
  colorize_states: true
now:
  show: true
  label: Nu
  color: "#FF6B6B"
stacked: true
yaxis:
  - id: Volume
    decimals: 0
    align_to: 1000
    apex_config:
      tickAmount: 6
      labels:
        formatter: |
          EVAL:function(value) {
            return value.toFixed(0) + ' MW';
          }
  - id: Price
    opposite: true
    decimals: 0
    min: ~0
    max: ~25
    apex_config:
      tickAmount: 6
      labels:
        formatter: |
          EVAL:function(value) {
            return value.toFixed(0) + ' ct/kWh';
          }
apex_config:
  chart:
    height: 400px
    stacked: true
    stackType: normal
  grid:
    show: true
    borderColor: "#e0e0e0"
    strokeDashArray: 3
  xaxis:
    labels:
      datetimeUTC: false
      format: ddd dd MMM
  tooltip:
    enabled: true
    shared: true
    intersect: false
    x:
      format: dd MMM yyyy HH:mm
    "y":
      formatter: |
        EVAL:function(value) {
          return value.toFixed(0) + ' MW';
        }
  stroke:
    curve: smooth
    width: 2
  fill:
    type: solid
    opacity: 0.85
  legend:
    show: true
    position: bottom
    horizontalAlign: center
series:
  - entity: sensor.ned_forecast_wind_onshore
    name: Wind op land
    type: column
    yaxis_id: Volume
    color: "#0EA5E9"
    unit: MW
    stack_group: renewable
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.ned_forecast_wind_offshore
    name: Wind op zee
    type: column
    color: "#14B8A6"
    yaxis_id: Volume
    unit: MW
    stack_group: renewable
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.ned_forecast_solar
    name: Zon
    type: column
    color: "#FBBF24"
    yaxis_id: Volume
    unit: MW
    stack_group: renewable
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.ned_forecast_consumption
    name: Verbruik
    type: line
    color: red
    yaxis_id: Volume
    unit: MW
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.ned_forecast_epex_price
    name: EPEX Prijs
    type: line
    color: white
    yaxis_id: Price
    unit: ct/kWh
    stroke_width: 3
    opacity: 1
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });

```
## Resultaat: 
Een gestapelde grafiek met 144 uur forecast, waarbij:

    🌬️ Wind op land (blauw)
    🌊 Wind op zee (turquoise)
    ☀️ Zon (geel)
    ⚡ Verbruik (rode lijn)
       EPEX prijs verwachting (witte lijn)

worden getoond met een "Nu" indicator op het huidige moment.

PS voor een brede weergave moet je de card in de grid card configuration opnemen met 1 kolom
```yaml
square: true
type: grid
cards:
- apexchart # <-- voeg hier de apex chart in
columns: 1
grid_options:
  columns: 24
  rows: auto
```
