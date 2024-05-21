#############################################################################
# Author: parenti
#
# Created on February 05, 2024, 11:53 AM
# from template 'minimal middlelayer' of Karabo 2.19.3
#
# This file is intended to be used together with Karabo:
#
# http://www.karabo.eu
#
# IF YOU REQUIRE ANY LICENSING AND COPYRIGHT TERMS, PLEASE ADD THEM HERE.
# Karabo itself is licensed under the terms of the MPL 2.0 license.
#############################################################################

from asyncio import CancelledError
from time import time

import numpy as np
from pyAndorSDK3 import AndorSDK3, CameraException, ErrorCodes

from imageSourcePy.CameraImageSourceMdl import CameraImageSource
from karabo.middlelayer import (
    AccessMode, Assignment, Bool, Double, EncodingType, MetricPrefix,
    Overwrite, Slot, State, String, Timestamp, UInt8, UInt16, UInt32, UInt64,
    Unit, background, coslot, isSet, sleep)
from processing_utils.moving_average import MovingAverage
from processing_utils.rate_calculator import RateCalculator

from ._version import version as deviceVersion

DATA_TYPE_MAP = {
    # Pixel Encoding: Karabo Type
    "Mono8": UInt8,
    "Mono12": UInt16,
    "Mono12Packed": UInt16,
    "Mono16": UInt16,
    "Mono32": UInt32}

FEATURE_MAP = {
    # Karabo Key: Feature Name
    "cycleMode": "CycleMode",
    "frameCount": "FrameCount",
    "exposureTime": "ExposureTime",
    "frameRateTarget": "FrameRate",
    "aoiHBin": "AOIHBin",
    "aoiWidth": "AOIWidth",
    "aoiLeft": "AOILeft",
    "aoiVBin": "AOIVBin",
    "aoiHeight": "AOIHeight",
    "aoiTop": "AOITop",
    "pixelReadoutRate": "PixelReadoutRate",
    "pixelEncoding": "PixelEncoding",
    "bitDepth": "BitDepth",
    "bytesPerPixel": "BytesPerPixel",
    "triggerMode": "TriggerMode",
    "externalTriggerDelay": "ExternalTriggerDelay",
    "electronicShutteringMode": "ElectronicShutteringMode",
    "fanSpeed": "FanSpeed",
    "sensorCooling": "SensorCooling",
    "temperatureControl": "TemperatureControl"}

# Updating a camera feature can affect the value or options of another one.
# Here is a dictionary of known relations.
RELATED_PROPERTIES = {
    # Karabo <key>: Properties potentially affected by a change in <key>
    "exposureTime": ("frameRateTarget",),
    "pixelReadoutRate": ("frameRateTarget", ),
    "pixelEncoding": ("bitDepth", "bytesPerPixel", ),
    "aoiHBin": ("aoiWidth", ),
    "aoiWidth": ("aoiLeft", ),
    "aoiLeft": ("aoiWidth", ),
    "aoiVBin": ("aoiHeight", ),
    "aoiHeight": ("aoiTop", ),
    "aoiTop": ("aoiHeight", )}

# Updating some camera features will affect e.g. the image shape or data type,
# thus a schema update for the output channel will be needed.
SCHEMA_CHANGING_PROPERTIES = {
    "aoiHBin", "aoiWidth", "aoiVBin", "aoiHeight", "pixelEncoding"}

# Sleep time between two connect attempts
RECONNECT_TIME = 5


