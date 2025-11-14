"""
<plugin key="LyrionMediaServer" name="Lyrion Media Server" author="MadPatrick" version="1.4.1" wikilink="https://lyrion.org" externallink="https://github.com/MadPatrick/domoticz_LMS">
    <description>
        <h2>Lyrion Media Server Plugin - Extended</h2>
        <p>Version 1.4.1</p>
        <p>Detects players, creates devices, and provides:</p>
        <ul>
            <li>Power / Play / Pause / Stop</li>
            <li>Volume (Dimmer)</li>
            <li>Track info (Text)</li>
            <li>Playlists (Selector)</li>
            <li>Sync / Unsync</li>
            <li>Display text (via Actions device)</li>
        </ul>
    </description>    
    <params>
        <param field="Address" label="Server IP" width="200px" required="true" default="192.168.1.6"/>
        <param field="Port" label="Port" width="100px" required="true" default="9000"/>
        <param field="Username" label="Username" width="150px"/>
        <param field="Password" label="Password" width="150px" password="true"/>
        <param field="Mode1" label="Polling interval (sec)" width="100px" default="10"/>
        <param field="Mode2" label="Max playlists to expose" width="100px" default="10"/>
        <param field="Mode3" label="Debug logging" width="100px" default="No">
            <options>
                <option label="No" value="False"/>
                <option label="Yes" value="True"/>
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import requests
import time

PLAYLISTS_DEVICE_UNIT = 250

class LMSPlugin:
    def __init__(self):
        self.url = ""
        self.auth = None
        self.pollInterval = 30
        self.nextPoll = 0
        self.players = []
        self.playlists = []
        self.max_playlists = 50
        self.imageID = 0  # icon set ID
        self.debug = False  # Debug flag

    def onStart(self):
        Domoticz.Log("LMS plugin gestart.")

        # ------------ ICONEN LADEN --------------------
        if "lms" not in Images:
            Domoticz.Log("LMS icons not found, loading lms.zip ...")
            Domoticz.Image("lms.zip").Create()

        if "lms" in Images:
            self.imageID = Images["lms"].ID
            Domoticz.Log(f"LMS icons Loaded (ImageID={self.imageID})")
        else:
            Domoticz.Error("Kon LMS icon pack niet laden!")
        # ----------------------------------------------

        self.pollInterval = int(Parameters.get("Mode1", 30))
        self.max_playlists = int(Parameters.get("Mode2", 50))
        self.debug = Parameters.get("Mode3", "False").lower() == "true"
        if self.debug:
            Domoticz.Log("DEBUG mode activated.")

        self.url = f"http://{Parameters.get('Address', '127.0.0.1')}:{Parameters.get('Port', '9000')}/jsonrpc.js"
        username = Parameters.get("Username", "")
        password = Parameters.get("Password", "")
        self.auth = (username, password) if username else None

        Domoticz.Heartbeat(10)
        self.nextPoll = time.time() + 10
        Domoticz.Log("LMS plugin initialisation delayed unit first heartbeat.")

    def onStop(self):
        Domoticz.Log("LMS plugin stopped.")

    def onHeartbeat(self):
        if time.time() >= self.nextPoll:
            self.nextPoll = time.time() + self.pollInterval
            self.updateEverything()

    # -------------------------
    # LMS JSON-RPC helpers
    # -------------------------
    def lms_query_raw(self, player, cmd_array):
        data = {"id": 1, "method": "slim.request", "params": [player, cmd_array]}
        try:
            r = requests.post(self.url, json=data, auth=self.auth, timeout=10)
            r.raise_for_status()
            j = r.json()
            return j.get("result", j)
        except Exception as e:
            Domoticz.Error(f"Query fout: {e}")
            return None

    def get_serverstatus(self):
        return self.lms_query_raw("", ["serverstatus", 0, 999])

    def get_status(self, playerid, tags="tags:adclmntyK"):
        return self.lms_query_raw(playerid, ["status", "-", 1, tags])

    def get_playlists(self):
        return self.lms_query_raw("", ["playlists", 0, 999])

    def send_playercmd(self, playerid, cmd_array):
        return self.lms_query_raw(playerid, cmd_array)

    def send_button(self, playerid, button):
        return self.send_playercmd(playerid, ["button", button])

    def send_display_text(self, playerid, subject, text, duration=5):
        if not playerid or not text:
            return
        s1 = str(subject)[:64].replace('"', "'")
        s2 = str(text)[:128].replace('"', "'")
        cmd = ["show", f"line1:{s1}", f"line2:{s2}", f"duration:{duration}", "brightness:4", "font:huge"]
        self.send_playercmd(playerid, cmd)
        Domoticz.Log(f"{playerid}: Displaytext send ({s1} / {s2})")

    # -------------------------
    # Device helpers
    # -------------------------
    def friendly_dev_name(self, name, mac):
        return f"{name} [{mac}]"

    def find_player_devices(self, mac):
        for u, dev in Devices.items():
            if dev.Name.endswith(f"[{mac}]"):
                baseprefix = dev.Name[:-(len(mac) + 3)]
                main = vol = text = actions = None
                for uid, d in Devices.items():
                    if d.Name.startswith(baseprefix) and d.Name.endswith(f"[{mac}]"):
                        if "Volume" in d.Name:
                            vol = uid
                        elif "Track" in d.Name:
                            text = uid
                        elif "Actions" in d.Name:
                            actions = uid
                        else:
                            main = uid
                return (main, vol, text, actions)
        return None

    def create_player_devices(self, name, mac):
        friendly = self.friendly_dev_name(name, mac)
        unit = 1
        while unit in Devices:
            unit += 10

        # Hoofddevice: Play / Pause / Stop als knoppenbalk
        opts_main = {
            "LevelNames": "Off|Pause|Play|Stop",
            "LevelActions": "||||",
            "SelectorStyle": "0"
        }

        Domoticz.Device(
            Name=friendly,
            Unit=unit,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_main,
            Image=self.imageID
        ).Create()

        Domoticz.Device(
            Name=f"{name} Volume [{mac}]",
            Unit=unit + 1,
            TypeName="Dimmer",
            Image=self.imageID
        ).Create()

        Domoticz.Device(
            Name=f"{name} Track [{mac}]",
            Unit=unit + 2,
            TypeName="Text",
            Image=self.imageID
        ).Create()

        opts_act = {
            "LevelNames": "None|SendText|Sync to this|Unsync",
            "LevelActions": "||",
            "SelectorStyle": "0"
        }

        Domoticz.Device(
            Name=f"{name} Actions [{mac}]",
            Unit=unit + 3,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_act,
            Image=self.imageID
        ).Create()

        Domoticz.Log(f"Devices created for '{name}'")
        return (unit, unit + 1, unit + 2, unit + 3)

    # -------------------------
    # Playlists helpers
    # -------------------------
    def reload_playlists(self):
        root = self.get_playlists()
        if not root:
            self.playlists = []
        else:
            pl = root.get("playlists_loop", [])
            self.playlists = [ {
                "id": p.get("id"),
                "playlist": p.get("playlist", ""),
                "refid": int(p.get("id", 0)) % 256
            } for p in pl[:self.max_playlists]]

        levelnames = "Select|" + "|".join([p["playlist"] for p in self.playlists]) if self.playlists else "Select|No playlists"

        opts = {
            "LevelNames": levelnames,
            "LevelActions": "",
            "SelectorStyle": "1"
        }

        if PLAYLISTS_DEVICE_UNIT not in Devices:
            Domoticz.Device(
                Name="LMS Playlists",
                Unit=PLAYLISTS_DEVICE_UNIT,
                TypeName="Selector Switch",
                Switchtype=18,
                Options=opts,
                Image=self.imageID
            ).Create()
            Domoticz.Log(f"Playlists-device created (unit {PLAYLISTS_DEVICE_UNIT})")
        else:
            dev = Devices[PLAYLISTS_DEVICE_UNIT]
            if dev.Options.get("LevelNames", "") != levelnames or dev.Options.get("SelectorStyle", "") != "1":
                Domoticz.Log(f"Playlists updated: {levelnames}")
                dev.Update(nValue=0, sValue="0", Options=opts)

    def play_playlist_by_level(self, Level):
        if Level < 10:
            Domoticz.Log("LMS: 'Select' choosen, No playlist started.")
            return

        idx = int(Level // 10) - 1
        if idx < 0 or idx >= len(self.playlists):
            Domoticz.Log(f"LMS: Invalid playlist-index (Level={Level}, idx={idx}).")
            return

        pl = self.playlists[idx]
        playlist_name = pl["playlist"]
        Domoticz.Log(f"LMS: Playlist Selected: '{playlist_name}' (idx={idx})")
        self.start_playlist_on_first_player(playlist_name)

    def start_playlist_on_first_player(self, playlist_name):
        if not self.players:
            Domoticz.Log("LMS: No players available to play the playlist.")
            return

        first = self.players[0]
        mac = first.get("playerid")
        name = first.get("name", "Unknown")

        if not mac:
            Domoticz.Log("LMS: First player as no playedID, Can not start the playlist.")
            return

        Domoticz.Log(f"LMS: Start playlist '{playlist_name}' on player '{name}' ({mac}).")
        self.send_playercmd(mac, ["playlist", "add", playlist_name])
        self.send_playercmd(mac, ["play"])
        self.nextPoll = time.time() + 1

    # -------------------------
    # Updating players & playlists
    # -------------------------
    def updateEverything(self):
        server = self.get_serverstatus()
        if not server:
            Domoticz.Error(f"No response from LMS server at {self.url}")
            return

        self.players = server.get("players_loop", [])
        for p in self.players:
            name, mac = p.get("name", "Unknown"), p.get("playerid", "")
            if not mac:
                continue
            if not self.find_player_devices(mac):
                self.create_player_devices(name, mac)

        self.reload_playlists()

        for p in self.players:
            name, mac = p.get("name", "Unknown"), p.get("playerid", "")
            if not mac:
                continue
            devices = self.find_player_devices(mac)
            if not devices:
                continue
            main, vol, text, actions = devices
            st = self.get_status(mac) or {}

            if self.debug:
                Domoticz.Log(f"DEBUG STATUS for {name} ({mac}): {st}")

            power = int(st.get("power", 0))
            mode = st.get("mode", "stop")
            mixer_vol = int(st.get("mixer volume", 0))
            sel_level = {"pause": 10, "play": 20, "stop": 30}.get(mode, 0)
            if power == 0:
                sel_level = 0

            if main in Devices:
                nval = 1 if power == 1 else 0
                sval = str(sel_level)
                if Devices[main].nValue != nval or Devices[main].sValue != sval:
                    Devices[main].Update(nValue=nval, sValue=sval)

            if vol in Devices:
                onoff = 1 if power == 1 else 0
                sval = str(mixer_vol if power == 1 else 0)
                if Devices[vol].nValue != onoff or Devices[vol].sValue != sval:
                    Devices[vol].Update(nValue=onoff, sValue=sval)

            if text in Devices:
                title = st.get("title") or st.get("current_title") or ""
                artist = st.get("artist") or ""
                album = st.get("album") or ""

                # remote_meta / remoteMeta
                for key in ("remote_meta", "remoteMeta"):
                    if key in st:
                        meta = st[key]
                        title = meta.get("title", title)
                        artist = meta.get("artist", artist)
                        album = meta.get("album", album)

                # current_title fallback
                if "current_title" in st:
                    station = st["current_title"]
                    if title.startswith(station):
                        title = title[len(station):].strip(" -")
                    title = title.replace("??", "").strip()

                # fallback splitsing artist-title
                if not artist and "-" in title:
                    parts = title.split("-", 1)
                    if len(parts) == 2:
                        artist, title = parts[0].strip(), parts[1].strip()

                # playlist_loop fallback
                if not title and "playlist_loop" in st and len(st["playlist_loop"]) > 0:
                    entry = st["playlist_loop"][0]
                    title = entry.get("title", title)
                    artist = entry.get("artist", artist)
                    album = entry.get("album", album)

                if not title:
                    title = "(onbekend nummer)"

                if power == 0:
                    label = "Uit"
                elif mode == "play":
                    label = f"{title}"
                    if artist:
                        label += f" - {artist}"
                    if album:
                        label += f" ({album})"
                elif mode == "pause":
                    label = f"{title}"
                else:
                    label = "Gestopt"

                label = label[:255]
                if Devices[text].sValue != label:
                    Devices[text].Update(nValue=0, sValue=label)
                    Domoticz.Log(f"LMS: Player '{name}' [{mac}] - Now playing: '{label}'")

    # -------------------------
    # Handling commands
    # -------------------------
    def onCommand(self, Unit, Command, Level, Hue):
        if Unit in Devices:
            devname = Devices[Unit].Name
            mac = devname.split("[")[-1].strip("]") if "[" in devname else "Unknown"
            player_name = devname.split("[")[0].strip() if "[" in devname else devname

            # Playlists
            if Unit == PLAYLISTS_DEVICE_UNIT and Command == "Set Level":
                if self.playlists:
                    idx = int(Level // 10) - 1
                    if 0 <= idx < len(self.playlists):
                        playlist_name = self.playlists[idx]["playlist"]
                        Domoticz.Log(f"LMS: Player '{player_name}' [{mac}] - Playlist selected: '{playlist_name}'")
                        self.start_playlist_on_first_player(playlist_name)
                    else:
                        Domoticz.Log(f"LMS: Player '{player_name}' [{mac}] - Invalid playlist selection (Level={Level})")
                else:
                    Domoticz.Log(f"LMS: Player '{player_name}' [{mac}] - No playlists available")
                return

            # Power On/Off
            if Command in ["On", "Off"]:
                action = "Power On" if Command == "On" else "Power Off"
                self.send_playercmd(mac, ["power", "1" if Command == "On" else "0"])
                Devices[Unit].Update(nValue=1 if Command == "On" else 0, sValue="20" if Command == "On" else "0")
                Domoticz.Log(f"LMS: Player '{player_name}' [{mac}] - {action} triggered")
                return

            # Volume
            if "Volume" in devname and Command == "Set Level":
                self.send_playercmd(mac, ["mixer", "volume", str(Level)])
                Devices[Unit].Update(nValue=1, sValue=str(Level))
                Domoticz.Log(f"LMS: Player '{player_name}' [{mac}] - Volume set to {Level}%")
                return

            # Play / Pause / Stop
            if Command == "Set Level" and "Volume" not in devname:
                btn_name = {10: "Pause", 20: "Play", 30: "Stop"}.get(Level, f"Level {Level}")
                btn_cmd = {"Pause": "pause.single", "Play": "play.single", "Stop": "stop"}.get(btn_name, "")
                if btn_cmd:
                    self.send_button(mac, btn_cmd)
                Devices[Unit].Update(nValue=1, sValue=str(Level))
                Domoticz.Log(f"LMS: Player '{player_name}' [{mac}] - Command '{btn_name}' triggered")

# -------------------------
# Plugin instantiation
# -------------------------
_plugin = LMSPlugin()

def onStart():
    _plugin.onStart()

def onStop():
    _plugin.onStop()

def onHeartbeat():
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)
