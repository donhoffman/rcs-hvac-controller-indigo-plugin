#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2021, Donald Hoffman (don.hoffman@gmail.com)
#

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.
# Remove following before test.  Just here to satisfy PyDev and prevent errors during editing.
import indigo

from rcs import RCS

kHvacModeEnumToStrMap = {
    indigo.kHvacMode.Cool:              "cool",
    indigo.kHvacMode.Heat:              "heat",
    indigo.kHvacMode.HeatCool:          "auto",
    indigo.kHvacMode.Off:               "off",
    indigo.kHvacMode.ProgramHeat:       "program heat",
    indigo.kHvacMode.ProgramCool:       "program cool",
    indigo.kHvacMode.ProgramHeatCool:   "program auto"
}

kFanModeEnumToStrMap = {
    indigo.kFanMode.AlwaysOn:           "always on",
    indigo.kFanMode.Auto:               "auto"
}


def _lookupActionStrFromHvacMode(hvacMode):
    global kHvacModeEnumToStrMap
    return kHvacModeEnumToStrMap.get(hvacMode, "unknown")


def _lookupActionStrFromFanMode(fanMode):
    global kFanModeEnumToStrMap
    return kFanModeEnumToStrMap.get(fanMode, "unknown")


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super().__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.debug = self.pluginPrefs.get('debugMode', True)
        self.rcs = RCS(self)

    def __del__(self):
        indigo.PluginBase.__del__(self)

    def startup(self):
        self.logger.debug("startup called")

    def shutdown(self):
        self.logger.debug("shutdown called")

    def deviceStartComm(self, dev):
        self.logger.debug("<<-- entering deviceStartComm: %s (%d - %s)" % (dev.name, dev.id, dev.deviceTypeId))
        zoneIndex = dev.pluginProps["zoneIndex"]
        self.rcs.monitorZone(zoneIndex, dev)
        self.logger.debug("exiting deviceStartComm -->>")

    def deviceStopComm(self, dev):
        self.logger.debug("<<-- entering deviceStopComm: %s (%d - %s)" % (dev.name, dev.id, dev.deviceTypeId))
        zoneIndex = dev.pluginProps["zoneIndex"]
        self.rcs.unMonitorZone(zoneIndex)
        self.logger.debug("exiting deviceStopComm -->>")

    def runConcurrentThread(self):
        self.logger.debug("Starting concurrent thread...")

        if self.pluginPrefs['serialPort_serialConnType'] != 'local':
            self.errorLog("Only local serial ports supported.  Run aborted.")
            return
        if 'serialPort_serialPortLocal' not in self.pluginPrefs:
            self.errorLog("Missing serial port.  Run aborted.")
            return
        if not self.rcs.openComm(self.pluginPrefs["serialPort_serialPortLocal"]):
            return
        try:
            while True:
                self.rcs.getAllZoneStatus()
                self.sleep(15)
        except self.StopThread:
            self.logger.debug("Shutting down poll loop.")
        finally:
            self.rcs.closeComm()

    def validatePrefsConfigUI(self, valuesDict):
        errorMsgDict = indigo.Dict()

        self.validateSerialPortUI(valuesDict, errorMsgDict, "serialPort")
        if "debugMode" not in valuesDict:
            errorMsgDict[u'debugMode'] = "Missing debug parameter. Reconfigure and reload the RCS plugin."
        indigo.server.log("Debug mode configured to %s" % (valuesDict["debugMode"],))

        if len(errorMsgDict) > 0:
            return False, valuesDict, errorMsgDict
        return True, valuesDict

    # noinspection PyUnusedLocal
    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        errorMsgDict = indigo.Dict()

        zoneIndex = int(valuesDict["zoneIndex"])
        if zoneIndex < 1 or zoneIndex > 6:
            # User has not selected a valid zone index -- show an error.
            errorMsgDict[u'unitId'] = "Select a valid zone index. Value must be 1 through 6"

        if len(errorMsgDict) > 0:
            return False, valuesDict, errorMsgDict
        self.logger.debug("Device validated - zone index: %s" % (valuesDict["zoneIndex"],))
        return True, valuesDict

    def actionControlThermostat(self, action, dev):
        # SET HVAC MODE
        if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
            self._handleChangeHvacModeAction(dev, action.actionMode)

        # SET FAN MODE
        elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:
            self._handleChangeFanModeAction(dev, action.actionMode)

        # SET COOL SETPOINT
        elif action.thermostatAction == indigo.kThermostatAction.SetCoolSetpoint:
            newSetpoint = action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, "change cool setpoint", "setpointCool")

        # SET HEAT SETPOINT
        elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
            newSetpoint = action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, "change heat setpoint", "setpointHeat")

        # DECREASE/INCREASE COOL SETPOINT
        elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint - action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, "decrease cool setpoint", "setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint + action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, "increase cool setpoint", "setpointCool")

        # DECREASE/INCREASE HEAT SETPOINT
        elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint - action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, "decrease heat setpoint", "setpointHeat")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint + action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, "increase heat setpoint", "setpointHeat")

        # REQUEST STATE UPDATES
        elif action.thermostatAction in [indigo.kThermostatAction.RequestStatusAll,
                                         indigo.kThermostatAction.RequestMode,
                                         indigo.kThermostatAction.RequestEquipmentState,
                                         indigo.kThermostatAction.RequestTemperatures,
                                         indigo.kThermostatAction.RequestHumidities,
                                         indigo.kThermostatAction.RequestDeadbands,
                                         indigo.kThermostatAction.RequestSetpoints]:
            self.rcs.getAllZoneStatus()

    def _handleChangeHvacModeAction(self, dev, newHvacMode):
        # Command hardware module (dev) to change the thermostat mode here:
        zoneIndex = dev.pluginProps["zoneIndex"]
        sendSuccess = self.rcs.setHvacMode(zoneIndex, newHvacMode)

        actionStr = _lookupActionStrFromHvacMode(newHvacMode)
        if sendSuccess:
            # If success then log that the command was successfully sent.
            indigo.server.log("Sent \"%s\" mode change to %s" % (dev.name, actionStr))

            # And then tell the Indigo Server to update the state.
            if "hvacOperationMode" in dev.states:
                dev.updateStateOnServer("hvacOperationMode", newHvacMode)
        else:
            # Else log failure but do NOT update state on Indigo Server.
            indigo.server.log("Send \"%s\" mode change to %s failed" % (dev.name, actionStr), isError=True)

    def _handleChangeFanModeAction(self, dev, newFanMode):
        # Command hardware module (dev) to change the fan mode here:
        zoneIndex = dev.pluginProps["zoneIndex"]
        sendSuccess = self.rcs.setFanMode(zoneIndex, newFanMode)

        actionStr = _lookupActionStrFromFanMode(newFanMode)
        if sendSuccess:
            # If success then log that the command was successfully sent.
            indigo.server.log("Sent \"%s\" fan mode change to %s" % (dev.name, actionStr))

            # And then tell the Indigo Server to update the state.
            if "hvacFanMode" in dev.states:
                dev.updateStateOnServer("hvacFanMode", newFanMode)
        else:
            # Else log failure but do NOT update state on Indigo Server.
            indigo.server.log("Send \"%s\" fan mode change to %s failed" % (dev.name, actionStr), isError=True)

    # noinspection PyUnusedLocal
    def _handleChangeSetpointAction(self, dev, newSetpoint, logActionName, stateKey):
        # Note:  Heat and cool must always be the same on this hardware.
        #  So we always set both to same value when one is set.

        if newSetpoint < 40.0:
            newSetpoint = 40.0  # Arbitrary -- set to whatever hardware minimum setpoint value is.
        elif newSetpoint > 95.0:
            newSetpoint = 95.0  # Arbitrary -- set to whatever hardware maximum setpoint value is.
        zoneIndex = dev.pluginProps["zoneIndex"]
        sendSuccess = self.rcs.setHvacSetpoint(zoneIndex, int(newSetpoint))

        if sendSuccess:
            # If success then log that the command was successfully sent.
            indigo.server.log("Sent \"%s\" %s to %.1f°" % (dev.name, logActionName, newSetpoint))

            # And then tell the Indigo Server to update the state.
            dev.updateStateOnServer("setpointCool", newSetpoint, uiValue="%.1f °F" % (newSetpoint,))
            dev.updateStateOnServer("setpointHeat", newSetpoint, uiValue="%.1f °F" % (newSetpoint,))
        else:
            # Else log failure but do NOT update state on Indigo Server.
            indigo.server.log("Send \"%s\" %s to %.1f° failed" % (dev.name, logActionName, newSetpoint), isError=True)
