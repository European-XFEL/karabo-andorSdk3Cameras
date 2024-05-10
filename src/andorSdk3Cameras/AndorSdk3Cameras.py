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
    Unit, background, isSet, sleep)
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
    "aoiWitdh": "AOIWidth",
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

# Sleep time between two connect attempts
SLEEP_TIME = 5


class AndorSdk3Cameras(CameraImageSource):
    __version__ = deviceVersion

    camera = None

    def set_feature(self, key, value):
        if self.camera and isSet(value):
            self.logger.debug(f"Setting {FEATURE_MAP[key]} = {value.value}")
            setattr(self.camera, FEATURE_MAP[key], value.value)
        setattr(self, key, value)

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
            # Also apply 'frameCount'
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
        img_size = self.camera.ImageSizeBytes
        buffer_count = 5
        for _ in range(0, buffer_count):
            # Allocate buffers
            buf = np.empty((img_size,), dtype='B')
            self.camera.queue(buf, img_size)

        self.camera.AcquisitionStart()

        while True:
            try:
                img = self.camera.wait_buffer(timeout=1000)  # timeout in ms
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
                    # e.g. reached frame count in fixed cycle mode
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
        if self.camera:
            # XXX also update_schema_andor() might be required
            await self.update_output_schema_andor()

    @UInt32(
        displayedName="ROI Width",
        description="Width of the region of interest.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiWitdh(self, value):
        self.set_feature("aoiWitdh", value)
        if self.camera:
            # XXX also update_schema_andor() might be required
            await self.update_output_schema_andor()

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
        if self.camera:
            # XXX also update_schema_andor() might be required
            await self.update_output_schema_andor()

    @UInt32(
        displayedName="ROI Height",
        description="Height of the region of interest.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiHeight(self, value):
        self.set_feature("aoiHeight", value)
        if self.camera:
            # XXX also update_schema_andor() might be required
            await self.update_output_schema_andor()

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
        if self.camera:
            self.bitDepth = self.camera.BitDepth
            self.bytesPerPixel = self.camera.BytesPerPixel
            await self.update_output_schema_andor()

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
        self.poll_task = None

    def connect(self, sdk3):
        """ This method will be called when the device starts.

            Define your actions to be executed after instantiation.
        """
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

    async def onInitialization(self):
        """ This method will be called when the device starts.

            Define your actions to be executed after instantiation.
        """
        no_camera_msg = (
            f"No camera found with SN={self.serialNumber}. "
            "It could be OFF or controlled by another application. "
            f"Trying to reconnect in {SLEEP_TIME} s.")
        connected_msg = f"Connected to {self.serialNumber}"

        sdk3 = AndorSDK3()
        while True:
            cam = self.connect(sdk3)
            if cam:
                break

            if self.status != no_camera_msg:
                self.status = no_camera_msg
                self.logger.error(no_camera_msg)
            await sleep(SLEEP_TIME)
            # XXX Reinitialize() only works properly if the camera is connected
            # after the device is instantiated.
            # It does not if the camera is disconnected and reconnected.
            # In this case I have to even restart the MDL server to be able to
            # connect again to the camera.
            sdk3.Reinitialise()

        self.camera = cam
        self.status = connected_msg
        self.logger.info(connected_msg)
        self.state = State.INIT

        for key, feature in FEATURE_MAP.items():
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

        self.cameraModel = self.camera.CameraModel
        self.interfaceType = self.camera.InterfaceType
        self.firmwareVersion = self.camera.FirmwareVersion
        self.clockFrequency = self.camera.TimestampClockFrequency
        self.pixelHeight = self.camera.PixelHeight
        self.pixelWidth = self.camera.PixelWidth

        await self.update_output_schema_andor()

        await self.update_schema_andor()

        # Start polling
        self.poll_task = background(self.poll_camera())

        if self.state != State.ERROR:
            self.state = State.ON

    async def update_output_schema_andor(self):
        heigth = self.camera.AOIHeight
        width = self.camera.AOIWidth
        shape = (heigth, width)
        pixel_encoding = self.camera.PixelEncoding
        dtype = DATA_TYPE_MAP[pixel_encoding]

        self.logger.debug(
            f"Update output schema: shape={shape} dtype={dtype}")
        await self.update_output_schema(shape, EncodingType.GRAY, dtype)

    async def update_schema_andor(self):
        new_dict = {}
        for key, feature in FEATURE_MAP.items():
            feature_type = getattr(self.camera, f"type_{feature}")
            if feature_type == "enumerated_string":
                options = getattr(self.camera, f"options_{feature}")
                # XXX Also change defaultValue if not in options
                setattr(self.__class__, key, Overwrite(options=options))
                value = getattr(self, key)
                if isSet(value) and value.value not in options:
                    new_dict[key] = options[0]

            elif feature_type in ("float", "int"):
                min_value = getattr(self.camera, f"min_{feature}")
                max_value = getattr(self.camera, f"max_{feature}")
                # Also change defaultVale if not within range
                setattr(self.__class__, key, Overwrite(
                    minInc=min_value, maxInc=max_value))
                value = getattr(self, key)
                if isSet(value):
                    if value.value < min_value:
                        new_dict[key] = min_value
                    elif value.value > max_value:
                        new_dict[key] = max_value

        await self.publishInjectedParameters(**new_dict)

    async def poll_camera(self):
        error_count = 0

        while True:
            try:
                self.timestampClock = self.camera.TimestampClock
                self.reference_time = time()

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
                    self.status = "Lost connection to the camera"
                    self.state = State.UNKNOWN
                    self.poll_task = None
                    return

            await sleep(5)

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
        if self.poll_task:
            self.poll_task.cancel()
        self.frame_rate_task.cancel()
        if self.acq_task:
            self.acq_task.cancel()
        if self.camera:
            if self.camera.CameraAcquiring:
                self.camera.AcquisitionStop()
            self.camera.flush()
