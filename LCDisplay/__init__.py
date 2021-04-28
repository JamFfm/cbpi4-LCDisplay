# -*- coding: utf-8 -*-
import time
import socket
import fcntl
import struct
import logging
import asyncio
import json
import aiohttp
import cbpi
from .RPLCD.i2c import CharLCD
from time import strftime
from cbpi.api import *
from cbpi.api.config import ConfigType
from cbpi.api.dataclasses import Kettle, Props, Sensor
from cbpi.api.timer import Timer
from datetime import datetime
from typing import KeysView
from cbpi.api.base import CBPiBase
from cbpi.api.dataclasses import NotificationType  # INFO, WARNING, ERROR, SUCCESS
from cbpi.controller.sensor_controller import SensorController


# LCDisplay VERSION = '5.0.02'
#
# this plug in is made for CBPI4. Do not use it in CBPI3.
# The LCD-library and LCD-driver are taken from RPLCD Project version 1.0. The documentation:
# http://rplcd.readthedocs.io/en/stable/ very good and readable. Git is here: https://github.com/dbrgn/RPLCD.
# LCD_Address should be something like 0x27, 0x3f etc.
# See in Craftbeerpi-UI (webpage of CBPI4) settings .
# To determine address of LCD use command prompt in Raspi and type in:
# sudo i2cdetect -y 1 or sudo i2cdetect -y 0
#
# Assembled by JamFfm
# 02.04.2021
# 18.04.2021 progress, thanks to avollkopf
# 28.04.2021 little progress, heater state can be detected, apparently cbpicodec is not necessary to convert umlaute.
# I leave it because I woluld like to handle the A00 parameter as I am not sure if all versions of LCD can use umlaute.
# Timer detect is missing :-)

logger = logging.getLogger(__name__)
DEBUG = True  # turn True to show (much) more debug info in app.log
BLINK = False  # start value for blinking the beerglass during heating only for single mode
global lcd
# beerglass symbol
bierkrug = (
    0b11100,
    0b00000,
    0b11100,
    0b11111,
    0b11101,
    0b11101,
    0b11111,
    0b11100
)
# cooler symbol should look like snowflake but is instead a star. I use 3 of them like in refrigerators
cool = (
    0b00100,
    0b10101,
    0b01110,
    0b11111,
    0b01110,
    0b10101,
    0b00100,
    0b00000
)
# Ä symbol because in A00 LCD there is no big Ä only small ä- If you use A02 LCD this is not necessary.
awithdots = (
    0b10001,
    0b01110,
    0b10001,
    0b10001,
    0b11111,
    0b10001,
    0b10001,
    0b00000
)
# Ö symbol because in A00 LCD there is no big Ö only small ö- If you use A02 LCD this is not necessary.
owithdots = (
    0b10001,
    0b01110,
    0b10001,
    0b10001,
    0b10001,
    0b10001,
    0b01110,
    0b00000
)
# Ü symbol because in A00 LCD there is no big Ü only small ü- If you use A02 LCD this is not necessary.
uwithdots = (
    0b01010,
    0b10001,
    0b10001,
    0b10001,
    0b10001,
    0b10001,
    0b01110,
    0b00000
)
# ß symbol because in A00 LCD there is no ß If you use A02 LCD this is not necessary.
esszett = (
    0b00000,
    0b00000,
    0b11100,
    0b10010,
    0b10100,
    0b10010,
    0b11100,
    0b10000
)


