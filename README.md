

## 🚀 Upgrade naar v1.4.0 (Breaking Change)

### Wat is er veranderd?

Prijzen zijn nu in **`€/kWh`** (was: `ct/kWh`). Dit betekent dat waarden 100× kleiner zijn.

### ✅ Check na upgrade

1. **Developer Tools → States**
   - `sensor.ned_forecast_price_now` moet tussen `0.05` en `0.30` zitten
   - `unit_of_measurement` moet `€/kWh` zijn

2. **Automations aanpassen**
   ```yaml
   # VOOR v3.0:
   below: 15  # 15 ct/kWh
   
   # NA v3.0:
   below: 0.15  # 0.15 €/kWh (= 15 cent)

3. **Template sensors**
   - Verwijder eventuele /100 of *100 conversies
   - De sensor is nu in € 

---
# ⚡ NED Energy Forecast voor Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/BravoNLD/NED-forecast.svg)](https://github.com/BravoNLD/NED-forecast/releases)
[![GitHub Issues](https://img.shields.io/github/issues/BravoNLD/NED-forecast)](https://github.com/BravoNLD/NED-forecast/issues)

Home Assistant integratie voor real-time duurzame energievoorspellingen in Nederland. Haal wind-, zon-, en verbruiksdata op tot 144 uur vooruit, en voorspel daarmee EPEX spotprijzen.

---

## 📸 Voorbeeld

![NED Energy Forecast Dashboard](https://github.com/user-attachments/assets/4f5f0550-2da0-40ed-ad9b-f385b36203f6)
*Real-time duurzame energie forecast met EPEX prijzen verwachting*

---

## ✨ Functies

| Feature | Beschrijving |
|---------|--------------|
| 🌬️ **Wind (land + zee)** | Productievoorspelling windenergie |
| ☀️ **Zonne-energie** | Productievoorspelling zonenergie |
| ⚡ **Totaalverbruik** | Nederlandse elektriciteitsverbruik per uur |
| 💰 **EPEX prijzen verwachting** | Day-ahead spotprijzen verwachting (€/kWh) |
| 📈 **144u forecast** | Tot 6 dagen vooruit kijken |
| 🔄 **Auto-refresh** | Data wordt elk uur automatisch geüpdatet |
| .. **Auto-fit** | (Optioneel) Het prijsmodel wordt elke nacht (02:07) gefit op de prijzen van de afgelopen periode

---

## ⚡ Quick Start

1. **Installeer via HACS** → Voeg custom repository toe
2. **API Key ophalen** bij [NED.nl](https://ned.nl/nl/user/register)
3. **Configureer integratie** via Settings → Integrations
4. **Optioneel** Refereer je epex prijs sensor, zodat hij de forecast daarop kan baseren
5. **Kopieer ApexCharts config** (zie hieronder)
6. **Klaar!** 🎉

---

## 📦 Installatie

### Via HACS (aanbevolen)

1. Open **HACS** in Home Assistant
2. Klik op de **3 stippen** rechts bovenin → **Custom repositories**
3. Voeg toe:
   - **Repository**: `https://github.com/BravoNLD/NED-forecast`
   - **Categorie**: `Integration`
4. Klik op **Add**
5. Zoek naar **"NED Energy Forecast"** in HACS
6. Klik op **Download**
7. **Herstart Home Assistant**

### Handmatige installatie

