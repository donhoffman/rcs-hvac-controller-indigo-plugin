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
        self.zones[str(zoneIndex)] = dev
        
    def unMonitorZone(self, zoneIndex):
        zoneIndex = str(zoneIndex)
        if zoneIndex in self.zones:
            del self.zones[zoneIndex]

    def openComm(self, serialPort):
        self.conn = self.plugin.openSerial("RCS", serialPort, 9600, timeout=1, writeTimeout=1)
        if self.conn:
            self.plugin.debugLog(u"Serial port %s open." % (serialPort,))
            return True
        else:
            self.plugin.errorLog("Could not open serial port for %s" % (serialPort,))
            return False

    def closeComm(self):
        if self.conn:
            self.plugin.debugLog(u"Closing comm port.")
            self.conn.close()
            self.conn = None

    def getAllZoneStatus(self):
        # Todo: Is there a way to see if fan is on in manual mode?
        if not self.conn and not self.conn.is_open:
            return
        currDev = None

        with self.connLock:
            # We get both type 1 and 2 status in same lock to minimize inconsistency.
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write("A=1 R=1\r")
            statusType1 = self.conn.readline()
            self.plugin.debugLog(u"Received status 1 line: %s" % (statusType1,))
            self.conn.write("A=1 R=2\r")
            statusType2 = self.conn.readline()
            self.plugin.debugLog(u"Received status 2 line: %s" % (statusType1,))

        paramList1 = statusType1.split()
        for param in paramList1:
            if param.find("Z=") == 0:
                zoneIndex = str(param[2:])
                currDev = self.zones.get(zoneIndex, None)
                if not currDev:
                    self.plugin.debugLog(u"Out of range or unknown zone %s. Skipping" % (zoneIndex,))
            elif param.find("T=") == 0:
                if currDev:
                    temperature = int(param[2:])
                    currDev.updateStateOnServer(u"temperatureInput1", temperature)
            elif param.find("SP=") == 0:
                if currDev:
                    setpoint = int(param[3:])
                    # Since RCS only supports one setpoint for both heat and cool, we set the indigo values for both
                    #  to be the same.
                    currDev.updateStateOnServer(u"setpointHeat", setpoint, uiValue=u"%.1f °F" % (setpoint,))
                    currDev.updateStateOnServer(u"setpointCool", setpoint, uiValue=u"%.1f °F" % (setpoint,))
            elif param.find("M=") == 0:
                if currDev:
                    mode = HvacModeMapReverse[str(param[2:])]
                    if mode:
                        currDev.updateStateOnServer(u"hvacOperationMode", mode)
            elif param.find("FM=") == 0:
                if currDev:
                    fanMode = FanModeMapReverse[str(param[3:])]
                    currDev.updateStateOnServer(u"hvacFanMode", fanMode)
            else:
                self.plugin.debugLog(u"Ignored parameter %s" % (param,))
                
        # Getstatus type 2
        #   Cooling functions not implemented as no air conditioner to test with.
        #   Fan modes not tested as not sure they are support in my installation.
        heatCall = 0
        paramList2 = statusType2.split()
        for param in paramList2:
            if param.find("H1A=") == 0:
                heatCall = int(param[4:])
                self.plugin.debugLog(u"Heat call for system: %s" % heatCall)
            if param.find("D") == 0:
                zoneIndex = str(param[1:2])
                damperStatus = int(param[3:])
                self.plugin.debugLog(u"Damper info for zone %s: %s" % (zoneIndex, damperStatus))
                currDev = self.zones.get(zoneIndex, None)
                if currDev:
                    currDev.updateStateOnServer(u"zoneDamperStatus", DamperStatusMapReverse[damperStatus])
                    isHeatOn = (damperStatus == 0) and (heatCall == 1)
                    currDev.updateStateOnServer(u"hvacHeaterIsOn", isHeatOn)
            else:
                self.plugin.debugLog(u"Ignored parameter %s" % (param,))            
                                                        
    def setHvacMode(self, zoneIndex, hvacMode):
        if not self.conn and not self.conn.is_open:
            return False
        if hvacMode not in HvacModeMap:
            return False
        cmdString = "A=1 Z=%s M=%s\r" % (zoneIndex, HvacModeMap[hvacMode])
        with self.connLock:
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write(cmdString)
            self.plugin.sleep(kSleepBetweenComm)
        self.plugin.debugLog(u"Sent command: %s" % (cmdString,))
        return True

    def setFanMode(self, zoneIndex, fanMode):
        if not self.conn and not self.conn.is_open:
            return False
        if fanMode not in FanModeMap:
            return False
        cmdString = "A=1 Z=%s M=%s\r" % (zoneIndex, HvacModeMap[fanMode])
        with self.connLock:
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write(cmdString)
            self.plugin.sleep(kSleepBetweenComm)
        self.plugin.debugLog(u"Sent command: %s" % (cmdString,))
        return True

    def setHvacSetpoint(self, zoneIndex, setpoint):
        if not self.conn and not self.conn.is_open:
            return False
        if setpoint < 40 or setpoint > 99:
            return False
        cmdString = "A=1 Z=%s SP=%s\r" % (zoneIndex, setpoint)
        with self.connLock:
            self.plugin.sleep(kSleepBetweenComm)
            self.conn.write(cmdString)
            self.plugin.sleep(kSleepBetweenComm)
        self.plugin.debugLog(u"Sent command: %s" % (cmdString,))
        return True
