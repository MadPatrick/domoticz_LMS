# 🎵 Logitech Media Server Plugin (Extended)
### 🚀 Release v1.0.0 — First Stable Release

Deze eerste stabiele release brengt volledige integratie tussen **Logitech Media Server (LMS)** en **Domoticz**.  
De plugin is volledig herschreven, uitgebreid, getest en stabiel bevonden op Domoticz 2024+.

---

## 🌟 Nieuwe functies in v1.0.0

### 🎛️ **Volledige LMS-afstandsbediening**
- Play / Pause / Stop
- Next / Previous
- Volume control (dimmer)
- Power On/Off
- Sync / Unsync spelers

### 📡 **Automatische spelerdetectie**
- Detecteert alle aangesloten LMS-spelers automatisch
- Per speler worden Domoticz-devices aangemaakt

### 📊 **Uitgebreide speler-informatie**
- Huidige track
- Artiest
- Album
- Speelstatus
- Volume
- Online/offline status

### 🎶 **Playlist ondersteuning**
- Laad playlists per speler  
- Playlist toevoegen
- Playlist clear
- Direct starten via Domoticz of scripts

### 🧠 **Betrouwbare JSON-RPC communicatie**
- Volledige ondersteuning voor `jsonrpc.js`
- Volledig getest met Material Skin (UI)
- Werkt met LMS 8.x

---

## 🛠️ Technische verbeteringen

- Nieuwe pluginstructuur conform Domoticz 2024+
- Heartbeat-fix (geen crashes bij ontbrekende functies)
- Snellere parsing van playerstatus
- Minder API-verzoeken → efficiënter CPU-gebruik
- Verbeterde error handling + debug logging

---

## 📦 Installatie

Clone de plugin in de Domoticz plugin-map:

```bash
cd /home/<user>/domoticz/plugins
git clone https://github.com/MadPatrick/domoticz_LMS.git
sudo systemctl restart domoticz