class AndorSdk3Camera(CameraImageSource):
    __version__ = deviceVersion

    camera = None

    def sync_feature(self, key):
        """Synchronizes the property in the Karabo device with the current
        value on the camera."""
        if not self.camera:
            return

        feature = FEATURE_MAP[key]
        value = getattr(self.camera, feature)
        if getattr(self, key).value != value:
            self.logger.debug(
                f"Feature {feature} changed. Updating to {value}")
            setattr(self, key, value)

    def set_feature(self, key, value):
        new_value = value.value
        if self.camera:
            feature = FEATURE_MAP[key]
            current_value = getattr(self.camera, feature)
            if isSet(new_value) and current_value != new_value:
                self.logger.debug(f"Setting {feature} to {new_value}")
                setattr(self.camera, feature, new_value)
        setattr(self, key, new_value)

    serialNumber = String(
        displayedName="Serial Number",
        accessMode=AccessMode.INITONLY,
        assignment=Assignment.MANDATORY)

    cameraModel = String(
        displayedName="Camera Model",
        accessMode=AccessMode.READONLY)

    interfaceType = String(
        displayedName="Interface Type",
        accessMode=AccessMode.READONLY)

    firmwareVersion = String(
        displayedName="Firmware Version",
        accessMode=AccessMode.READONLY)

    clockFrequency = UInt32(
        displayedName="Clock Frequency",
        description="The frequency of the camera internal clock.",
        unitSymbol=Unit.HERTZ,
        accessMode=AccessMode.READONLY)

    timestampClock = UInt64(
        displayedName="Camera Clock",
        description="The current value of the camera internal clock.",
        accessMode=AccessMode.READONLY)

    @String(
        displayedName="Cycle Mode",
        description="Continuous: keep acquiring until acquisition is stopped. "
                    "Fixed: the camera acquires 'Frame Count' images and "
                    "stops automatically.",
        defaultValue="Continuous",
        allowedStates={State.UNKNOWN, State.ON})
    async def cycleMode(self, value):
        self.set_feature("cycleMode", value)
        if value.value == "Fixed":
            # 'frameCount' can only be set when in 'Fixed' cycle mode
            self.set_feature("frameCount", self.frameCount)

    @UInt32(
        displayedName="Frame Count",
        description="Number of frames to acquire when in 'Fixed' cycle mode.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def frameCount(self, value):
        if self.cycleMode.value == "Fixed":
            # Can only be set on the camera in "Fixed" cycle mode
            self.set_feature("frameCount", value)
        else:
            self.frameCount = value

    @Double(
        displayedName="Exposure Time",
        minInc=0.0,
        unitSymbol=Unit.SECOND,
        allowedStates={State.UNKNOWN, State.ON})
    async def exposureTime(self, value):
        self.set_feature("exposureTime", value)

    @Double(
        displayedName="Target Frame Rate",
        minInc=0.0,
        unitSymbol=Unit.HERTZ,
        allowedStates={State.UNKNOWN, State.ON})
    async def frameRateTarget(self, value):
        self.set_feature("frameRateTarget", value)

    frameRate = Double(
        displayedName="Actual Frame Rate",
        defaultValue=0.0,
        unitSymbol=Unit.HERTZ,
        accessMode=AccessMode.READONLY)

    latency = Double(
        displayedName="Image Latency",
        defaultValue=0.0,
        unitSymbol=Unit.SECOND,
        accessMode=AccessMode.READONLY)

    maxLatency = Double(
        displayedName="Max Image Latency",
        description="The acquisition will be aborted if the image latency "
                    "exceeds this value, as it most probably means the "
                    "device cannot cope with the frame rate.",
        defaultValue=2.0,
        unitSymbol=Unit.SECOND)

    @Slot(
        displayedName="Acquire",
        allowedStates={State.ON})
    async def acquire(self):
        self.acq_task = background(self.acquire_task)

        self.state = State.ACQUIRING
        self.status = "Acquisition Started"

    async def acquire_task(self):
        self.image_latency.window.clear()

        # Synchronize camera internal clock and Karabo time
        self.synchronize_camera()

        img_size = self.camera.ImageSizeBytes
        buffer_count = 5
        for _ in range(0, buffer_count):
            # Allocate buffers
            buf = np.empty((img_size,), dtype='B')
            self.camera.queue(buf, img_size)

        self.camera.AcquisitionStart()

        image_count = 0
        cycle_mode = self.camera.CycleMode
        frame_count = self.camera.FrameCount
        while True:
            try:
                img = self.camera.wait_buffer(timeout=1000)  # timeout in ms
                image_count += 1
                current_time = time()
                data = img.image  # ndarray
                camera_clock = img.metadata.timestamp  # "ticks" since power up

                # Corrected image time
                image_time = (
                    (camera_clock - self.timestampClock.value) /
                    self.clockFrequency.value + self.reference_time)
                latency, _ = self.image_latency(current_time - image_time)
                ts = Timestamp(image_time)
                self.logger.debug(
                    f"Received new image: shape: {data.shape} "
                    f"camera clock: {camera_clock} latency: {latency}")

                await self.write_channels(
                    data, encoding=EncodingType.GRAY, timestamp=ts)

                # Reuse buffer
                self.camera.queue(img._np_data, img_size)

                self.frame_rate.update()

                if latency > self.maxLatency.value:
                    self.state = State.ERROR
                    self.status = (
                        f"Too high latency: {latency} s. The frame rate is "
                        "possibly too high.")
                    break

            except CancelledError:
                # Task has been canceled
                break

            except CameraException as e:
                if not self.camera.CameraAcquiring:
                    self.state = State.ON
                    break
                elif cycle_mode == "Fixed" and image_count >= frame_count:
                    self.status = "Reached frame count in fixed cycle mode"
                    self.state = State.ON
                    break
                elif e.err_code == ErrorCodes.AT_ERR_TIMEDOUT:
                    # e.g. waiting for external trigger
                    continue
                else:
                    self.status = f"Exception in acquire_task: {e}"
                    self.state = State.ERROR
                    break

            except Exception as e:
                self.status = f"Exception in acquire_task: {e}"
                self.state = State.ERROR
                break

            finally:
                await sleep(0.01)

        if self.camera.CameraAcquiring:
            self.camera.AcquisitionStop()
        self.camera.flush()
        # XXX Do we need to free allocated buffers?

    @Slot(
        displayedName="Stop",
        allowedStates=[State.ACQUIRING])
    async def stop(self):
        self.state = State.STOPPING
        self.camera.AcquisitionStop()

        if self.acq_task:
            self.acq_task.cancel()
            try:
                await self.acq_task
            except (Exception, CancelledError):
                pass
            self.acq_task = None

        self.state = State.ON
        self.status = "Acquisition Stopped"

    @Slot(
        displayedName="Reset",
        description="Acknowledge errors.",
        allowedStates={State.ERROR})
    async def reset(self):
        self.status = ""
        self.state = State.ON

    @UInt32(
        displayedName="ROI Horizontal Binning",
        description="Configures the horizontal binning of the sensor region "
                    "of interest.",
        minInc=1,
        defaultValue=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiHBin(self, value):
        self.set_feature("aoiHBin", value)

    @UInt32(
        displayedName="ROI Width",
        description="Width of the region of interest.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiWidth(self, value):
        self.set_feature("aoiWidth", value)

    @UInt32(
        displayedName="ROI X",
        description="X coordinate of the top-left corner of the region of "
                    "interest. (The leftmost pixel has X = 1.)",
        minInc=1,
        defaultValue=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiLeft(self, value):
        self.set_feature("aoiLeft", value)

    @UInt32(
        displayedName="ROI Vertical Binning",
        description="Configures the vertical binning of the sensor region of "
                    "interest.",
        minInc=1,
        defaultValue=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiVBin(self, value):
        self.set_feature("aoiVBin", value)

    @UInt32(
        displayedName="ROI Height",
        description="Height of the region of interest.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiHeight(self, value):
        self.set_feature("aoiHeight", value)

    @UInt32(
        displayedName="ROI Y",
        description="Y coordinate of top-left corner of the region of "
                    "interest. (The topmost pixel has Y = 1.)",
        minInc=1,
        defaultValue=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiTop(self, value):
        self.set_feature("aoiTop", value)

    @String(
        displayedName="Pixel Readout Rate",
        allowedStates={State.UNKNOWN, State.ON})
    async def pixelReadoutRate(self, value):
        self.set_feature("pixelReadoutRate", value)

    @String(
        displayedName="Pixel Encoding",
        defaultValue="Mono12Packed",
        allowedStates={State.UNKNOWN, State.ON})
    async def pixelEncoding(self, value):
        if value.value not in DATA_TYPE_MAP:
            raise NotImplementedError(f"{value.value} is not yet supported")

        self.set_feature("pixelEncoding", value)

    bitDepth = String(
        displayedName="Bit Depth",
        accessMode=AccessMode.READONLY)

    bytesPerPixel = Double(
        displayedName="Bytes-per-Pixel",
        accessMode=AccessMode.READONLY)

    pixelHeight = Double(
        displayedName="Pixel Height",
        unitSymbol=Unit.METER,
        metricPrefixSymbol=MetricPrefix.MICRO,
        accessMode=AccessMode.READONLY)

    pixelWidth = Double(
        displayedName="Pixel Width",
        unitSymbol=Unit.METER,
        metricPrefixSymbol=MetricPrefix.MICRO,
        accessMode=AccessMode.READONLY)

    @String(
        displayedName="Trigger Mode",
        defaultValue="Internal",
        allowedStates={State.UNKNOWN, State.ON})
    async def triggerMode(self, value):
        self.set_feature("triggerMode", value)

    @Double(
        displayedName="Ext. Trigger Delay",
        unitSymbol=Unit.SECOND,
        allowedStates={State.UNKNOWN, State.ON})
    async def externalTriggerDelay(self, value):
        self.set_feature("externalTriggerDelay", value)

    @String(
        displayedName="Electronic Shutter Mode",
        defaultValue="Rolling",
        allowedStates={State.UNKNOWN, State.ON})
    async def electronicShutteringMode(self, value):
        self.set_feature("electronicShutteringMode", value)

    @String(
        displayedName="Fan Speed",
        allowedStates={State.UNKNOWN, State.ON})
    async def fanSpeed(self, value):
        self.set_feature("fanSpeed", value)

    @Bool(
        displayedName="Sensor Cooling",
        allowedStates={State.UNKNOWN, State.ON})
    async def sensorCooling(self, value):
        self.set_feature("sensorCooling", value)

    @String(
        displayedName="Temperature Control",
        unitSymbol=Unit.DEGREE_CELSIUS,
        allowedStates={State.UNKNOWN, State.ON})
    async def temperatureControl(self, value):
        self.set_feature("temperatureControl", value)
        if self.camera:
            self.targetSensorTemperature = self.camera.TargetSensorTemperature

    targetSensorTemperature = Double(
        displayedName="Target Sensor Temperature",
        unitSymbol=Unit.DEGREE_CELSIUS,
        accessMode=AccessMode.READONLY)

    sensorTemperature = Double(
        displayedName="Sensor Temperature",
        unitSymbol=Unit.DEGREE_CELSIUS,
        accessMode=AccessMode.READONLY)

    temperatureStatus = String(
        displayedName="Temperature Status",
        accessMode=AccessMode.READONLY)

    def __init__(self, configuration):
        super().__init__(configuration)
        self.frame_rate = RateCalculator(refresh_interval=1.0)
        self.image_latency = MovingAverage(window_size=10)
        self.frame_rate_task = background(self.refresh_frame_rate())
        self.acq_task = None
        self.connect_or_poll_task = None

    def connect(self, sdk3):
        """Try to connect (for the first time) to the camera"""
        if self.camera:
            raise RuntimeError(
                "This function can only be called to connect to the camera "
                "the first time.")

        self.logger.debug(f"connect: Found {sdk3.DeviceCount} cameras")
        for idx in range(sdk3.DeviceCount):
            try:
                cam = sdk3.GetCamera(idx)
                self.logger.debug(f"connect: Found camera {cam.SerialNumber}")
                if cam.SerialNumber == self.serialNumber:
                    return cam
            except Exception as e:
                # Simulated cameras will raise AT_ERR_NOTIMPLEMENTED
                # Cameras already in use will throw AT_ERR_DEVICEINUSE
                self.logger.debug(f"connect: idx={idx} e={e}")
                continue

    async def reconnect(self):
        """Try to reconnect to the camera after a connection loss"""
        reconnect_fail_msg = (
            f"Could not reconnect to {self.serialNumber}. "
            f"Trying again in {RECONNECT_TIME} s.")
        connected_msg = f"Reconnected to {self.serialNumber}"

        if not self.camera:
            raise RuntimeError(
                "This function can only be called to re-connect to the camera "
                "after the connection has been lost.")

        if self.camera.handle:
            self.camera.close()  # Closes the camera instance

        while True:
            try:
                self.camera.open()  # Re-opens the camera instance
                break
            except Exception:
                # The camera is not available yet
                if self.status != reconnect_fail_msg:
                    self.status = reconnect_fail_msg
                    self.logger.error(reconnect_fail_msg)
                await sleep(RECONNECT_TIME)

        self.status = connected_msg
        self.logger.info(connected_msg)
        self.state = State.INIT

        await self.initialize_camera()

    async def onInitialization(self):
        """This method will be called when the device starts."""
        no_camera_msg = (
            f"No camera found with SN={self.serialNumber}. "
            "It could be OFF or controlled by another application. "
            f"Trying to reconnect in {RECONNECT_TIME} s.")
        connected_msg = f"Connected to {self.serialNumber}"

        sdk3 = AndorSDK3()
        while True:
            cam = self.connect(sdk3)
            if cam:
                break

            if self.status != no_camera_msg:
                self.status = no_camera_msg
                self.logger.error(no_camera_msg)
            await sleep(RECONNECT_TIME)
            # Reinitialize the library in order to re-discover cameras
            # NB This will block forever if called again after a camera
            # has been already discovered!
            sdk3.Reinitialise()

        self.camera = cam
        self.status = connected_msg
        self.logger.info(connected_msg)
        self.state = State.INIT

        await self.initialize_camera()

    async def initialize_camera(self):
        """This function does the initial setup of the camera"""
        schema_hash = self.getDeviceSchema().hash

        for key, feature in FEATURE_MAP.items():
            access_mode = schema_hash.getAttribute(key, "accessMode")
            if access_mode not in (
                    AccessMode.INITONLY.value,
                    AccessMode.RECONFIGURABLE.value):
                # The parameter is read-only
                continue

            value = getattr(self, key, None)
            if isSet(value):
                # Set values to the camera
                try:
                    self.logger.debug(
                        f"Setting {feature} = {value.value}")
                    setattr(self.camera, feature, value.value)
                except Exception as e:
                    if self.state != State.ERROR:
                        self.state = State.ERROR
                    self.status = f"Could not set {feature} on camera"
                    self.logger.error(
                        f"Could not set {feature} on camera: {e}")
            else:
                # Read values from the camera
                value = getattr(self.camera, feature)
                self.logger.debug(f"{feature}: {value}")
                setattr(self, key, value)

        self.camera.MetadataEnable = True

        await self.update_output_schema_andor()

        await self.update_schema_andor()

        self.cameraModel = self.camera.CameraModel
        self.interfaceType = self.camera.InterfaceType
        self.firmwareVersion = self.camera.FirmwareVersion
        self.clockFrequency = self.camera.TimestampClockFrequency
        self.bitDepth = self.camera.BitDepth
        self.bytesPerPixel = self.camera.BytesPerPixel
        self.pixelHeight = self.camera.PixelHeight
        self.pixelWidth = self.camera.PixelWidth

        # Start polling
        self.connect_or_poll_task = background(self.poll_camera())

        if self.state != State.ERROR:
            self.state = State.ON

    async def update_output_schema_andor(self):
        if not self.camera:
            return

        heigth = self.camera.AOIHeight
        width = self.camera.AOIWidth
        shape = (heigth, width)
        pixel_encoding = self.camera.PixelEncoding
        dtype = DATA_TYPE_MAP[pixel_encoding]

        self.logger.debug(
            f"Update output schema: shape={shape} dtype={dtype}")
        await self.update_output_schema(shape, EncodingType.GRAY, dtype)

    def update_options(self, key, config):
        """
        Updates the options for the device parameter specified by the key.
        This function will also update the 'config' dict in case the current
        value of the property is none of the available options.

        In order to inject the new options to the schema,
        'publishInjectedParameters' must be called.

        :param key: The key of the property for which we want to update options
        :param config: The configuration dict, which will be updated with a new
        value for 'key' in case the current value on the device is none of the
        available options.
        """
        if not self.camera:
            return

        # XXX Possibly skip read-only parameters

        feature = FEATURE_MAP[key]
        feature_type = getattr(self.camera, f"type_{feature}")
        if feature_type == "enumerated_string":
            options = getattr(self.camera, f"options_{feature}")
            self.logger.debug(f"Setting new options for {key}: {options}")
            # XXX Also change defaultValue if not in options
            setattr(self.__class__, key, Overwrite(options=options))
            value = getattr(self, key)
            if isSet(value) and value.value not in options:
                config[key] = options[0]

        elif feature_type in ("float", "int"):
            min_value = getattr(self.camera, f"min_{feature}")
            max_value = getattr(self.camera, f"max_{feature}")
            self.logger.debug(
                f"Setting new range for {key}: {min_value} - {max_value}")
            # Also change defaultVale if not within range
            setattr(self.__class__, key, Overwrite(
                minInc=min_value, maxInc=max_value))
            value = getattr(self, key)
            if isSet(value):
                if value.value < min_value:
                    config[key] = min_value
                elif value.value > max_value:
                    config[key] = max_value

    async def update_schema_andor(self):
        """Updates the device schema with the allowed options for the
        camera features"""
        new_conf = {}
        for key in FEATURE_MAP:
            self.update_options(key, new_conf)

        await self.publishInjectedParameters(**new_conf)

    def synchronize_camera(self):
        """Synchronizes the camera internal clock and the Karabo time"""
        self.timestampClock = self.camera.TimestampClock
        self.reference_time = time()

    async def poll_camera(self):
        error_count = 0

        while True:
            try:
                # Synchronize camera internal clock and Karabo time
                self.synchronize_camera()

                self.sensorTemperature = self.camera.SensorTemperature
                self.temperatureStatus = self.camera.TemperatureStatus

                error_count = 0

            except CameraException as e:
                error_count += 1
                if error_count < 10:
                    self.logger.error(f"Exception in poll_camera: {e}")
                else:
                    # Assume the connection is lost after 10 consecutive
                    # communication errors
                    await self.disconnection_handler()
                    return

            await sleep(5)

    async def disconnection_handler(self):
        status = "Lost connection to the camera"
        self.logger.error(status)
        self.status = status
        await sleep(1)

        if self.acq_task:
            self.acq_task.cancel()
            self.acq_task = None

        if self.connect_or_poll_task:
            self.connect_or_poll_task.cancel()

        self.state = State.UNKNOWN

        self.connect_or_poll_task = background(self.reconnect())

    async def refresh_frame_rate(self):
        while True:
            fps = self.frame_rate.refresh()
            if self.state == State.ACQUIRING:
                if fps:
                    self.frameRate = fps
                self.latency = self.image_latency.avg
            else:
                if self.frameRate:
                    self.frameRate = 0.0
                if self.latency:
                    self.latency = 0.0

            await sleep(1)

    async def onDestruction(self):
        if self.connect_or_poll_task:
            self.connect_or_poll_task.cancel()
        self.frame_rate_task.cancel()
        if self.acq_task:
            self.acq_task.cancel()
        if self.camera:
            if self.camera.CameraAcquiring:
                self.camera.AcquisitionStop()
            self.camera.flush()

    async def slotReconfigure(self, conf, message):
        self.logger.debug(f"slotReconfigure: conf = {conf}")
        await super().slotReconfigure(conf, message)

        # Create a list of parameters for which the value or options have
        # potentially changed
        keys = []
        for k in conf:
            if k in RELATED_PROPERTIES:
                keys.extend(RELATED_PROPERTIES[k])

        # Update options
        new_conf = {}
        for key in keys:
            self.update_options(key, new_conf)
        await self.publishInjectedParameters(**new_conf)

        # Update values
        for key in keys:
            self.sync_feature(key)

        if SCHEMA_CHANGING_PROPERTIES.intersection(conf):
            # Output channel schema needs update
            await self.update_output_schema_andor()

    slotReconfigure = coslot(slotReconfigure, passMessage=True)
