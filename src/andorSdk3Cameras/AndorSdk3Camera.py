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

from asyncio import CancelledError, wait_for
from copy import copy
from time import time

import numpy as np
from pyAndorSDK3 import AndorSDK3, CameraException, ErrorCodes

from imageSourcePy.CameraImageSourceMdl import CameraImageSource
from karabo.middlelayer import (
    AccessMode, Assignment, Bool, Configurable, Double, Encoding, Hash,
    KaraboValue, MetricPrefix, Node, Overwrite, Slot, State, String, Timestamp,
    UInt8, UInt16, UInt32, UInt64, Unit, background, coslot, get_timestamp,
    getProperties, has_changes, isSet, sleep)
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
    "cameraModel": "CameraModel",
    "interfaceType": "InterfaceType",
    "firmwareVersion": "FirmwareVersion",
    "clockFrequency": "TimestampClockFrequency",
    "timestampClock": "TimestampClock",
    "bitDepth": "BitDepth",
    "bytesPerPixel": "BytesPerPixel",
    "pixelHeight": "PixelHeight",
    "pixelWidth": "PixelWidth",
    "cycleMode": "CycleMode",
    # FrameCount can only be set on the camera when CycleMode==Fixed
    "frameCount": "FrameCount",
    "exposureTime": "ExposureTime",
    "aoiHBin": "AOIHBin",
    "aoiWidth": "AOIWidth",
    "aoiLeft": "AOILeft",
    "aoiVBin": "AOIVBin",
    "aoiHeight": "AOIHeight",
    "aoiTop": "AOITop",
    "pixelReadoutRate": "PixelReadoutRate",
    "simplePreAmpGainControl": "SimplePreAmpGainControl",
    "pixelEncoding": "PixelEncoding",
    "bitDepth": "BitDepth",
    "bytesPerPixel": "BytesPerPixel",
    "triggerMode": "TriggerMode",
    # FrameRate can only be set on the camera when TriggerMode==Internal
    "frameRateTarget": "FrameRate",
    "externalTriggerDelay": "ExternalTriggerDelay",
    "rollingShutterGlobalClear": "RollingShutterGlobalClear",
    "electronicShutteringMode": "ElectronicShutteringMode",
    "baseline": "Baseline",
    "staticBlemishCorrection": "StaticBlemishCorrection",
    "spuriousNoiseFilter": "SpuriousNoiseFilter",
    "fanSpeed": "FanSpeed",
    "sensorCooling": "SensorCooling",
    "sensorTemperature": "SensorTemperature",
    "temperatureStatus": "TemperatureStatus",
    "temperatureControl": "TemperatureControl"}

KEY_MAP = {
    # Feature Name: Karabo Key
    feature: key for key, feature in FEATURE_MAP.items()}

# Updating some camera features will affect e.g. the image shape or data type,
# thus a schema update for the output channel will be needed.
SCHEMA_CHANGING_PROPERTIES = {
    "aoiHBin", "aoiWidth", "aoiVBin", "aoiHeight", "rotation",
    "simplePreAmpGainControl", "pixelEncoding"}

# Sleep time between two connect attempts
RECONNECT_TIME = 5


async def get_timeserver_time(timeserver_id):
    """Get current tid, timestamp and period from timeserver"""
    props = await getProperties(timeserver_id, ["id", "periodActual"])

    tid = props["id"]  # reference tid from timeserver
    timestamp = (  # reference timestamp from timeserver
        props.getAttributes("id")["sec"]
        + props.getAttributes("id")["frac"] / 10**18)
    period = props["periodActual"] / 1000  # ms -> s

    return tid, timestamp, period


def flip_and_rotate(data, flip_x, flip_y, rotation):
    if flip_x or flip_y or rotation != 0:
        if flip_x:
            data = np.flipud(data)
        if flip_y:
            data = np.fliplr(data)
        if rotation != 0:
            n_rotations = rotation // 90 % 4
            data = np.rot90(data, n_rotations)

    return np.ascontiguousarray(data)


class Flip(Configurable):
    x = Bool(
        displayedName="Horizontal Flip",
        description="Enable horizontal flip. This is applied before the "
                    "image rotation.",
        accessMode=AccessMode.RECONFIGURABLE,
        assignment=Assignment.OPTIONAL,
        defaultValue=False,
        allowedStates={State.UNKNOWN, State.ON})

    y = Bool(
        displayedName="Vertical Flip",
        description="Enable vertical flip. This is applied before the "
                    "image rotation.",
        accessMode=AccessMode.RECONFIGURABLE,
        assignment=Assignment.OPTIONAL,
        defaultValue=False,
        allowedStates={State.UNKNOWN, State.ON})


