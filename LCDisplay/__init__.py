# -*- coding: utf-8 -*-
import time
import socket
import fcntl
import struct
import logging
import asyncio
import json
from .RPLCD.i2c import CharLCD
from time import strftime
from cbpi.api import *
from cbpi.api.config import ConfigType


logger = logging.getLogger(__name__)

# global lcd
lcd = CharLCD(i2c_expander='PCF8574', address=0x27, port=1, cols=20, rows=4, dotsize=8, charmap='A00', auto_linebreaks=True, backlight_enabled=True)


class LCDisplay(CBPiExtension):
    def __init__(self, cbpi):
        self.cbpi = cbpi
        self._task = asyncio.create_task(self.run())

    async def run(self):
        logger.info('Starting LCDisplay background task')
        while True:
            # this is the main code repeated constantly
            await self.show_standby()
        pass

    async def show_standby(self):
        ip = await self.set_ip()
        cbpi_version = await self.get_version_fo("")
        breweryname = await self.get_breweryname()
        lcd._set_cursor_mode('hide')
        lcd.cursor_pos = (0, 0)
        lcd.write_string(("CBPI       %s" % cbpi_version).ljust(20))
        lcd.cursor_pos = (1, 0)
        lcd.write_string(("%s" % breweryname).ljust(20))
        lcd.cursor_pos = (2, 0)
        lcd.write_string(("IP: %s" % ip).ljust(20))
        lcd.cursor_pos = (3, 0)
        lcd.write_string((strftime("%Y-%m-%d %H:%M:%S", time.localtime())).ljust(20))
        await asyncio.sleep(1)

    async def get_version_fo(self, path):
        version = ""
        try:
            if path is not "":
                fo = open(path, "r")
            else:
                fo = open("/usr/local/lib/python3.7/dist-packages/cbpi/__init__.py", "r")
            version = (fo.read())[15:23]  # just get the number of e.g. __version = "4.0.0.33"
            fo.close()
        finally:
            return version

    async def set_ip(self):
        if await self.get_ip('wlan0') != 'Not connected':
            ip = await self.get_ip('wlan0')
        elif await self.get_ip('eth0') != 'Not connected':
            ip = await self.get_ip('eth0')
        elif await self.get_ip('enxb827eb488a6e') != 'Not connected':
            ip = await self.get_ip('enxb827eb488a6e')
        else:
            ip = 'Not connected'
        pass
        return ip

    async def get_ip(self, interface):
        ip_addr = 'Not connected'
        so = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            ip_addr = socket.inet_ntoa(fcntl.ioctl(so.fileno(), 0x8915, struct.pack('256s', bytes(interface.encode())[:15]))[20:24])
        finally:
            pass
        return ip_addr

    async def get_breweryname(self):
        # ToDo : find a more generalist way to find the right path for config.json file
        filename = '/home/pi/cbpi4/config/config.json'
        brewery_json_obj = json.loads(open(filename).read())
        brewery = brewery_json_obj['BREWERY_NAME']['value']
        # Todo : close file?
        return brewery
        pass

    async def buzzer_gpio(self):
        global buzzer_gpio
        buzzer_gpio = self.cbpi.config.get("buzzer_gpio", None)
        if buzzer_gpio is None:
            logger.info("INIT Buzzer GPIO")
            try:
                await self.cbpi.config.add("buzzer_gpio", 5, ConfigType.SELECT, "Buzzer GPIO",
                                           [{"label": "0", "value": 0},
                                            {"label": "1", "value": 1},
                                            {"label": "2", "value": 2},
                                            {"label": "3", "value": 3},
                                            {"label": "4", "value": 4},
                                            {"label": "5", "value": 5},
                                            {"label": "6", "value": 6},
                                            {"label": "7", "value": 7},
                                            {"label": "8", "value": 8},
                                            {"label": "9", "value": 9},
                                            {"label": "10", "value": 10},
                                            {"label": "11", "value": 11},
                                            {"label": "12", "value": 12},
                                            {"label": "13", "value": 13},
                                            {"label": "14", "value": 14},
                                            {"label": "15", "value": 15},
                                            {"label": "16", "value": 16},
                                            {"label": "17", "value": 17},
                                            {"label": "18", "value": 18},
                                            {"label": "19", "value": 19},
                                            {"label": "20", "value": 20},
                                            {"label": "21", "value": 21},
                                            {"label": "22", "value": 22},
                                            {"label": "23", "value": 23},
                                            {"label": "24", "value": 24},
                                            {"label": "25", "value": 25},
                                            {"label": "26", "value": 26},
                                            {"label": "27", "value": 27}])
                buzzer_gpio = self.cbpi.config.get("buzzer_gpio", None)
            except:
                logger.warning('Unable to update config')


def setup(cbpi):
    cbpi.plugin.register("LCDisplay", LCDisplay)

