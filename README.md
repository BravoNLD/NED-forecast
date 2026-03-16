# ⚡ NED Energy Forecast voor Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/BravoNLD/NED-forecast.svg)](https://github.com/BravoNLD/NED-forecast/releases)
[![GitHub Issues](https://img.shields.io/github/issues/BravoNLD/NED-forecast)](https://github.com/BravoNLD/NED-forecast/issues)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/BravoNLD/NED-forecast/graphs/commit-activity)

**Voorspel duurzame energie én EPEX spotprijzen in Nederland — tot 144 uur vooruit, direct in Home Assistant.**

Deze integratie haalt real-time productievoorspellingen op voor wind- en zonne-energie, Nederlandse verbruiksdata, én maakt slimme prijsvoorspellingen op basis van jouw eigen EPEX-sensor. Perfect voor automatiseringen die je wasmachine starten als de stroom goedkoop en groen is.

---

## 🆕 Wat is er nieuw in v1.4.1?

### ⚡ Supersnel opstarten (85-95% sneller)

Het machine learning model traint nu **in de achtergrond** tijdens Home Assistant startup. Voorheen moest HA wachten tot het model klaar was (ca 40 seconden), nu zijn je sensors binnen 1-3 seconden beschikbaar.

**Wat betekent dit voor jou:**

* ✅ **Snellere HA restart** - Setup completeert direct
* ✅ **Direct beschikbare sensors** - Geen wachttijd meer
* ⏱️ **Tijdelijk eenvoudigere forecast** - De eerste ~30-60 minuten gebruikt een fallback-formule
* 🔄 **Automatische switch** - Zodra het ML-model klaar is, schakelt de forecast automatisch over

> \*\*Let op:\*\* Direct na restart kan `forecast_epex_price` kort gebaseerd zijn op een eenvoudigere berekening. Dit is normaal en lost zichzelf op binnen 30-60 minuten.

**Technisch:** Model fitting gebeurt nu via `hass.async_create_task` met proper concurrency guards en cleanup bij reload/shutdown. Geen breaking changes in configuratie.

---

## 📸 Voorbeeld

![NED Energy Forecast Dashboard](https://github.com/user-attachments/assets/4f5f0550-2da0-40ed-ad9b-f385b36203f6)

*Real-time dashboard met duurzame energie forecast en EPEX prijsverwachting tot 6 dagen vooruit*

---

## ✨ Features

|Feature|Beschrijving|
|-|-|
|🌬️ **Wind (land + zee)**|Productievoorspelling windenergie per uur|
|☀️ **Zonne-energie**|Productievoorspelling zonenergie per uur|
|⚡ **Totaal verbruik**|Nederlands elektriciteitsverbruik forecast|
|💰 **EPEX prijzen AI forecast**|Day-ahead spotprijzen verwachting o.b.v. je eigen sensor (€/kWh)|
|📈 **144u vooruit**|Tot 6 dagen forecast data in sensor attributes|
|🔄 **Auto-refresh**|Elk uur automatisch geüpdatet|
|🤖 **Auto-fit ML model**|Dagelijks om 02:07 model retraining op recente prijsdata|
|📊 **Model metrics**|R² score sensor toont nauwkeurigheid van prijsvoorspelling|
|⚡ **Snelle startup**|Model traint in background, geen blokkerende setup|

---

## ⚡ Quick start

1. **Installeer via HACS** → Voeg custom repository toe ([zie installatie](#-installatie))
2. **Haal API key op** bij [NED.nl](https://ned.nl/nl/user/register) (gratis)
3. **Configureer integratie** via Settings → Integrations → Add Integration
4. **Optioneel:** Koppel je EPEX prijs sensor voor slimme prijsvoorspelling
5. **Kopieer** [**ApexCharts config**](#-apexcharts-dashboard) voor een mooie grafiek
6. **Klaar!** 🎉

---

## 📦 Installatie

### Via HACS (aanbevolen)

1. Open **HACS** in Home Assistant
2. Klik rechts bovenin op de **︙ (drie stippen)** → **Custom repositories**
3. Voeg toe:

   * **Repository:** `https://github.com/BravoNLD/NED-forecast`
   * **Category:** `Integration`

4. Klik op **Add**
5. Zoek naar **"NED Energy Forecast"** in HACS
6. Klik op **Download**
7. **Herstart Home Assistant**

### Handmatige installatie

1. Download de [laatste release](https://github.com/BravoNLD/NED-forecast/releases)
2. Pak het archief uit
3. Kopieer de map `custom\_components/ned\_energy\_forecast/` naar je HA config directory
4. Herstart Home Assistant

---

## ⚙️ Configuratie

### Stap 1: Verkrijg een API key

1. Ga naar [**NED.nl API Registratie**](https://ned.nl/nl/user/register)
2. Maak een gratis account aan (non-commercieel gebruik)
3. Log in → Ga naar je **Profiel** → **API Keys**
4. Klik op **Generate new API key**
5. **Kopieer en bewaar deze veilig** – je ziet hem maar één keer!

> \*\*Tip:\*\* Bewaar je API key in je password manager

### Stap 2: Integratie toevoegen in Home Assistant

1. Ga naar **Settings** → **Devices \& Services**
2. Klik rechts onder op **+ Add Integration**
3. Zoek naar **"NED Energy Forecast"**
4. Plak je **API key** in het eerste veld
5. **Optioneel:** Selecteer je bestaande **EPEX prijs sensor** (bijv. van ENTSO-E, Nordpool, of Energy Zero)

   * Als je dit invult, wordt een slimme prijsvoorspelling gemaakt op basis van duurzame energie overschot
   * Als je dit leeg laat, worden alleen de duurzame energie sensoren aangemaakt

6. Klik op **Submit**

De sensoren worden nu automatisch aangemaakt en direct ververst.

### Stap 3: (Optioneel) Geavanceerde instellingen

Klik op **Configure** bij de integratie in Settings → Integrations voor extra opties:

|Optie|Default|Beschrijving|
|-|-|-|
|**Price sensor**|Geen|Je EPEX spotprijs sensor (€/kWh of ct/kWh)|
|**Forecast hours**|48|Aantal uren vooruit (12-168 uur)|

---

## 📊 Sensoren \& attributen

### Beschikbare sensoren

Alle sensoren hebben een **huidige waarde** (state) en **forecast attributen** met data tot 144 uur vooruit.

|Entity ID|Eenheid|Beschrijving|
|-|-|-|
|`sensor.ned_forecast_wind_onshore`|GW|Windproductie op land|
|`sensor.ned_forecast_wind_offshore`|GW|Windproductie op zee (offshore windparken)|
|`sensor.ned_forecast_solar`|GW|Totale zonneproductie Nederland|
|`sensor.ned_forecast_consumption`|GW|Landelijk elektriciteitsverbruik|
|`sensor.forecast_epex_price`|€/kWh|EPEX spotprijs voorspelling (alleen als price sensor geconfigureerd)|
|`sensor.model_r2_score`|-|R² score van het ML model|

** 📈 ApexCharts dashboard
Kopieer deze configuratie voor een professionele gestapelde grafiek met prijzen:

``` yaml
type: custom:apexcharts-card
graph_span: 144h
span:
  start: day
header:
  show: true
  title: EPEX prijs en duurzame energie forecast
  show_states: false
  colorize_states: true
now:
  show: true
  label: Nu
  color: "#FF6B6B"
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
    decimals: 2
    min: ~0
    max: ~0.30
    apex_config:
      tickAmount: 6
      labels:
        formatter: |
          EVAL:function(value) {
            return '€' + value.toFixed(2);
          }
apex_config:
  chart:
    height: 400px
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
  stroke:
    curve: smooth
    width: 2
  legend:
    show: true
    position: bottom
    horizontalAlign: center
series:
  - entity: sensor.ned_forecast_wind_onshore
    name: Wind op land
    type: area
    yaxis_id: Volume
    color: "#0EA5E9"
    group_by:
      func: last
      duration: 1h
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.ned_forecast_wind_offshore
    name: Wind op zee
    type: area
    color: "#14B8A6"
    yaxis_id: Volume
    group_by:
      func: last
      duration: 1h
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.ned_forecast_solar
    name: Zon
    type: area
    color: "#FBBF24"
    yaxis_id: Volume
    group_by:
      func: last
      duration: 1h
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.ned_forecast_consumption
    name: Verbruik
    type: line
    color: "#EF4444"
    yaxis_id: Volume
    stroke_width: 3
    group_by:
      func: last
      duration: 1h
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
  - entity: sensor.forecast_epex_price
    name: EPEX prijs
    type: line
    color: "#8B5CF6"
    yaxis_id: Price
    stroke_width: 3
    float_precision: 3
    group_by:
      func: last
      duration: 1h
    show:
      legend_value: false
    data_generator: |
      return entity.attributes.forecast.map((entry) => {
        return [new Date(entry.datetime).getTime(), entry.value];
      });
```

Vereiste: Installeer eerst ApexCharts Card via HACS

---

## 🔧 Troubleshooting

Sensoren tonen "Unavailable"
Mogelijke oorzaken:

API key ongeldig - Check in Settings → Integrations → NED Energy Forecast → Configure

NED.nl API down - Check ned.nl status

Netwerk issues - Check HA logs: Settings → System → Logs → Filter op "ned\_energy"

---

## 🤝 Contributing

Bijdragen zijn welkom!

Issues \& bugs
Check of het issue al bestaat
Open een nieuwe issue met:
HA versie
Integratie versie
Logs (Settings → System → Logs → filter "ned\_energy")
Screenshot indien relevant
Pull requests
Fork de repository
Maak een feature branch: git checkout -b feature/amazing-feature
Commit je changes: git commit -m 'feat: add amazing feature'
Push naar de branch: git push origin feature/amazing-feature
Open een Pull Request

## 📜 License

Dit project is gelicenseerd onder de MIT License – zie het LICENSE bestand voor details.

## 🙏 Credits

    Data-bron: NED.nl 
[![Datasource](https://ned.nl/themes/custom/nedt/logo.svg)](https://ned.nl/nl)
Alle energie forecast data is afkomstig van NED (Nationale Energiedata), een initiatief voor open energiedata in Nederland.

Ontwikkeling

Maintainer: @BravoNLD

Contributors: See all contributors
Community

Dank aan:

De Tweakers.net community voor vroege testing
Alle GitHub contributors en issue reporters

## ⭐ Support dit project

Vind je deze integratie nuttig?

⭐ Star deze repository op GitHub

🐛 Meld bugs via issues

💬 Deel je dashboard in de discussions

🇳🇱 Haal ook je energie bij [Zonneplan](https://start.zonneplan.nl/energie?promotion_code=483ebbfa-75ef-4ee1-990f-67e08567c1ca&utm_source=referral&utm_medium=app&utm_campaign=deel-en-verdien&c=113735) !

Gemaakt met ⚡ voor de Nederlandse energietransitie

Documentatie • Issues • Discussions • Releases

