# coding=utf-8
# Copyright (c) 2021, Donald Hoffman (don.hoffman@gmail.com)

from threading import Lock

import indigo

# If this value is too short, then the hardware may miss consecutive commands (it
# has no buffering) which will totally break the communication (0.005 fails).
# Additionally, the shorter the value the higher CPU usage because the inputs
# require polling. On the flip side, if this duration is too large then momentary
# input changes (changes that last less than this duration) may be missed. 11
# milliseconds seems like a good balance.
kSleepBetweenComm = 0.011

HvacModeMap = {
    indigo.kHvacMode.Off:       "O",
    indigo.kHvacMode.Heat:      "H",
    indigo.kHvacMode.Cool:      "C",
    indigo.kHvacMode.HeatCool:  "A",
}
HvacModeMapReverse = {
    "O": indigo.kHvacMode.Off,
    "H": indigo.kHvacMode.Heat,
    "C": indigo.kHvacMode.Cool,
    "A": indigo.kHvacMode.HeatCool,
    "I": None
}
FanModeMap = {
    indigo.kFanMode.Auto:       "0",
    indigo.kFanMode.AlwaysOn:   "1",
}
FanModeMapReverse = {
    "0": indigo.kFanMode.Auto,
    "1": indigo.kFanMode.AlwaysOn,
}
DamperStatusMapReverse = {
    0: "open",
    1: "closed",
}