class AndorSdk3Camera(CameraImageSource):
    __version__ = deviceVersion

    sdk3 = AndorSDK3()

    def register_callback(self, feature):
        @self.sdk3.event_callback
        def inner(handle, feature):
            key = KEY_MAP[feature]
            new_value = getattr(self.camera, feature)

            # Update options
            self.update_options(key)

            # Update value on the device
            old_value = getattr(self, key)
            if has_changes(old_value, new_value):
                setattr(self, key, new_value)
                self.logger.debug(
                    f"Feature update: feature={feature} value={new_value}")

        self.camera.register_feature_callback(feature, inner)

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
        if not isSet(value):
            return

        if not self.camera:
            # Will be applied when the connection is established
            setattr(self, key, value)
            return

        feature = FEATURE_MAP[key]
        old_value = getattr(self.camera, feature)
        new_value = value.value if isinstance(value, KaraboValue) else value
        try:
            if has_changes(old_value, new_value):
                self.logger.debug(f"Setting {feature} to {new_value}")
                setattr(self.camera, feature, new_value)
        except CameraException as e:
            # Depending on other settings the feature might not
            # be writable
            msg = (
                f"Could not set {key} on camera: {e}. This could depend on "
                "other camera settings.")
            self.status = msg
            self.logger.warning(msg)
            raise
        finally:
            # Even in case of success the value on tha camera could
            # slightly differ from the target one, as not all float
            # value are allowed.
            new_value = getattr(self.camera, feature)
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

    @UInt32(
        displayedName="Frame Count",
        description="Number of frames to acquire when in 'Fixed' cycle mode. "
                    "This parameter can only be set with continuous cycle "
                    "mode.",
        minInc=1,
        allowedStates={State.UNKNOWN, State.ON})
    async def frameCount(self, value):
        self.set_feature("frameCount", value)

    @Double(
        displayedName="Exposure Time",
        minInc=0.0,
        unitSymbol=Unit.SECOND,
        allowedStates={State.UNKNOWN, State.ON})
    async def exposureTime(self, value):
        self.set_feature("exposureTime", value)

    @Double(
        displayedName="Target Frame Rate",
        description="The target frame rate. This parameter can only be set "
                    "in internal trigger mode.",
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

        try:
            # Synchronize camera internal clock and Karabo time
            self.timestampClock = self.camera.TimestampClock

            img_size = self.camera.ImageSizeBytes
            buffer_count = 5
            for _ in range(0, buffer_count):
                # Allocate buffers
                buf = np.empty((img_size,), dtype='B')
                self.camera.queue(buf, img_size)

            self.camera.AcquisitionStart()

        except CameraException:
            # The connection with the camera has been lost
            await self.disconnection_handler()
            return

        image_count = 0
        cycle_mode = self.camera.CycleMode
        frame_count = self.camera.FrameCount
        while True:
            try:
                img = self.camera.wait_buffer(timeout=1000)  # timeout in ms
                image_count += 1

            except CancelledError:
                # Task has been canceled
                break

            except CameraException as e:
                try:
                    # In case the camera went offline during acquisition,
                    # accessing self.camera.CameraAcquiring will throw
                    camera_acquiring = self.camera.CameraAcquiring
                except CameraException:
                    await self.disconnection_handler()
                    return

                if not camera_acquiring:
                    self.state = State.ON
                    break
                elif cycle_mode == "Fixed" and image_count >= frame_count:
                    self.status = "Reached frame count in fixed cycle mode"
                    self.state = State.ON
                    break
                elif e.err_code == ErrorCodes.AT_ERR_TIMEDOUT:
                    # e.g. waiting for external/software trigger
                    continue
                else:
                    self.status = f"CameraException in acquire_task: {e}"
                    self.state = State.ERROR
                    break

            try:
                current_timestamp = get_timestamp()
                current_tid = current_timestamp.tid
                current_time = current_timestamp.toTimestamp()
                current_time_unix = time()

                data = img.image  # ndarray
                # Image time as "ticks" since camera power-up.
                # Convert it to "float" to avoid overflows from int operations
                image_time_ticks = float(img.metadata.timestamp)

                # Camera clock (ticks): cache current value as it could be
                # updated in the background by the polling task
                timestamp_clock = copy(self.timestampClock)
                timestamp_clock_ts = timestamp_clock.timestamp.toTimestamp()

                # Corrected image time
                image_time = (
                    (image_time_ticks - timestamp_clock.value) /
                    self.clockFrequency.value + timestamp_clock_ts)
                if current_time < image_time:
                    self.logger.warning(
                        "This should not happen! latency < 0.0!!! "
                        f"Current time: {current_time} s; "
                        f"Current time (UNIX): {current_time_unix} s; "
                        f"Image time: {image_time} s; "
                        f"Image time: {image_time_ticks} ticks; "
                        f"Cam ref. time: {timestamp_clock.value} ticks; "
                        f"Clock freq. {self.clockFrequency.value} Hz; "
                        f"Ref. time: {timestamp_clock_ts} s; "
                        f"TS tid: {self.ts_tid}; "
                        f"TS ts: {self.ts_timestamp} s; "
                        f"TS period: {self.ts_period} s.")
                    continue  # drop image
                latency, _ = self.image_latency(current_time - image_time)

                ts = Timestamp(image_time)
                if None in (self.ts_tid, self.ts_timestamp, self.ts_period):
                    # No reference info from timeserver. Use actual tid
                    ts.tid = current_tid
                else:
                    delta_tid = (
                        image_time - self.ts_timestamp) / self.ts_period
                    ts.tid = self.ts_tid + delta_tid

                self.logger.debug(
                    f"Received new image: shape: {data.shape} "
                    f"current time: {current_time} current tid: {current_tid} "
                    f"camera clock: {image_time_ticks} latency: {latency} "
                    f"corrected tid: {ts.tid}")

                # Flip and rotate image
                data = flip_and_rotate(
                    data, self.flip.x, self.flip.y, self.rotation.value)
                await self.write_channels(
                    data, encoding=Encoding.GRAY, timestamp=ts)

                self.frame_rate.update()

                if latency > self.maxLatency.value:
                    self.state = State.ERROR
                    msg = (
                        f"Too high latency: {latency} s. The frame rate is "
                        "possibly too high.")
                    self.status = msg
                    self.logger.error(msg)
                    break

            except CancelledError:
                # Task has been canceled
                break

            except Exception as e:
                msg = f"{e.__class__.__name__} in acquire_task: {e}."
                self.status = msg
                self.state = State.ERROR
                break

            # Reuse buffer
            self.camera.queue(img._np_data, img_size)

            await sleep(0.01)

        if self.camera and self.camera.handle:
            if self.camera.CameraAcquiring:
                self.camera.AcquisitionStop()
            self.camera.flush()  # cleans any existing queued buffers

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
            except CancelledError:
                pass
            self.acq_task = None

        self.camera.flush()  # cleans any existing queued buffers

        self.state = State.ON
        self.status = "Acquisition Stopped"

    @Slot(
        displayedName="Trigger",
        description="Send software trigger to the camera.",
        allowedStates=[State.ACQUIRING])
    async def trigger(self):
        if self.camera.TriggerMode == "Software":
            self.camera.SoftwareTrigger()

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

    flip = Node(
        Flip,
        displayedName="Image Flip",
        description="Enables mirroring of the image.")

    rotation = UInt16(
        displayedName="Image Rotation",
        description="The image rotation. The angle must be a multiple of "
                    "90°. The rotation is done after the image flip.",
        accessMode=AccessMode.RECONFIGURABLE,
        assignment=Assignment.OPTIONAL,
        unitSymbol=Unit.DEGREE,
        options=[0, 90, 180, 270],
        defaultValue=0,
        allowedStates={State.UNKNOWN, State.ON})

    @String(
        displayedName="Pixel Readout Rate",
        allowedStates={State.UNKNOWN, State.ON})
    async def pixelReadoutRate(self, value):
        self.set_feature("pixelReadoutRate", value)

    @String(
        displayedName="Simple Pre-Amp Gain Control",
        allowedStates={State.UNKNOWN, State.ON})
    async def simplePreAmpGainControl(self, value):
        self.set_feature("simplePreAmpGainControl", value)

    @String(
        displayedName="Pixel Encoding",
        defaultValue="Mono16",
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

    @Bool(
        displayedName="Rolling Shutter Global Clear",
        allowedStates={State.UNKNOWN, State.ON})
    async def rollingShutterGlobalClear(self, value):
        self.set_feature("rollingShutterGlobalClear", value)

    @String(
        displayedName="Electronic Shutter Mode",
        defaultValue="Rolling",
        allowedStates={State.UNKNOWN, State.ON})
    async def electronicShutteringMode(self, value):
        self.set_feature("electronicShutteringMode", value)

    @UInt16(
        displayedName="Baseline",
        allowedStates={State.UNKNOWN, State.ON})
    async def baseline(self, value):
        self.set_feature("baseline", value)

    @Bool(
        displayedName="Static Blemish Correction",
        allowedStates={State.UNKNOWN, State.ON})
    async def staticBlemishCorrection(self, value):
        self.set_feature("staticBlemishCorrection", value)

    @Bool(
        displayedName="Spurious Noise Filter",
        allowedStates={State.UNKNOWN, State.ON})
    async def spuriousNoiseFilter(self, value):
        self.set_feature("spuriousNoiseFilter", value)

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

        self.camera = None

        self.ts_tid = None
        self.ts_timestamp = None
        self.ts_period = None
        self.frame_rate = RateCalculator(refresh_interval=1.0)
        self.image_latency = MovingAverage(window_size=10)
        self.frame_rate_task = None
        self.acq_task = None
        self.connect_or_poll_task = None
        self.schema_hash = None
        self.must_update_schema = False

    def connect(self):
        """Try to connect (for the first time) to the camera"""
        if self.camera:
            raise RuntimeError(
                "This function can only be called to connect to the camera "
                "the first time.")

        self.logger.debug(f"connect: Found {self.sdk3.DeviceCount} cameras")
        for idx in range(self.sdk3.DeviceCount):
            try:
                cam = self.sdk3.GetCamera(idx)
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

        self.frame_rate_task = background(self.refresh_frame_rate())

        while True:
            cam = self.connect()
            if cam:
                break

            if self.status != no_camera_msg:
                self.status = no_camera_msg
                self.logger.error(no_camera_msg)
            await sleep(RECONNECT_TIME)
            # Reinitialize the library in order to re-discover cameras
            # NB This will block forever if called again after a camera
            # has been already discovered!
            self.sdk3.Reinitialise()

        self.camera = cam
        self.status = connected_msg
        self.logger.info(connected_msg)
        self.state = State.INIT

        await self.initialize_camera()

    async def initialize_camera(self):
        """This function does the initial setup of the camera"""
        schema_hash = self.getDeviceSchema().hash
        config_hash = Hash()
        failed = []

        for key, feature in FEATURE_MAP.items():
            access_mode = schema_hash.getAttribute(key, "accessMode")
            if access_mode in (
                    AccessMode.INITONLY.value,
                    AccessMode.RECONFIGURABLE.value):
                # The parameter is writeable
                is_writable = True
            else:
                is_writable = False

            value = getattr(self, key, None)
            if isSet(value) and is_writable:
                # Set values to the camera
                try:
                    self.logger.debug(
                        f"Setting {feature} = {value.value}")
                    setattr(self.camera, feature, value.value)
                except CameraException as e:
                    # Setting of this parameter could be not allowed in the
                    # current status of the camera
                    failed.append(key)
                    self.logger.warning(
                        f"Could not set {key} on camera: {e}. "
                        "This could depend on other camera settings.")

            # Read back value from the camera
            value = getattr(self.camera, feature)
            self.logger.debug(f"Reading {feature}: {value}")
            config_hash[key] = value

            # Register feature callback
            self.register_callback(feature)

        if failed:
            self.status = (
                "The following parameters could not be set: " +
                ", ".join(failed) + ". This could depend on other "
                "camera settings.")

        self.camera.MetadataEnable = True

        # Ranges and options have been updated by the callback function,
        # now we need to publish the new schema.
        self.logger.debug(
            f"Parameters update: {config_hash}")
        await self.publishInjectedParameters(**config_hash)

        await self.update_output_schema_andor()

        # Start polling
        self.connect_or_poll_task = background(self.poll_camera())

        if self.state != State.ERROR:
            self.state = State.ON

    async def update_output_schema_andor(self):
        if not self.camera:
            return

        if self.rotation.value in (0, 180):
            heigth = self.camera.AOIHeight
            width = self.camera.AOIWidth
        else:  # rotated image
            heigth = self.camera.AOIWidth
            width = self.camera.AOIHeight
        shape = (heigth, width)
        pixel_encoding = self.camera.PixelEncoding
        dtype = DATA_TYPE_MAP[pixel_encoding]

        self.logger.debug(
            f"Update output schema: shape={shape} dtype={dtype}")
        await self.update_output_schema(shape, Encoding.GRAY, dtype)

    def update_options(self, key):
        """
        Updates the options for the device parameter specified by the key.

        In order to inject the new options to the schema,
        'publishInjectedParameters' must be called.

        :param key: The key of the property for which we want to update options
        """
        if not self.camera:
            return

        try:
            # This might fail in case 'inner' has been called concurrently
            # and the updated schema has not been published yet.
            schema_hash = self.getDeviceSchema().hash
            self.schema_hash = schema_hash
        except AttributeError as e:
            # Use cached schema if available
            if self.schema_hash:
                schema_hash = self.schema_hash
            else:
                self.logger.debug(
                    f"Could not update options for {key}: {e}")
                return

        # Skip read-only and init-only parameters
        access_mode = schema_hash.getAttribute(key, "accessMode")
        if access_mode != AccessMode.RECONFIGURABLE.value:
            return

        feature = FEATURE_MAP[key]
        feature_type = getattr(self.camera, f"type_{feature}")
        default_value = None
        if "defaultValue" in schema_hash.getAttributes(key):
            default_value = schema_hash.getAttribute(key, "defaultValue")
        options = None
        min_inc = None
        max_inc = None

        if feature_type == "enumerated_string":
            new_options = getattr(self.camera, f"options_{feature}")
            if "options" in schema_hash.getAttributes(key):
                options = schema_hash.getAttribute(key, "options")
            if options == new_options:
                # No change in options
                return
            if default_value and default_value not in new_options:
                default_value = new_options[0]

            self.logger.debug(
                f"Setting new options for {key}: {new_options}")
            # Also change defaultValue if not in options
            setattr(self.__class__, key, Overwrite(
                options=new_options, defaultValue=default_value))
            self.must_update_schema = True

        elif feature_type in ("float", "int"):
            new_min = getattr(self.camera, f"min_{feature}")
            new_max = getattr(self.camera, f"max_{feature}")
            if "minInc" in schema_hash.getAttributes(key):
                min_inc = schema_hash.getAttribute(key, "minInc")
            if "maxInc" in schema_hash.getAttributes(key):
                max_inc = schema_hash.getAttribute(key, "maxInc")
            if min_inc == new_min and max_inc == new_max:
                # No change in allowed range
                return

            if default_value and (
                    default_value < new_min or default_value > new_max):
                default_value = new_min

            self.logger.debug(
                f"Setting new range for {key}: {new_min} - {new_max}")
            # Also change defaultValue if not within range
            setattr(self.__class__, key, Overwrite(
                minInc=new_min, maxInc=new_max, defaultValue=default_value))
            self.must_update_schema = True

    async def poll_camera(self):
        error_count = 0

        while True:
            try:
                for key in ("sensorTemperature", "temperatureStatus",
                            "timestampClock"):
                    self.sync_feature(key)

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

        self.camera.flush()  # cleans any existing queued buffers

        if self.connect_or_poll_task:
            self.connect_or_poll_task.cancel()

        self.state = State.UNKNOWN

        self.connect_or_poll_task = background(self.reconnect())

    async def refresh_frame_rate(self):
        timeserver_id = self.slotGetTime()["timeServerId"]
        while True:
            # Get current tid, timestamp and period from timeserver
            try:
                self.ts_tid, self.ts_timestamp, self.ts_period = (
                    await wait_for(get_timeserver_time(timeserver_id), 1))
            except Exception:
                # Timeserver is offline or not defined. Continue without.
                self.ts_tid, self.ts_timestamp, self.ts_period = (
                    None, None, None)

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
            self.camera.flush()  # cleans any existing queued buffers
            self.camera = None  # needed to allow other clients to connect

    async def slotReconfigure(self, conf, message):
        self.logger.debug(f"slotReconfigure: conf = {conf}")
        await super().slotReconfigure(conf, message)

        if self.must_update_schema:
            self.logger.debug("Injecting new schema")
            await self.publishInjectedParameters()
            self.schema_hash = None
            self.must_update_schema = False

        if SCHEMA_CHANGING_PROPERTIES.intersection(conf):
            # Output channel schema needs update
            await self.update_output_schema_andor()

    slotReconfigure = coslot(slotReconfigure, passMessage=True)
