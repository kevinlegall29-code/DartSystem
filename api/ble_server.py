"""
Serveur BLE GATT — le Raspberry Pi expose les événements de fléchettes en Bluetooth.

L'app (Flutter) se connecte, s'abonne à la caractéristique "events" et reçoit
des notifications JSON :
  {"t":"dart","label":"T20","value":60,"mult":3,"conf":0.9}
  {"t":"takeout"}
  {"t":"ping"}

Service  UUID : a1b2c3d4-0001-4a5b-8c6d-1234567890ab
Char events  : a1b2c3d4-0002-4a5b-8c6d-1234567890ab  (read + notify)

Tolérant : si bless/BlueZ indisponible, le reste de l'app fonctionne (WiFi).
"""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

SERVICE_UUID = "a1b2c3d4-0001-4a5b-8c6d-1234567890ab"
CHAR_UUID    = "a1b2c3d4-0002-4a5b-8c6d-1234567890ab"
DEVICE_NAME  = "DartSystem"


class BLEServer:
    def __init__(self):
        self._server = None
        self._loop = None
        self._available = False

    async def start(self):
        """Démarre le périphérique BLE. Retourne True si OK."""
        try:
            from bless import (
                BlessServer,
                GATTCharacteristicProperties,
                GATTAttributePermissions,
            )
        except ImportError:
            logger.warning("BLE indisponible (bless non installé) — mode WiFi seul")
            return False

        try:
            self._loop = asyncio.get_running_loop()
            self._server = BlessServer(name=DEVICE_NAME, loop=self._loop)

            await self._server.add_new_service(SERVICE_UUID)
            props = (GATTCharacteristicProperties.read
                     | GATTCharacteristicProperties.notify)
            perms = GATTAttributePermissions.readable
            await self._server.add_new_characteristic(
                SERVICE_UUID, CHAR_UUID, props, b'{"t":"hello"}', perms
            )

            await self._server.start()
            self._available = True
            logger.info(f"BLE actif — périphérique '{DEVICE_NAME}'")
            return True
        except Exception as e:
            logger.warning(f"BLE non démarré : {e} — mode WiFi seul")
            self._available = False
            return False

    async def stop(self):
        if self._server:
            try:
                await self._server.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------

    def notify(self, event: dict):
        """Thread-safe : pousse un événement vers l'app BLE (appelé depuis le thread moteur)."""
        if not self._available or self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._do_notify(event), self._loop)
        except Exception as e:
            logger.debug(f"BLE notify échec : {e}")

    async def _do_notify(self, event: dict):
        try:
            data = json.dumps(event, separators=(",", ":")).encode()
            char = self._server.get_characteristic(CHAR_UUID)
            char.value = data
            self._server.update_value(SERVICE_UUID, CHAR_UUID)
        except Exception as e:
            logger.debug(f"BLE update échec : {e}")


# Singleton
ble_server = BLEServer()