class RCS(object):
    def __init__(self, plugin):
        self.conn = None
        self.connLock = Lock()
        self.plugin = plugin
        self.zones = {}

    def __del__(self):
        if self.conn and self.conn.is_open:
            self.conn.close()

    def monitorZone(self, zoneIndex, dev):
        self.plugin.logger.debug("zoneIndex Type: %s" % (type(zoneIndex, )))
        self.zones[zoneIndex] = dev
        
    def unMonitorZone(self, zoneIndex):
        if zoneIndex in self.zones:
            del self.zones[zoneIndex]

    def openComm(self, serialPort):
        self.conn = self.plugin.openSerial("RCS", serialPort, 9600, timeout=1, writeTimeout=1)
        if self.conn:
            self.plugin.logger.debug("Serial port %s open." % (serialPort,))
            return True
        else:
            self.plugin.errorLog("Could not open serial port for %s" % (serialPort,))
            return False

    def closeComm(self):
        if self.conn:
            self.plugin.logger.debug("Closing comm port.")
            self.conn.close()
            self.conn = None

    def getAllZoneStatus(self):
        # Todo: Is there a way to see if fan is on in manual mode?
        if not self.conn or not self.conn.is_open:
            return
        currDev = None

        with self.connLock:
            # We get both type 1 and 2 status in same lock to minimize inconsistency.
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write(b"A=1 R=1\r")
            statusType1 = self.conn.readline()
            self.plugin.logger.debug("Received status 1 line: %s" % (statusType1,))
            self.conn.write(b"A=1 R=2\r")
            statusType2 = self.conn.readline()
            self.plugin.logger.debug("Received status 2 line: %s" % (statusType2,))

        paramList1 = statusType1.split()
        self.plugin.logger.debug(" paramList1 = %s" % (paramList1,))
        for param in paramList1:
            if param.find(b"Z=") == 0:
                self.plugin.logger.debug("Got zone index")
                zoneIndex = int(param[2:])
                self.plugin.logger.debug(type(zoneIndex))
                self.plugin.logger.debug("Got zone %d." % (zoneIndex, ))
                self.plugin.logger.debug(type(zoneIndex))
                if str(zoneIndex) in self.zones:
                    currDev = self.zones.get(str(zoneIndex), None)
                else:
                    self.plugin.logger.debug("Out of range or unknown zone %d. Skipping" % (zoneIndex,))
            elif param.find(b"T=") == 0:
                self.plugin.logger.debug("Got temperature")
                if currDev:
                    temperature = float(param[2:])
                    currDev.updateStateOnServer("temperatureInput1", temperature, uiValue=f"{temperature} °F")
                    self.plugin.logger.debug("Temperature = %f" % temperature)
            elif param.find(b"SP=") == 0:
                self.plugin.logger.debug("Got setpoint")
                if currDev:
                    setpoint = float(param[3:])
                    # Since RCS only supports one setpoint for both heat and cool, we set the indigo values for both
                    #  to be the same.
                    currDev.updateStateOnServer("setpointHeat", setpoint, uiValue=f"{setpoint} °F")
                    currDev.updateStateOnServer("setpointCool", setpoint, uiValue=f"{setpoint} °F")
                    self.plugin.logger.debug("Setpoint = %f" % setpoint)
            elif param.find(b"M=") == 0:
                self.plugin.logger.debug("Got mode")
                if currDev:
                    mode = HvacModeMapReverse[param[2:].decode('ascii')]
                    if mode:
                        currDev.updateStateOnServer("hvacOperationMode", mode)
            elif param.find(b"FM=") == 0:
                self.plugin.logger.debug("Got fan mode")
                if currDev:
                    fanMode = FanModeMapReverse[param[3:].decode("ascii")]
                    currDev.updateStateOnServer("hvacFanMode", fanMode)
            else:
                self.plugin.logger.debug("Ignored parameter %s" % (param,))

        # Getstatus type 2
        #   Cooling functions not implemented as no air conditioner to test with.
        #   Fan modes not tested as not sure they are support in my installation.
        heatCall = 0
        paramList2 = statusType2.split()
        self.plugin.logger.debug(" paramList2 = %s" % (paramList2,))
        for param in paramList2:
            if param.find(b"H1A=") == 0:
                self.plugin.logger.debug("Got heat call")
                heatCall = int(param[4:])
                self.plugin.logger.debug("Heat call for system: %s" % (heatCall,))
            elif param.find(b"D") == 0:
                self.plugin.logger.debug("Got damper info")
                zoneIndex = int(param[1:2])
                damperStatus = int(param[3:])
                self.plugin.logger.debug("Damper info for zone %d: %d" % (zoneIndex, damperStatus))
                currDev = self.zones.get(str(zoneIndex), None)
                if currDev:
                    currDev.updateStateOnServer("zoneDamperStatus", DamperStatusMapReverse[damperStatus])
                    isHeatOn = (damperStatus == 0) and (heatCall == 1)
                    currDev.updateStateOnServer("hvacHeaterIsOn", isHeatOn)
            else:
                self.plugin.logger.debug("Ignored parameter %s" % (param,))            
                                                        
    def setHvacMode(self, zoneIndex, hvacMode):
        if not self.conn or not self.conn.is_open:
            return False
        if hvacMode not in HvacModeMap:
            return False
        cmdString = "A=1 Z=%s M=%s\r" % (zoneIndex, HvacModeMap[hvacMode])
        with self.connLock:
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write(cmdString)
            self.plugin.sleep(kSleepBetweenComm)
        self.plugin.logger.debug("Sent command: %s" % (cmdString,))
        return True

    def setFanMode(self, zoneIndex, fanMode):
        if not self.conn or not self.conn.is_open:
            return False
        if fanMode not in FanModeMap:
            return False
        cmdString = "A=1 Z=%s M=%s\r" % (zoneIndex, FanModeMap[fanMode])
        with self.connLock:
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write(cmdString)
            self.plugin.sleep(kSleepBetweenComm)
        self.plugin.logger.debug("Sent command: %s" % (cmdString,))
        return True

    def setHvacSetpoint(self, zoneIndex, setpoint):
        if not self.conn or not self.conn.is_open:
            return False
        if setpoint < 40 or setpoint > 99:
            return False
        cmdString = "A=1 Z=%s SP=%s\r" % (zoneIndex, setpoint)
        with self.connLock:
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write(cmdString)
            self.plugin.sleep(kSleepBetweenComm)
        self.plugin.logger.debug("Sent command: %s" % (cmdString,))
        return True
