"""
<plugin key="LyrionMusicServer" name="Lyrion Music Server" author="MadPatrick" version="2.0.2" wikilink="https://lyrion.org" externallink="https://github.com/MadPatrick/domoticz_Lyrion">
    <description>
        <h2>Lyrion Music Server Plugin - Extended</h2>
        <p>Version 2.0.2</p>
        <p>Detects players, creates devices, and provides:</p>
        <ul>
            <li>Power / Play / Pause / Stop</li>
            <li>Volume (Dimmer)</li>
            <li>Track info (Text)</li>
            <li>Playlists (Selector)</li>
            <li>Sync / Unsync</li>
            <li>Display text (via Actions device)</li>
            <li>Shuffle (Selector)</li>
            <li>Repeat (Selector)</li>
        </ul>
    </description>

    <params>
        <param field="Address" label="Server IP" width="200px" required="true" default="192.168.1.6"/>
        <param field="Port" label="Port" width="100px" required="true" default="9000"/>
        <param field="Username" label="Username" width="150px"/>
        <param field="Password" label="Password" width="150px" password="true"/>
        <param field="Mode1" label="Polling interval (sec)" width="150px" default="10">
            <options>
                <option label="5 sec" value="5"/>
                <option label="10 sec" value="10"/>
                <option label="20 sec" value="20"/>
                <option label="30 sec" value="30"/>
                <option label="60 sec" value="60"/>
            </options>
        </param>
        <param field="Mode2" label="Max playlists to expose" width="100px" default="10"/>
        <param field="Mode3" label="Debug logging" width="100px" default="No">
            <options>
                <option label="No" value="False"/>
                <option label="Yes" value="True"/>
            </options>
        </param>
        <param field="Mode4" label="Message text" width="300px" default="Hello from Domoticz!" />
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
        self.imageID = 0
        self.debug = False

        # Display text settings
        self.displayText = ""           # Mode4: line2
        self.subjectText = "Lyrion"     # line1
        self.displayDuration = 60

        # Logging and initialization tracking
        self.initialized = False
        self.createdDevices = 0
        self.activePlaylist = None

        # Track-change detection
        self.lastTrackIndex = {}

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def log(self, msg):
        Domoticz.Log(msg)

    def debug_log(self, msg):
        if self.debug:
            Domoticz.Log(f"DEBUG: {msg}")

    def error(self, msg):
        Domoticz.Error(msg)

    @staticmethod
    def is_main_device_name(name: str) -> bool:
        """True als dit het hoofd-device is (geen Volume/Track/... suffix)."""
        return not any(x in name for x in ("Volume", "Track", "Actions", "Shuffle", "Repeat"))

    # ------------------------------------------------------------------
    # Domoticz lifecycle
    # ------------------------------------------------------------------
    def onStart(self):
        self.log(f"Plugin version {Parameters['Version']} is starting up.")
        
        _IMAGE = "lyrion"

        # Vlag om te controleren of we de ZIJN aan het creëren
        creating_new_icon = _IMAGE not in Images
        
        # Roep ALTIJD Create() aan. Domoticz API zal dit negeren als het al bestaat.
        Domoticz.Image(f"{_IMAGE}.zip").Create()

        # Update de image ID vanuit de Images dictionary (die nu gevuld moet zijn)
        if _IMAGE in Images:
            self.imageID = Images[_IMAGE].ID
            if creating_new_icon:
                # Log de 'loaded' melding ALLEEN als het de ECHTE eerste keer was
                self.log(f"Icons created and loaded (ImageID={self.imageID}).")
            else:
                # Log de 'found' melding als het een herstart is
                self.log(f"Icons found in database (ImageID={self.imageID}).")
        else:
            self.error(f"Unable to load icon pack '{_IMAGE}.zip'")

        
        self.pollInterval = int(Parameters.get("Mode1", 30))
        self.max_playlists = int(Parameters.get("Mode2", 50))
        self.debug = Parameters.get("Mode3", "False").lower() == "true"

        self.displayText = Parameters.get("Mode4", "")
        self.log(f"Display text (line2) = '{self.displayText}'")

        self.url = f"http://{Parameters['Address']}:{Parameters['Port']}/jsonrpc.js"

        user = Parameters.get("Username", "")
        pwd = Parameters.get("Password", "")
        self.auth = (user, pwd) if user else None

        Domoticz.Heartbeat(10)
        self.nextPoll = time.time() + 10

    def onStop(self):
        self.log("Plugin stopped.")

    def onHeartbeat(self):
        if time.time() >= self.nextPoll:
            self.nextPoll = time.time() + self.pollInterval
            self.updateEverything()

    # ------------------------------------------------------------------
    # LMS JSON helper
    # ------------------------------------------------------------------
    def lms_query_raw(self, player, cmd_array):
        data = {"id": 1, "method": "slim.request", "params": [player, cmd_array]}
        try:
            r = requests.post(self.url, json=data, auth=self.auth, timeout=5)
            r.raise_for_status()
            result = r.json().get("result")
            self.debug_log(f"Query: player={player}, cmd={cmd_array}, result={result}")
            return result
        except Exception as e:
            self.error(f"LMS query error: {e}")
            return None

    def get_serverstatus(self):
        return self.lms_query_raw("", ["serverstatus", 0, 999])

    def get_status(self, playerid):
        return self.lms_query_raw(playerid, ["status", "-", 1, "tags:adclmntyK"])

    def get_playlists(self):
        return self.lms_query_raw("", ["playlists", 0, 999])

    def send_playercmd(self, playerid, cmd_array):
        return self.lms_query_raw(playerid, cmd_array)

    def send_button(self, playerid, button):
        return self.send_playercmd(playerid, ["button", button])

    # ------------------------------------------------------------------
    # DISPLAY TEXT
    # ------------------------------------------------------------------
    def send_display_text(self, playerid, line2_text):
        if not playerid or not line2_text:
            return

        line1 = self.subjectText[:64].replace('"', "'")
        line2 = line2_text[:128].replace('"', "'")
        d = self.displayDuration

        cmd = [
            "show",
            f"line1:{line1}",
            f"line2:{line2}",
            f"duration:{d}",
            "brightness:4",
            "font:large",
        ]

        self.send_playercmd(playerid, cmd)
        self.log(f"Display text sent to {playerid}: '{line1}' / '{line2}' ({d}s)")

    # ------------------------------------------------------------------
    # DEVICE CREATION / LOOKUP
    # ------------------------------------------------------------------
    def create_player_devices(self, name, mac):

        base = name
        unit = 1
        # Per 10 units per speler
        while unit in Devices:
            unit += 10

        # main selector
        opts_main = {
            "LevelNames": "Off|Pause|Play|Stop",
            "LevelActions": "||||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=base,
            Unit=unit,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_main,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # volume
        Domoticz.Device(
            Name=f"{base} Volume",
            Unit=unit + 1,
            Type=244,
            Subtype=73,
            Switchtype=7,
            Image=5,
            Description=mac,
            Used=1,
        ).Create()

        # track text
        Domoticz.Device(
            Name=f"{base} Track",
            Unit=unit + 2,
            TypeName="Text",
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # actions selector
        opts_act = {
            "LevelNames": "None|SendText|Sync to this|Unsync",
            "LevelActions": "||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=f"{base} Actions",
            Unit=unit + 3,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_act,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # shuffle selector
        opts_shuffle = {
            "LevelNames": "Off|Songs|Albums",
            "LevelActions": "||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=f"{base} Shuffle",
            Unit=unit + 4,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_shuffle,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # repeat selector
        opts_repeat = {
            "LevelNames": "Off|Track|Playlist",
            "LevelActions": "||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=f"{base} Repeat",
            Unit=unit + 5,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_repeat,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        self.createdDevices += 6
        self.log(f"Devices created for player '{name}'")
        return (unit, unit + 1, unit + 2, unit + 3, unit + 4, unit + 5)

    def find_player_devices(self, mac):

        main = vol = text = actions = shuffle = repeat = None

        for uid, dev in Devices.items():
            if dev.Description != mac:
                continue

            if dev.Name.endswith("Volume"):
                vol = uid
            elif dev.Name.endswith("Track"):
                text = uid
            elif dev.Name.endswith("Actions"):
                actions = uid
            elif dev.Name.endswith("Shuffle"):
                shuffle = uid
            elif dev.Name.endswith("Repeat"):
                repeat = uid
            else:
                main = uid

        if main:
            return (main, vol, text, actions, shuffle, repeat)
        return None

    # ------------------------------------------------------------------
    # PLAYLIST MANAGEMENT
    # ------------------------------------------------------------------
    def reload_playlists(self):

        root = self.get_playlists()
        if not root:
            self.playlists = []
        else:
            pl = root.get("playlists_loop", [])
            self.playlists = [
                {
                    "id": p.get("id"),
                    "playlist": p.get("playlist", ""),
                    "refid": int(p.get("id", 0)) % 256,
                }
                for p in pl[: self.max_playlists]
            ]

        if not self.playlists:
            levelnames = "Select|No playlists"
        else:
            levelnames = "Select|" + "|".join(p["playlist"] for p in self.playlists)

        opts = {
            "LevelNames": levelnames,
            "LevelActions": "",
            "SelectorStyle": "1",
        }

        if PLAYLISTS_DEVICE_UNIT not in Devices:
            Domoticz.Device(
                Name="Lyrion Playlists",
                Unit=PLAYLISTS_DEVICE_UNIT,
                TypeName="Selector Switch",
                Switchtype=18,
                Options=opts,
                Image=self.imageID,
                Used=1,
            ).Create()
            self.log("Playlist selector created.")
        else:
            dev = Devices[PLAYLISTS_DEVICE_UNIT]
            if dev.Options.get("LevelNames", "") != levelnames:
                dev.Update(nValue=0, sValue=dev.sValue, Options=opts)
                self.log("Playlist selector updated.")

    def play_playlist_by_level(self, Level):

        # Level 0 = Select (geen actie)
        if Level == 0:
            self.log("Playlist selection reset to 'Select'.")
            return

        if Level < 10:
            return

        idx = int(Level // 10) - 1
        if idx < 0 or idx >= len(self.playlists):
            self.error("Invalid playlist index.")
            return

        playlist_name = self.playlists[idx]["playlist"]
        self.activePlaylist = playlist_name

        self.start_playlist_on_first_player(playlist_name)

        selected_level = (idx + 1) * 10
        if PLAYLISTS_DEVICE_UNIT in Devices:
            Devices[PLAYLISTS_DEVICE_UNIT].Update(nValue=0, sValue=str(selected_level))

    def start_playlist_on_first_player(self, playlist_name):

        if not self.players:
            self.log("No players online to start playlist.")
            return

        first = self.players[0]
        mac = first.get("playerid")

        # Zoek de LMS playlist ID
        pl = next((p for p in self.playlists if p["playlist"] == playlist_name), None)
        if not pl:
            self.error(f"Playlist '{playlist_name}' not found in LMS list")
            return

        playlist_id = pl["id"]

        # Laad playlist zoals LMS GUI dat doet
        self.send_playercmd(
            mac,
            ["playlistcontrol", "cmd:load", f"playlist_id:{playlist_id}"],
        )

        self.log(f"Loaded playlist '{playlist_name}' (ID {playlist_id}) via playlistcontrol")

        # Binnenkort opnieuw pollen zodat UI snel up-to-date is
        self.nextPoll = time.time() + 1

    # ------------------------------------------------------------------
    # MAIN UPDATE LOOP
    # ------------------------------------------------------------------
    def updateEverything(self):

        server = self.get_serverstatus()
        if not server:
            self.error("Lyrion server not responding.")
            return

        self.players = server.get("players_loop", []) or []

        # Ensure devices exist for each player
        for p in self.players:
            name = p.get("name", "Unknown")
            mac = p.get("playerid", "")
            if mac and not self.find_player_devices(mac):
                self.create_player_devices(name, mac)

        self.reload_playlists()

        #------------------------------------------------------------------
        # PROCESS EACH PLAYER
        #------------------------------------------------------------------
        for p in self.players:

            mac = p.get("playerid")
            if not mac:
                continue

            devices = self.find_player_devices(mac)
            if not devices:
                continue

            main, vol, text, actions, shuffle, repeat = devices
            st = self.get_status(mac) or {}

            power = int(st.get("power", 0))
            mode = st.get("mode", "stop")

            sel_level = {"pause": 10, "play": 20, "stop": 30}.get(mode, 0)
            if power == 0:
                sel_level = 0

            #------------------------------------------------------------------
            # MAIN PLAYER STATE
            #------------------------------------------------------------------
            if main in Devices:
                dev_main = Devices[main]
                n = 1 if power else 0
                s = str(sel_level)
                if dev_main.nValue != n or dev_main.sValue != s:
                    dev_main.Update(nValue=n, sValue=s)

            #------------------------------------------------------------------
            # VOLUME
            #------------------------------------------------------------------
            if vol in Devices:
                dev_vol = Devices[vol]

                # Oud volume ophalen
                old = int(dev_vol.sValue) if dev_vol.sValue.isdigit() else 0

                # Nieuw volume proberen te parsen
                raw = st.get("mixer volume", old)
                try:
                    # LMS geeft soms "35%", soms "-10", soms "35"
                    new = int(float(str(raw).replace("%", "")))
                except:
                    new = old

                # Alleen bij verandering updaten
                if new != old:
                    dev_vol.Update(nValue=1 if new > 0 else 0, sValue=str(new))
    
            #------------------------------------------------------------------
            # TRACK — metadata handling (radio + lokaal)
            #------------------------------------------------------------------
            if text in Devices:
                dev_text = Devices[text]

                # Speler uit of niet aan het spelen ? leeg trackinfo
                if power == 0 or mode in ["stop", "pause"]:
                    if dev_text.sValue != " ":
                        dev_text.Update(nValue=0, sValue=" ")
                    continue

                remote = st.get("remote", 0)
                rm = st.get("remoteMeta", {})
                pl = st.get("playlist_loop", [])

                title = ""
                artist = ""

                # 1) remoteMeta voor streams
                if remote and rm:
                    title = rm.get("title", "") or title
                    artist = rm.get("artist", "") or artist

                # 2) playlist_loop fallback
                if not title and isinstance(pl, list) and pl:
                    title = pl[0].get("title", "") or title
                    artist = pl[0].get("artist", "") or artist

                # 3) fallback: stationnaam
                if not title:
                    title = st.get("current_title", "")

                # Label opbouwen
                if not title:
                    label = " "
                elif artist:
                    label = label = f"&#127908; {artist}<br>&#127925; {title}"
                else:
                    label = title

                label = label[:255]

                # Trackchange-detectie
                track_index = st.get("playlist_cur_index")
                player_key = mac
                changed = False

                if track_index is not None:
                    if (
                        player_key not in self.lastTrackIndex
                        or self.lastTrackIndex[player_key] != track_index
                    ):
                        changed = True
                        self.lastTrackIndex[player_key] = track_index

                if dev_text.sValue != label or changed:
                    dev_text.Update(nValue=0, sValue=label)

            #------------------------------------------------------------------
            # SHUFFLE
            #------------------------------------------------------------------
            if shuffle in Devices:
                dev_shuffle = Devices[shuffle]
                try:
                    shuffle_state = int(st.get("playlist shuffle", 0))
                except Exception:
                    shuffle_state = 0
                level = shuffle_state * 10
                if dev_shuffle.sValue != str(level):
                    dev_shuffle.Update(nValue=0, sValue=str(level))

            #------------------------------------------------------------------
            # PLAYLIST SELECTOR RESET / UPDATE
            #------------------------------------------------------------------
            playlist_tracks = st.get("playlist_tracks", 0)
            playlist_name = st.get("playlist_name", "")
            remote = st.get("remote", 0)

            # Echte playlist actief: meerdere tracks, naam, en geen remote stream
            playlist_is_active = (
                playlist_tracks > 1
                and playlist_name not in ("", None)
                and remote == 0
            )

            if PLAYLISTS_DEVICE_UNIT in Devices:
                dev_pl = Devices[PLAYLISTS_DEVICE_UNIT]

                if playlist_is_active:
                    self.log(
                        f"Detected active playlist '{playlist_name}' ({playlist_tracks} tracks)"
                    )

                    # Zoek juiste level
                    found = False
                    for idx, pinfo in enumerate(self.playlists):
                        if pinfo["playlist"] == playlist_name:
                            expected_level = (idx + 1) * 10
                            found = True
                            if dev_pl.sValue != str(expected_level):
                                self.log(
                                    f"Setting playlist selector to level {expected_level} for '{playlist_name}'"
                                )
                                dev_pl.Update(nValue=0, sValue=str(expected_level))
                            break

                    if not found:
                        self.log(
                            f"Playlist '{playlist_name}' is not in Domoticz selector list"
                        )

                else:
                    # Geen echte playlist actief (radio / losse track)
                    if dev_pl.sValue != "0":
                        self.log("No playlist active - resetting selector to 'Select'")
                        dev_pl.Update(nValue=0, sValue="0")

        #------------------------------------------------------------------
        # INITIALIZATION LOG
        #------------------------------------------------------------------
        if not self.initialized:
            self.log("Initialization complete:")
            self.log(f" Players           : {len(self.players)}")
            device_count = len(Devices)
            self.log(f" Devices           : {device_count}")
            self.log(f" Playlists         : {len(self.playlists)}")
            self.log(f" Poll interval     : {self.pollInterval} sec")
            self.initialized = True

    # ------------------------------------------------------------------
    # COMMAND HANDLER
    # ------------------------------------------------------------------
    def onCommand(self, Unit, Command, Level, Hue):

        if Unit not in Devices:
            return

        dev = Devices[Unit]
        devname = dev.Name
        mac = dev.Description

        self.debug_log(
            f"onCommand: Unit={Unit}, Name={devname}, Command={Command}, Level={Level}, mac={mac}"
        )

        # Playlist selector: level 0 = 'Select', nooit naar LMS sturen
        if Unit == PLAYLISTS_DEVICE_UNIT and Command == "Set Level" and Level == 0:
            Devices[PLAYLISTS_DEVICE_UNIT].Update(nValue=0, sValue="0")
            return

        # Playlist selector: een echte playlist
        if Unit == PLAYLISTS_DEVICE_UNIT and Command == "Set Level":
            self.play_playlist_by_level(Level)
            return

        # Actions selector
        if "Actions" in devname and Command == "Set Level":
            self.handle_actions(dev, mac, Level)
            return

        # ---------------------------------
        # SHUFFLE DEVICE
        # ---------------------------------
        if "Shuffle" in devname:
            if Command == "Set Level":
                mode = int(Level // 10)
            elif Command == "Off":
                mode = 0
                Level = 0
            else:
                return

            self.send_playercmd(mac, ["playlist", "shuffle", str(mode)])

            # nValue = 1 als shuffle Songs/Albums is
            nval = 1 if mode > 0 else 0
            dev.Update(nValue=nval, sValue=str(Level))

            mode_name = {
                0: "Off",
                1: "Songs",
                2: "Albums"
            }.get(mode, f"Unknown ({mode})")

            Domoticz.Log(f"Shuffle set to : {mode_name}")
            return

        # ---------------------------------
        # REPEAT DEVICE
        # ---------------------------------
        if "Repeat" in devname:
            if Command == "Set Level":
                mode = int(Level // 10)
            elif Command == "Off":
                mode = 0
                Level = 0
            else:
                return

            self.send_playercmd(mac, ["playlist", "repeat", str(mode)])

            # nValue = 1 als repeat Track/Playlist is
            nval = 1 if mode > 0 else 0
            dev.Update(nValue=nval, sValue=str(Level))

            mode_name = {
                0: "Off",
                1: "Track",
                2: "Playlist"
            }.get(mode, f"Unknown ({mode})")

            Domoticz.Log(f"Repeat set to : {mode_name}")
            return

        # Power op hoofddevice
        if Command in ["On", "Off"] and self.is_main_device_name(devname):
            self.handle_power(dev, mac, Command)
            return

        # Volume device
        if "Volume" in devname and Command == "Set Level":
            self.handle_volume(dev, mac, Level)
            return

        # Play / Pause / Stop op hoofddevice
        if Command == "Set Level" and self.is_main_device_name(devname):
            self.handle_main_playback(dev, mac, Level)
            return

    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------
    def handle_actions(self, dev, mac, Level):

        # 10 = Send Display Text (blijft hetzelfde)
        if Level == 10:
            if not self.displayText:
                self.error("Message text (Mode4) is empty.")
                return
            self.send_display_text(mac, self.displayText)
            dev.Update(nValue=1, sValue=str(Level))
            self.log(f"SendText sent to: {mac}")
            return

        # ------------------------------
        # 20 = Sync to this player
        # ------------------------------
        if Level == 20:
            self.log(f"Syncing all players TO master: {mac}")

            # haal serverstatus op om lijst spelers te krijgen
            server = self.get_serverstatus()
            if not server:
                self.error("Cannot sync: server not responding.")
                return

            players = server.get("players_loop", [])
            if not players:
                self.error("No players found to sync.")
                return

            # SYNC = alle andere spelers syncen naar deze
            for p in players:
                other_mac = p.get("playerid")
                if other_mac and other_mac != mac:
                    self.log(f" -> syncing {other_mac} to master {mac}")
                    self.send_playercmd(other_mac, ["sync", mac])

            dev.Update(nValue=1, sValue=str(Level))
            return

        # ------------------------------
        # 30 = Unsync this player
        # ------------------------------
        if Level == 30:
            self.log(f"Unsyncing player: {mac}")
            self.send_playercmd(mac, ["sync", "-"])
            dev.Update(nValue=1, sValue=str(Level))
            return

    def handle_shuffle(self, dev, mac, Command, Level):
        if Command == "Set Level":
            mode = int(Level // 10)
        elif Command == "Off":
            mode = 0
            Level = 0
        else:
            return

        self.send_playercmd(mac, ["playlist", "shuffle", str(mode)])
        dev.Update(nValue=0, sValue=str(Level))

        mode_name = {0: "Off", 1: "Songs", 2: "Albums"}.get(
            mode, f"Unknown ({mode})"
        )
        self.log(f"Shuffle set to: {mode_name}")

    def handle_repeat(self, dev, mac, Command, Level):
        if Command == "Set Level":
            mode = int(Level // 10)
        elif Command == "Off":
            mode = 0
            Level = 0
        else:
            return

        self.send_playercmd(mac, ["playlist", "repeat", str(mode)])
        dev.Update(nValue=0, sValue=str(Level))

        mode_name = {0: "Off", 1: "Track", 2: "Playlist"}.get(
            mode, f"Unknown ({mode})"
        )
        self.log(f"Repeat set to: {mode_name}")

    def handle_power(self, dev, mac, Command):
        self.send_playercmd(mac, ["power", "1" if Command == "On" else "0"])
        dev.Update(nValue=1 if Command == "On" else 0, sValue="")
        self.log(f"Power {Command}")

    def handle_volume(self, dev, mac, Level):
        self.send_playercmd(mac, ["mixer", "volume", str(Level)])
        dev.Update(nValue=1 if Level > 0 else 0, sValue=str(Level))
        self.log(f"Volume set to {Level}%")

    def handle_main_playback(self, dev, mac, Level):
        btn_map = {
            10: ("pause.single", "Pause"),
            20: ("play.single", "Play"),
            30: ("stop", "Stop"),
        }

        if Level not in btn_map:
            return

        cmd, label = btn_map[Level]
        self.send_button(mac, cmd)
        dev.Update(nValue=1, sValue=str(Level))
        self.log(f"Player command: {label}")


# -------------------------------------------------------------------
# DOMOTICZ HOOKS
# -------------------------------------------------------------------
_plugin = LMSPlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onHeartbeat():
    _plugin.onHeartbeat()


def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)
