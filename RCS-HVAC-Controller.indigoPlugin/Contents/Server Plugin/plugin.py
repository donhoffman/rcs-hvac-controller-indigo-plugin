#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2021, Donald Hoffman (don.hoffman@gmail.com)
#

from rcs import RCS

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.
# Remove following before test.  Just here to satisfy PyDev and prevent errors during editing.
import indigo

kHvacModeEnumToStrMap = {
    indigo.kHvacMode.Cool			: u"cool",
    indigo.kHvacMode.Heat			: u"heat",
    indigo.kHvacMode.HeatCool		: u"auto",
    indigo.kHvacMode.Off			: u"off",
    indigo.kHcMode.ProgramHeat		: u"program heat",
    indigo.kHcMode.ProgramCool		: u"program cool",
    indigo.kHvacMde.ProgramHeatCool	: u"program auto"
}

kFanModeEnumToStrMap = {
    indigo.kFanMode.AlwaysOn			: u"always on",
    indigo.kFanMode.Auto				: u"auto"
}


def _lookupActionStrFromHvacMode(hvacMode):
    global kHvacModeEnumToStrMap
    return kHvacModeEnumToStrMap.get(hvacMode, u"unknown")


def _lookupActionStrFromFanMode(fanMode):
    global kFanModeEnumToStrMap
    return kFanModeEnumToStrMap.get(fanMode, u"unknown")


