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
2. Kopieer de map `custom_components/ned_forecast` naar je `config/custom_components/` map
3. Herstart Home Assistant

## Configuratie

1. Ga naar Settings → Devices & Services
2. Klik op "+ Add Integration"
3. Zoek naar "NED Energy Forecast"
4. Volg de configuratie stappen

## Sensoren

De integratie maakt de volgende sensoren aan:

- `sensor.ned_forecast_wind_onshore` - Wind op land (MW)
- `sensor.ned_forecast_wind_offshore` - Wind op zee (MW)
- `sensor.ned_forecast_solar` - Zonne-energie (MW)
- `sensor.ned_forecast_consumption` - Elektriciteitsverbruik (MW)
- `sensor.ned_forecast_total_renewable` - Totaal duurzaam (MW)
- `sensor.ned_forecast_coverage_percentage` - Dekkingspercentage (%)

Elke sensor bevat een `forecast` attribuut met voorspellingen voor de komende 48 uur.

## Gebruik in Lovelace

Voorbeeld ApexCharts configuratie:

```yaml
type: custom:apexcharts-card
graph_span: 48h
header:
  show: true
  title: Nederlandse energie forecast
series:
  - entity: sensor.ned_forecast_wind_onshore
    name: Wind op land
    type: area
  - entity: sensor.ned_forecast_wind_offshore
    name: Wind op zee
    type: area
  - entity: sensor.ned_forecast_solar
    name: Zon
    type: area