1. Download de [nieuwste release](https://github.com/BravoNLD/NED-forecast/releases)
2. Pak het uit in `custom_components/ned_energy_forecast/`
3. Herstart Home Assistant

---

## ⚙️ Configuratie

### Stap 1: Verkrijg een API key

1. Ga naar **[NED.nl API Registratie](https://ned.nl/nl/user/register)**
2. Maak een account aan (gratis voor non-commercieel gebruik)
3. Log in en navigeer naar je profiel → **API Keys**
4. Genereer een nieuwe API key
5. **Kopieer en bewaar deze veilig** – je ziet hem maar één keer!

### Stap 2: Integratie toevoegen

1. Ga naar **Settings** → **Devices & Services**
2. Klik op **+ Add Integration**
3. Zoek naar **"NED Energy Forecast"**
4. Plak je API key
5. Optioneel: Voeg je EPEX prijs sensor toe
6. Klik op **Submit**

De sensoren worden nu automatisch aangemaakt en elk uur geüpdatet.

---

## 📊 Beschikbare sensoren

| Sensor | Entity ID | Eenheid | Beschrijving |
|--------|-----------|---------|--------------|
| Wind (land) | `sensor.ned_forecast_wind_onshore` | GW | Windproductie op land |
| Wind (zee) | `sensor.ned_forecast_wind_offshore` | GW | Offshore windparken |
| Zonne-energie | `sensor.ned_forecast_solar` | GW | Totale zonneproductie |
| Totaal duurzaam | `sensor.ned_forecast_total_renewable` | GW | Som wind + zon |
| Verbruik | `sensor.ned_forecast_consumption` | GW | Landelijk verbruik |
| Dekkingspercentage | `sensor.ned_forecast_coverage` | % | Duurzame dekking |
| EPEX prijs (prijs/kWh) | `sensor.ned_epex_price_kwh` | €/kWh | Prijs voorspelling |
Alle sensoren bevatten **forecast attributes** met data tot 144 uur vooruit.

---

## 📈 ApexCharts voorbeeld

Kopieer deze configuratie voor een mooie gestapelde grafiek met prijzen:

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
    align_to: 1
    apex_config:
      tickAmount: 6
      labels:
        formatter: |
          EVAL:function(value) {
            return value.toFixed(0) + ' GW';
          }
  - id: Price
    opposite: true
    decimals: 0
    min: ~0
    max: ~0.25
    apex_config:
      tickAmount: 6
      labels:
        formatter: |
          EVAL:function(value) {
            return value.toFixed(0) + ' €/kWh';
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
          return value.toFixed(0) + ' GW';
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
    unit: GW
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
    unit: GW
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
    unit: GW
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
    unit: GW
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.forecast_epex_price
    name: EPEX Prijs
    type: line
    color: white
    yaxis_id: Price
    unit: €/kWh
    stroke_width: 3
    opacity: 1
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
```
## 💡 Tip: Full-width weergave

Wrap de card in een grid voor maximale breedte:
```yaml
type: grid
columns: 1
cards:
  - type: custom:apexcharts-card
    # ... jouw config hierboven
```
## ❓ Veelgestelde vragen

**Q: Sensoren tonen "Unavailable"**  
A: Check of je API key geldig is. Kijk in de logs (`Settings → System → Logs`) voor foutmeldingen.

**Q: Forecast data is verouderd**  
A: De data wordt elk uur ververst. Force een update via Developer Tools → Services → `homeassistant.update_entity`.

**Q: ApexCharts grafiek is leeg**
A:  Controleer of custom:apexcharts-card is geïnstalleerd via HACS
    Wacht ~1 uur tot forecast data is opgehaald
    Check of entity ID's kloppen met jouw installatie

**Q: Mijn prijzen zijn 100x te hoog/laag
A: Check je automations en template sensors en verwijder conversies van €/kWh naar ct/kWh

## 🚀 Roadmap

- [ ] Notificaties bij lage/hoge dekkingspercentages  
- [x] EPEX prijsvoorspelling *(sinds v1.1.0)*

Suggesties? Open een [issue](https://github.com/BravoNLD/NED-forecast/issues)!

## 📜 Credits

    Data-bron: NED.nl 
[![Datasource](https://ned.nl/themes/custom/nedt/logo.svg)](https://ned.nl/nl)
    
    Ontwikkeld door: @BravoNLD

Dank aan de Tweakers.net community voor feedback en testing!

## Licentie

Dit project is gelicenseerd onder de MIT License – zie het LICENSE bestand voor details.

Gemaakt met ⚡ voor de Nederlandse energietransitie 
