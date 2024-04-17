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

from time import time

from pyAndorSDK3 import AndorSDK3, CameraException, ErrorCodes

from imageSourcePy.CameraImageSourceMdl import CameraImageSource
from karabo.middlelayer import (
    AccessMode, Assignment, Double, EncodingType, Slot, State, String,
    Timestamp, UInt8, UInt16, UInt32, UInt64, Unit, background, isSet, sleep)

from ._version import version as deviceVersion

DATA_TYPE_MAP = {
    # Pixel Encoding: Karabo Type
    "Mono8": UInt8,
    "Mono12": UInt16,
    # "Mono12Packed": Uint16,  # XXX not implemented yet
    "Mono16": UInt16,
    "Mono32": UInt32}

FEATURE_MAP = {
    # Karabo Key: Feature Name
    "cycleMode": "CycleMode",
    # "frameCount": "FrameCount",  # XXX not writeable?
    "exposureTime": "ExposureTime",
    "frameRateTarget": "FrameRate",
    "aoiHBin": "AOIHBin",
    "aoiWitdh": "AOIWidth",
    "aoiLeft": "AOILeft",
    "aoiVBin": "AOIVBin",
    "aoiHeight": "AOIHeight",
    "aoiTop": "AOITop",
    "pixelEncoding": "PixelEncoding",
    "bitDepth": "BitDepth",
    "triggerMode": "TriggerMode"}


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

    clockFrequency = UInt32(
        displayedName="Clock Frequency",
        description="The frequency of the camera internal clock.",
        unitSymbol=Unit.HERTZ,
        accessMode=AccessMode.READONLY)

    timestampClock = UInt64(
        displayedName="Camera Clock",
        description="The current value of the camera internal clock.",
        accessMode=AccessMode.READONLY)

    sensorTemperature = Double(
        displayedName="Sensor Temperature",
        unitSymbol=Unit.DEGREE_CELSIUS,
        accessMode=AccessMode.READONLY)

    @String(
        displayedName="Cycle Mode",
        description="Continuous: keep acquiring until acquisition is stopped. "
                    "Fixed: the camera acquires 'Frame Count' images and "
                    "stops automatically.",
        options={"Continuous", "Fixed"},
        # XXX read and inject options with self.camera.options_EnumFeatureName
        defaultValue="Continuous",
        allowedStates={State.UNKNOWN, State.ON})
    async def cycleMode(self, value):
        self.set_feature("cycleMode", value)

    @UInt32(
        displayedName="Frame Count",
        description="Number of frames to acquire when 'Fixed' cycle mode. "
                    "Ignored in 'Continuous' mode.",
        minInc=1,
        defaultValue=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def frameCount(self, value):
        self.set_feature("frameCount", value)

    @Double(
        displayedName="Exposure Time",
        minInc=0.0,
        # XXX read and inject min/max with self.camera.min_FeatureName and
        #     self.camera_max_FeatureName
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

    @Slot(
        displayedName="Acquire",
        allowedStates={State.ON})
    async def acquire(self):

        self.acq_task = background(self.acquire_task)

        self.state = State.ACQUIRING
        self.status = "Acquisition Started"

    async def acquire_task(self):
        while True:
            try:
                img = self.camera.acquire(timeout=1000)  # timeout in ms
                current_time = time()
                # XXX needs:
                # cd $KARABO/extern/lib
                # ln -fs libatutility.so.3.15.30092.2 libatutility.so.3
                data = img.image  # ndarray
                camera_clock = img.metadata.timestamp  # "ticks" since power up

                # Corrected image time
                image_time = (
                    (camera_clock - self.timestampClock.value) /
                    self.clockFrequency.value + self.reference_time)
                latency = current_time - image_time
                ts = Timestamp(image_time)
                self.logger.debug(
                    f"Received new image: shape: {data.shape} "
                    f"camera clock: {camera_clock} latency: {latency}")

                await self.write_channels(
                    data, encoding=EncodingType.GRAY, timestamp=ts)

            except CameraException as e:
                if not self.camera.CameraAcquiring:
                    # e.g. reached frame count in fixed cycle mode
                    self.state = State.ON
                    break
                elif e.err_code == ErrorCodes.AT_ERR_TIMEDOUT:
                    # e.g. waiting for external trigger
                    continue
                else:
                    self.status(f"Exception in acquire_task: {e}")
                    self.state = State.ERROR
                    break

            except Exception as e:
                self.status(f"Exception in acquire_task: {e}")
                self.state = State.ERROR
                break

            finally:
                await sleep(0.01)

        self.camera.flush()

    @Slot(
        displayedName="Stop",
        allowedStates=[State.ACQUIRING])
    async def stop(self):
        if self.acq_task:
            self.acq_task.cancel()
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
            await self.update_output_schema_andor()

    @UInt32(
        displayedName="ROI Width",
        description="Width of the region of interest.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiWitdh(self, value):
        self.set_feature("aoiWitdh", value)
        if self.camera:
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
            await self.update_output_schema_andor()

    @UInt32(
        displayedName="ROI Height",
        description="Height of the region of interest.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def aoiHeight(self, value):
        self.set_feature("aoiHeight", value)
        if self.camera:
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
        displayedName="Pixel Encoding",
        # XXX read and inject options with self.camera.options_EnumFeatureName
        options=list(DATA_TYPE_MAP),
        defaultValue="Mono16",
        allowedStates={State.UNKNOWN, State.ON})
    async def pixelEncoding(self, value):
        self.set_feature("pixelEncoding", value)
        if self.camera:
            self.bitDepth = self.camera.BitDepth
            await self.update_output_schema_andor()

    bitDepth = String(
        displayedName="Bit Depth",
        accessMode=AccessMode.READONLY)

    @String(
        displayedName="Trigger Mode",
        defaultValue="Internal",
        options={"Internal", "External"},
        allowedStates={State.UNKNOWN, State.ON})
    async def triggerMode(self, value):
        self.set_feature("triggerMode", value)

    # XXX more properties, e.g.
    # FanSpeed: Enumerated
    # PixelReadoutRate: Enumerated
    # SensorCooling: Bool

    def __init__(self, configuration):
        super().__init__(configuration)
        self.acq_task = None
        self.poll_task = background(self.poll_camera())

    async def onInitialization(self):
        """ This method will be called when the device starts.

            Define your actions to be executed after instantiation.
        """
        self.state = State.INIT

        sdk3 = AndorSDK3()
        for idx in range(sdk3.DeviceCount):
            try:
                cam = sdk3.GetCamera(idx)
                if cam.SerialNumber == self.serialNumber:
                    self.camera = cam
                    break
            except Exception:
                # Simulated cameras will raise AT_ERR_NOTIMPLEMENTED
                # Cameras already in use will throw AT_ERR_DEVICEINUSE
                continue

        if self.camera:
            self.status = f"Connected to {self.serialNumber}"
        else:
            self.status = f"No camera found with SN {self.serialNumber}"
            self.state = State.UNKNOWN
            return

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
        self.clockFrequency = self.camera.TimestampClockFrequency

        await self.update_output_schema_andor()

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

    async def poll_camera(self):
        while True:
            if self.camera:
                self.timestampClock = self.camera.TimestampClock
                self.reference_time = time()

                self.sensorTemperature = self.camera.SensorTemperature
                await sleep(5)
            else:
                await sleep(1)

    async def onDestruction(self):
        if self.poll_task:
            self.poll_task.cancel()
        if self.acq_task:
            self.acq_task.cancel()
        if self.camera:
            self.camera.AcquisitionStop()
            self.camera.flush()