class Plugin(indigo.PluginBase):
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.rcs = RCS(self)
        self.debug = self.pluginPrefs[u"debugMode"]

    def __del__(self):
        indigo.PluginBase.__del__(self)

    def startup(self):
        self.debugLog(u"startup called")

    def shutdown(self):
        self.debugLog(u"shutdown called")

    def deviceStartComm(self, dev):
        self.debugLog(u"<<-- entering deviceStartComm: %s (%d - %s)" % (dev.name, dev.id, dev.deviceTypeId))
        zoneIndex = dev.pluginProps[u"zoneIndex"]
        self.rcs.monitorZone(zoneIndex, dev)
        self.rcs.getAllZoneStatus()
        self.debugLog(u"exiting deviceStartComm -->>")

    def deviceStopComm(self, dev):
        self.debugLog(u"<<-- entering deviceStopComm: %s (%d - %s)" % (dev.name, dev.id, dev.deviceTypeId))
        zoneIndex = dev.pluginProps[u"zoneIndex"]
        self.rcs.unMonitorZone(zoneIndex)
        self.debugLog(u"exiting deviceStopComm -->>")

    def runConcurrentThread(self):
        if u"serialPort" not in self.pluginPrefs:
            self.errorLog(u"Serial port not defined.  Run aborted.")
            return
        if not self.rcs.openComm(self.pluginPrefs[u"serialPort"]):
            return
        try:
            while True:
                self.rcs.getAllZoneStatus()
                self.sleep(15)
        except self.stopThread:
            self.debugLog(u"Shutting down poll loop.")
        finally:
            self.rcs.closeComm()

    def validatePrefsConfigUI(self, valuesDict):
        errorMsgDict = indigo.Dict()

        self.validateSericalPortUI(valuesDict, errorMsgDict, u"serialPort")
        if u"debugMode" not in valuesDict:
            errorMsgDict[u'debugMode'] = u"Missing debug parameter. Reconfigure and reload the RCS plugin."
        indigo.server.log(u"Debug mode configured to %s" % (valuesDict[u"debugMode"],))

        if len(errorMsgDict) > 0:
            return False, valuesDict, errorMsgDict
        return True, valuesDict

    # noinspection PyUnusedLocal
    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        errorMsgDict = indigo.Dict()

        zoneIndex = int(valuesDict[u"zoneIndex"])
        if zoneIndex < 1 or zoneIndex > 6:
            # User has not selected a valid zone index -- show an error.
            errorMsgDict[u'unitId'] = u"Select a valid zone index. Value must be 1 through 6"

        if len(errorMsgDict) > 0:
            return False, valuesDict, errorMsgDict
        self.debugLog(u"Device validated - zone index: %s" % (valuesDict[u"zoneIndex"],))
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
            self._handleChangeSetpointAction(dev, newSetpoint, u"change cool setpoint", u"setpointCool")

        # SET HEAT SETPOINT
        elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
            newSetpoint = action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, u"change heat setpoint", u"setpointHeat")

        # DECREASE/INCREASE COOL SETPOINT
        elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint - action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, u"decrease cool setpoint", u"setpointCool")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
            newSetpoint = dev.coolSetpoint + action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, u"increase cool setpoint", u"setpointCool")

        # DECREASE/INCREASE HEAT SETPOINT
        elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint - action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, u"decrease heat setpoint", u"setpointHeat")

        elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
            newSetpoint = dev.heatSetpoint + action.actionValue
            self._handleChangeSetpointAction(dev, newSetpoint, u"increase heat setpoint", u"setpointHeat")

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
        zoneIndex = dev.pluginProps[u"zoneIndex"]
        sendSuccess = self.rcs.setHvacMode(zoneIndex, newHvacMode)

        actionStr = _lookupActionStrFromHvacMode(newHvacMode)
        if sendSuccess:
            # If success then log that the command was successfully sent.
            indigo.server.log(u"Sent \"%s\" mode change to %s" % (dev.name, actionStr))

            # And then tell the Indigo Server to update the state.
            if "hvacOperationMode" in dev.states:
                dev.updateStateOnServer("hvacOperationMode", newHvacMode)
        else:
            # Else log failure but do NOT update state on Indigo Server.
            indigo.server.log(u"Send \"%s\" mode change to %s failed" % (dev.name, actionStr), isError=True)

    def _handleChangeFanModeAction(self, dev, newFanMode):
        # Command hardware module (dev) to change the fan mode here:
        zoneIndex = dev.pluginProps[u"zoneIndex"]
        sendSuccess = self.rcs.setFanMode(zoneIndex, newFanMode)

        actionStr = _lookupActionStrFromFanMode(newFanMode)
        if sendSuccess:
            # If success then log that the command was successfully sent.
            indigo.server.log(u"Sent \"%s\" fan mode change to %s" % (dev.name, actionStr))

            # And then tell the Indigo Server to update the state.
            if "hvacFanMode" in dev.states:
                dev.updateStateOnServer("hvacFanMode", newFanMode)
        else:
            # Else log failure but do NOT update state on Indigo Server.
            indigo.server.log(u"Send \"%s\" fan mode change to %s failed" % (dev.name, actionStr), isError=True)

    def _handleChangeSetpointAction(self, dev, newSetpoint, logActionName, stateKey):
        # Note:  Heat and cool must always be the same on this hardware.
        #  So we always set both to same value when one is set.

        if newSetpoint < 40.0:
            newSetpoint = 40.0  # Arbitrary -- set to whatever hardware minimum setpoint value is.
        elif newSetpoint > 95.0:
            newSetpoint = 95.0  # Arbitrary -- set to whatever hardware maximum setpoint value is.
        zoneIndex = dev.pluginProps[u"zoneIndex"]
        sendSuccess = self.rcs.setHvacSetpoint(zoneIndex, newSetpoint)

        if stateKey == u"setpointCool":
            # Command hardware module (dev) to change the cool setpoint to newSetpoint here:
            # ** IMPLEMENT ME **
            sendSuccess = True  # Set to False if it failed.
        elif stateKey == u"setpointHeat":
            # Command hardware module (dev) to change the heat setpoint to newSetpoint here:
            # ** IMPLEMENT ME **
            sendSuccess = True  # Set to False if it failed.

        if sendSuccess:
            # If success then log that the command was successfully sent.
            indigo.server.log(u"Sent \"%s\" %s to %.1f°" % (dev.name, logActionName, newSetpoint))

            # And then tell the Indigo Server to update the state.
            dev.updateStateOnServer(u"setpointCool", newSetpoint, uiValue="%.1f °F" % (newSetpoint,))
            dev.updateStateOnServer(u"setpointHeat", newSetpoint, uiValue="%.1f °F" % (newSetpoint,))
        else:
            # Else log failure but do NOT update state on Indigo Server.
            indigo.server.log(u"Send \"%s\" %s to %.1f° failed" % (dev.name, logActionName, newSetpoint), isError=True)
