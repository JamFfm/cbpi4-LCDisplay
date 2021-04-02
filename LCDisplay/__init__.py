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

# LCDVERSION = '5.0.01'
#
# The LCD-library and LCD-driver are taken from RPLCD Project version 1.0. The documentation:
# http://rplcd.readthedocs.io/en/stable/ very good and readable. Git is here: https://github.com/dbrgn/RPLCD.
# LCD_Address should be something like 0x27, 0x3f etc.
# See in Craftbeerpi-UI (webpage of CBPI4) settings .
# To determine address of LCD use command prompt in Raspi and type in:
# sudo i2cdetect -y 1 or sudo i2cdetect -y 0
#
# Assembled by JamFfm

logger = logging.getLogger(__name__)
DEBUG = True  # turn True to show (much) more debug info in app.log
BLINK = False  # start value for blinking the beerglass during heating only for single mode


class LCDisplay(CBPiExtension):
    def __init__(self, cbpi):
        self.cbpi = cbpi
        self._task = asyncio.create_task(self.run())

    async def run(self):
        logger.info('LCDisplay - Starting background task')
        address1 = await self.set_lcd_address()
        address = int(address1, 16)
        if DEBUG: logger.info('LCDisplay - LCD address %s %s' % (address, address1))
        charmap = await self.set_lcd_charmap()
        if DEBUG: logger.info('LCDisplay - LCD charmap: %s' % charmap)
        global lcd
        lcd = CharLCD(i2c_expander='PCF8574', address=address, port=1, cols=20, rows=4, dotsize=8, charmap=charmap,
                      auto_linebreaks=True, backlight_enabled=True)
        logger.info('LCDisplay - LCD object set')
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
        brewery = self.cbpi.config.get("BREWERY_NAME", None)
        if brewery is None:
            brewery = "no name"
        return brewery
        pass

    async def get_breweryname1(self):
        # ToDo : find a more generalist way to find the right path for config.json file
        # just an example to access a json file
        filename = '/home/pi/cbpi4/config/config.json'
        brewery_json_obj = json.loads(open(filename).read())
        brewery = brewery_json_obj['BREWERY_NAME']['value']
        # Todo : close file?
        return brewery
        pass

    async def set_lcd_address(self):
        # global lcd_address
        lcd_address = self.cbpi.config.get("LCD_address", None)
        if lcd_address is None:
            logger.info("LCD_Address added")
            try:
                await self.cbpi.config.add("LCD_address", '0x27', ConfigType.STRING, "LCD address like 0x27 or 0x3f, CBPi reboot required")
                lcd_address = self.cbpi.config.get("LCD_address", None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return lcd_address

    async def set_lcd_charmap(self):
        lcd_charmap = self.cbpi.config.get("LCD_Charactermap", None)
        if lcd_charmap is None:
            logger.info("LCD_Charactermap added")
            try:
                await self.cbpi.config.add("LCD_Charactermap", 'A00', ConfigType.SELECT, "LCD Charactermap like A00, "
                                                                                         "A02, CBPi reboot required", [{"label": "A00", "value": "A00"}, {"label": "A02", "value": "A02"}])
                lcd_charmap = self.cbpi.config.get("LCD_Charactermap", None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return lcd_charmap


def setup(cbpi):
    cbpi.plugin.register("LCDisplay", LCDisplay)