class LCDisplay(CBPiExtension):
    def __init__(self, cbpi):
        self.cbpi = cbpi
        self._task = asyncio.create_task(self.run())

    async def run(self):
        logger.info('LCDisplay - Info: Starting background task')

        address = int(await self.set_lcd_address(), 16)
        logger.info('LCDisplay - LCD address: %s' % await self.set_lcd_address())

        charmap = await self.set_lcd_charmap()
        logger.info('LCDisplay - LCD charmap: %s' % charmap)

        global lcd
        try:
            lcd = CharLCD(i2c_expander='PCF8574', address=address, port=1, cols=20, rows=4, dotsize=8, charmap=charmap,
                          auto_linebreaks=True, backlight_enabled=True)
            lcd.create_char(0, bierkrug)    # u"\x00"  -->beerglass symbol
            lcd.create_char(1, cool)        # u"\x01"  -->Ice symbol
            lcd.create_char(2, awithdots)   # u"\x02"  -->Ä
            lcd.create_char(3, owithdots)   # u"\x03"  -->Ö
            lcd.create_char(4, uwithdots)   # u"\x04"  -->Ü
            lcd.create_char(5, esszett)     # u"\x05"  -->ß
            if DEBUG: logger.info('LCDisplay - Info: LCD object set')
        except Exception as e:
            if DEBUG: logger.info('LCDisplay - Error: LCD object not set, wrong LCD address: {}'.format(e))
            self.cbpi.notify('LCDisplay:', 'LCD Address is wrong. You have to choose a different LCD Address. '
                                           'Key in at Raspi prompt: sudo i2cdetect -y 1 or sudo i2cdetect -y 0',
                             NotificationType.ERROR)
        pass

        refresh = await self.set_lcd_refresh()
        logger.info('LCDisplay - LCD refresh: %s' % refresh)

        single_kettle_id = await self.set_lcd_kettle_for_single_mode()
        logger.info('LCDisplay - LCD single_kettle_id: %s' % single_kettle_id)

        display_mode = await self.set_lcd_display_mode()
        logger.info('LCDisplay - LCD display_mode: %s' % display_mode)

        unit = await self.get_cbpi_temp_unit()
        logger.info('LCDisplay - LCD unit: °%s' % unit)

        single_kettle_id = await self.set_lcd_kettle_for_single_mode()
        logger.info('LCDisplay - LCD single_kettle_id: %s' % single_kettle_id)

        sensor_for_sensor_mode = await self.set_lcd_sensortype_for_sensor_mode()
        logger.info('LCDisplay - LCD sensor_for_sensor_mode: %s' % sensor_for_sensor_mode)

        # testing area
        # try:
            # kettle_heater_id = "P2v35bB4YGuYba75WzN6NT"
            # heater = self.cbpi.actor.find_by_id(kettle_heater_id)
            # kettle_heater_status = heater.instance.state
            # logger.info("kettle_heater_status {}".format(kettle_heater_status))
        # except Exception as e:
            # logger.error(e)

        # *********************************************************************************************************
        while True:
            # this is the main code repeated constantly
            display_mode = await self.set_lcd_display_mode()
            single_kettle_id = await self.set_lcd_kettle_for_single_mode()
            refresh = await self.set_lcd_refresh()
            sensortype = await self.set_lcd_sensortype_for_sensor_mode()
            active_step = await self.get_active_step_values()
            # print(active_step)
            if active_step != 'no active step' and display_mode == 'Multidisplay':
                # print(active_step['active_step_name'] + 'Multidisplay')
                await self.show_multidisplay(refresh, charmap)
            elif active_step != 'no active step' and display_mode == 'Singledisplay':
                # print(active_step['active_step_name'] + 'Singledisplay')
                await self.show_singledisplay(single_kettle_id, charmap)
            elif active_step != 'no active step' and display_mode == 'Sensordisplay':
                # print(active_step['active_step_name'] + 'Sensordisplay')
                await self.show_sensordisplay(sensortype, refresh, charmap)
            else:
                await self.show_standby()
            pass
        pass
        # *********************************************************************************************************

    async def show_standby(self):
        ip = await self.set_ip()
        cbpi_version = await self.get_cbpi_version()
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

    async def show_multidisplay(self, refresh_time=2.0, charmap="A00"):

        kettle_heater_status = 1
        line1 = (("Multidisplay").ljust(20))
        line2 = (("Multidisplay").ljust(20))
        line3 = (("Multidisplay").ljust(20))
        line4 = ((strftime("%Y-%m-%d %H:%M:%S", time.localtime())).ljust(20))

        lcd._set_cursor_mode('hide')
        lcd.cursor_pos = (0, 0)
        lcd.write_string(line1.ljust(20))
        lcd.cursor_pos = (0, 19)
        if kettle_heater_status != 0:
            lcd.write_string(u"\x00")
        lcd.cursor_pos = (1, 0)
        lcd.write_string(line2.ljust(20))
        lcd.cursor_pos = (2, 0)
        lcd.write_string(line3.ljust(20))
        lcd.cursor_pos = (3, 0)
        lcd.write_string(line4.ljust(20))
        await asyncio.sleep(refresh_time)

    async def show_singledisplay(self, kettle_id, charmap="A00"):

        steps = await self.get_active_step_values()
        stepname1 = steps['active_step_name']
        stepname = await self.cbidecode(stepname1, charmap)

        kettlevalues = await self.get_kettle_values(kettle_id)
        kettle_name1 = kettlevalues['kettle_name']
        kettle_name = await self.cbidecode(kettle_name1, charmap)
        # kettle_name = kettle_name1
        kettle_target_temp = kettlevalues['kettle_target_temp']
        kettle_sensor_id = kettlevalues['kettle_sensor_id']
        kettle = self.cbpi.kettle.find_by_id(kettle_id)
        heater = self.cbpi.actor.find_by_id(kettle.heater)
        kettle_heater_status = heater.instance.state
        # logger.info("kettle_heater_status main {}".format(kettle_heater_status))
        lcd_unit = await self.get_cbpi_temp_unit()

        is_timer_running = True   # todo just moc mode

        # line1 the stepname
        line1 = ('%s' % stepname.ljust(20)[:20])

        # line2 when steptimer is running show remaining time and kettlename
        if is_timer_running is not True:
            time_remaining = "00:01:01"  # todo just moc mode
            line2 = (("%s %s" % (kettle_name.ljust(12)[:11], time_remaining)).ljust(20)[:20])
            pass
        else:
            line2 = ('%s' % kettle_name.ljust(20)[:20])
        pass

        # line 3 Target temp
        line3 = ("Targ. Temp:%6.2f%s%s" % (float(kettle_target_temp), "°", lcd_unit)).ljust(20)[:20]

        # line 4 Current temp
        try:
            sensor_value = self.cbpi.sensor.get_sensor_value(kettle_sensor_id).get('value')
            line4 = ("Curr. Temp:%6.2f%s%s" % (float(sensor_value), "°", lcd_unit)).ljust(20)[:20]
        except Exception as e:
            logger.error(e)
            line4 = (u"Curr. Temp: {}".format("No Data"))[:20]

        lcd._set_cursor_mode('hide')
        lcd.cursor_pos = (0, 0)
        lcd.write_string(line1.ljust(20))
        lcd.cursor_pos = (0, 19)
        global BLINK
        if BLINK is False and kettle_heater_status is True:
            lcd.write_string("\x00")
            BLINK = True
        else:
            lcd.write_string(" ")
            BLINK = False
        lcd.cursor_pos = (1, 0)
        lcd.write_string(line2.ljust(20))
        lcd.cursor_pos = (2, 0)
        lcd.write_string(line3.ljust(20))
        lcd.cursor_pos = (3, 0)
        lcd.write_string(line4.ljust(20))
        await asyncio.sleep(1)

    async def show_sensordisplay(self, sensortype, refresh_time=2.0, charmap="A00"):

        line1 = 'CBPi3 LCD Sensormode'
        line2 = '--------------------'
        line3 = (("Sensordisplay").ljust(20))
        line4 = ((strftime("%Y-%m-%d %H:%M:%S", time.localtime())).ljust(20))

        lcd._set_cursor_mode('hide')
        lcd.cursor_pos = (0, 0)
        lcd.write_string(line1.ljust(20))
        lcd.cursor_pos = (1, 0)
        lcd.write_string(line2.ljust(20))
        lcd.cursor_pos = (2, 0)
        lcd.write_string(line3.ljust(20))
        lcd.cursor_pos = (3, 0)
        lcd.write_string(line4.ljust(20))
        await asyncio.sleep(refresh_time)

    async def get_cbpi_version(self):
        try:
            version = self.cbpi.version
        except Exception as e:
            logger.warning('no cbpi version found')
            logger.warning(e)
            version = "no vers."
        return version

    async def get_cbpi_temp_unit(self):
        try:
            unit = self.cbpi.config.get("TEMP_UNIT", None)
        except Exception as e:
            logger.warning('no cbpi temp. unit found')
            logger.warning(e)
            unit = "na"
        pass
        return unit

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
            ip_addr = socket.inet_ntoa(
                fcntl.ioctl(so.fileno(), 0x8915, struct.pack('256s', bytes(interface.encode())[:15]))[20:24])
        except Exception as e:
            logger.warning('no ip found')
            logger.warning(e)
            return ip_addr
        finally:
            pass
        return ip_addr

    async def get_breweryname(self):
        try:
            brewery = self.cbpi.config.get("BREWERY_NAME", None)
        except Exception as e:
            logger.warning('no breweryname found')
            logger.warning(e)
            brewery = "no name"
        pass
        return brewery

    async def get_breweryname1(self):
        # ToDo : not used
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
        lcd_address = self.cbpi.config.get("LCD_Address", None)
        if lcd_address is None:
            logger.info("LCD_Address added")
            try:
                await self.cbpi.config.add("LCD_Address", '0x27', ConfigType.STRING,
                                           "LCD address like 0x27 or 0x3f, CBPi reboot required")
                lcd_address = self.cbpi.config.get("LCD_Address", None)
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
                                                                                         "A02, CBPi reboot required",
                                           [{"label": "A00", "value": "A00"}, {"label": "A02", "value": "A02"}])
                lcd_charmap = self.cbpi.config.get("LCD_Charactermap", None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return lcd_charmap

    async def set_lcd_refresh(self):
        ref = self.cbpi.config.get('LCD_Refresh', None)
        if ref is None:
            logger.info("LCD_Refresh added")
            try:
                await self.cbpi.config.add('LCD_Refresh', 3, ConfigType.SELECT,
                                           'Time to remain till next display in sec, NO! CBPi reboot '
                                           'required', [{"label": "1s", "value": 1}, {"label": "2s", "value": 2},
                                                        {"label": "3s", "value": 3}, {"label": "4s", "value": 4},
                                                        {"label": "5s", "value": 5}, {"label": "6s", "value": 6}])
                ref = self.cbpi.config.get('LCD_Refresh', None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return ref

    async def set_lcd_display_mode(self):
        mode = self.cbpi.config.get('LCD_Display_Mode', None)
        if mode is None:
            logger.info("LCD_Display_Mode added")
            try:
                await self.cbpi.config.add('LCD_Display_Mode', 'Multidisplay', ConfigType.SELECT,
                                           'select the mode of the LCD Display, consult readme, NO! CBPi reboot '
                                           'required', [{"label": "Multidisplay", "value": 'Multidisplay'},
                                                        {"label": "Singledisplay", "value": 'Singledisplay'},
                                                        {"label": "Sensordisplay", "value": 'Sensordisplay'}])
                mode = self.cbpi.config.get('LCD_Display_Mode', None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return mode

    async def set_lcd_sensortype_for_sensor_mode1(self):
        # ToDo : not used
        sensor_type = self.cbpi.config.get('LCD_Display_Sensortype', None)
        if sensor_type is None:
            try:
                await self.cbpi.config.add('LCD_Display_Sensortype', '', ConfigType.SENSOR,
                                           'select the type of sensors to be displayed in LCD, consult readme, '
                                           'NO! CBPi reboot required')
                logger.info("LCD_Display_Sensortype added")
                sensor_type = self.cbpi.config.get('LCD_Display_Sensortype', None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return sensor_type

    async def set_lcd_sensortype_for_sensor_mode(self):
        sensor_type = self.cbpi.config.get('LCD_Display_Sensortype', None)
        if sensor_type is None:
            logger.info("LCD_Display_Sensortype added")
            try:
                await self.cbpi.config.add('LCD_Display_Sensortype', 'ONE_WIRE_SENSOR', ConfigType.SELECT,
                                           'select the type of sensors to be displayed in LCD, consult readme, '
                                           'NO! CBPi reboot required',
                                           [{"label": "ONE_WIRE_SENSOR", "value": 'ONE_WIRE_SENSOR'},
                                            {"label": "iSpindel", "value": 'iSpindel'},
                                            {"label": "MQTT_SENSOR", "value": 'MQTT_SENSOR'},
                                            {"label": "iSpindel", "value": 'iSpindel'},
                                            {"label": "eManometer", "value": 'eManometer'},
                                            {"label": "PHSensor", "value": 'PHSensor'},
                                            {"label": "Http_Sensor", "value": 'Http_Sensor'}])
                sensor_type = self.cbpi.config.get('LCD_Display_Sensortype', None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return sensor_type

    async def set_lcd_kettle_for_single_mode(self):
        kettle_id = self.cbpi.config.get('LCD_Singledisplay_Kettle', None)
        if kettle_id is None:
            logger.info("LCD_Singledisplay_Kettle added")
            try:
                await self.cbpi.config.add('LCD_Singledisplay_Kettle', '', ConfigType.KETTLE,
                                           'select the type of sensors to be displayed in LCD, consult readme, '
                                           'NO! CBPi reboot required')
                kettle_id = self.cbpi.config.get('LCD_Singledisplay_Kettle', None)
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass
        pass
        return kettle_id

    async def cbidecode(self, string, charmap="A00"):  # Changes some german Letters to be displayed
        if charmap == "A00":
            # if DEBUG: logger.info('LCDDisplay  - string: %s' % string)
            replaced_text = string.replace(u"Ä", u"\x02").replace(u"Ö", u"\x03").replace(u"Ü", u"\x04").replace(u"ß",
                                                                                                                u"\x05")
            # if DEBUG: logger.info('LCDDisplay  - replaced_text: %s' % replaced_text)
            return replaced_text
        else:
            return string
        pass

    async def get_next_hop_timer(self, active_step, time_left):
        hop_timers = []
        for x in range(1, 6):
            try:
                hop = int((active_step['Hop_' + str(x)])) * 60
            except:
                hop = None
            if hop is not None:
                hop_left = time_left - hop
                if hop_left > 0:
                    hop_timers.append(hop_left)
                    if DEBUG: logger.info("LCDDisplay  - get_next_hop_timer %s %s" % (x, str(hop_timers)))
                pass
            pass
        pass

        if len(hop_timers) != 0:
            next_hop_timer = time.strftime("%H:%M:%S", time.gmtime(min(hop_timers)))
        else:
            next_hop_timer = None
        return next_hop_timer
        pass

    async def is_step_running1(self):
        # ToDo : not used and not working (unluckily)
        try:
            url = "http://127.0.0.1:8000/step2/"
            # url = "http://127.0.0.1:8000/recipe/"

            conn = aiohttp.TCPConnector(
                family=0,
                ssl=None,
                verify_ssl=False,
                # login="pi",
                local_addr=("127.0.0.1", 8000)
            )

            # conn = aiohttp.BaseConnector()
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get(url) as response:
                    print("test")
                    logger.info('steps2 %s' % response.text())
                    return await response.text()
        except Exception as e:
            logger.warning(e)
        pass

    async def get_active_step_values(self):
        try:
            step_json_obj = self.cbpi.step.get_state()
            steps = step_json_obj['steps']
            # if DEBUG: logger.info("steps %s" % steps)
            # if DEBUG: logger.info("indices %s" % str(len(steps)))
            i = 0
            result = 'no active step'
            while i < len(steps):
                if steps[i]["status"] == "A":
                    active_step_name = ("Name: %s" % (steps[i]["name"]))
                    # print(active_step_name)
                    active_step_status = ("Status: %s" % (steps[i]["status"]))
                    active_step_state_text = ("Status: %s" % (steps[i]["state_text"]))
                    # print(active_step_status)
                    active_step_target_temp = ("Target Temp: %s°C" % (steps[i]["props"]["Temp"]))
                    # print(active_step_target_temp)
                    active_step_timer_value = ("Timer: %s" % (steps[i]["props"]["Timer"]))
                    # print(active_step_timer_value)
                    return {'active_step_name': active_step_name,
                            'active_step_status': active_step_status,
                            'active_step_state_text': active_step_state_text,
                            'active_step_target_temp': active_step_target_temp,
                            'active_step_timer_value': active_step_timer_value}
                else:
                    result = 'no active step'
                pass
                i = i + 1
            pass
            return result

        except Exception as e:
            logger.warning(e)
            return {'active_step_name': 'error',
                    'active_step_status': 'error',
                    'active_step_target_temp': 'error',
                    'active_step_timer_value': 'error'}
        pass

    pass

    async def get_kettle_values(self, kettle_id):
        try:
            kettle_json_obj = self.cbpi.kettle.get_state()
            kettles = kettle_json_obj['data']
            # if DEBUG: logger.info("kettles %s" % kettles)
            i = 0
            result = None
            while i < len(kettles):
                if kettles[i]["id"] == kettle_id:
                    kettle_id = (kettles[i]["id"])
                    kettle_name = (kettles[i]["name"])
                    # print(kettle_name)
                    kettle_heater_id = (kettles[i]["heater"])
                    # print(kettle_heater_id)
                    kettle_sensor_id = (kettles[i]["sensor"])
                    # print(kettle_sensor_id)
                    kettle_target_temp = (kettles[i]["target_temp"])
                    # print(kettle_target_temp)
                    return {'kettle_id': kettle_id,
                            'kettle_name': kettle_name,
                            'kettle_heater_id': kettle_heater_id,
                            'kettle_sensor_id': kettle_sensor_id,
                            'kettle_target_temp': kettle_target_temp}
                else:
                    result = 'no kettle found with id %s' % kettle_id
                pass
                i = i + 1
            pass
            return result
        except Exception as e:
            logger.warning(e)
            return {'kettle_id': 'error',
                    'kettle_name': 'error',
                    'kettle_heater_id': 'error',
                    'kettle_sensor_id': 'error',
                    'kettle_target_temp': 'error'}
        pass

    pass


def setup(cbpi):
    cbpi.plugin.register("LCDisplay", LCDisplay)

