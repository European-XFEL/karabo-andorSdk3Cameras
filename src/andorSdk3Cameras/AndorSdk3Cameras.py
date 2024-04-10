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

import os

from pyAndorSDK3 import AndorSDK3, CameraException, ErrorCodes

from imageSourcePy.CameraImageSourceMdl import CameraImageSource
from karabo.middlelayer import (
    AccessMode, Assignment, Double, EncodingType, Slot, State, String, UInt8,
    UInt16, UInt32, Unit, background, sleep)

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
    "frameCount": "FrameCount",
    "exposureTime": "ExposureTime",
    "aoiHBin": "AOIHBin",
    "aoiWitdh": "AOIWidth",
    "aoiLeft": "AOILeft",
    "aoiVBin": "AOIVBin",
    "aoiHeight": "AOIHeight",
    "aoiTop": "AOITop",
    "pixelEncoding": "PixelEncoding"}


class AndorSdk3Cameras(CameraImageSource):
    __version__ = deviceVersion

    camera = None

    def set_feature(self, key, value):
        if self.camera:
            setattr(self.camera, FEATURE_MAP[key], value.value)
        setattr(self, key, value)

    serialNumber = String(
        displayedName="Serial Number",
        accessMode=AccessMode.INITONLY,
        assignment=Assignment.MANDATORY)

    cameraModel = String(
        displayedName="Camera Model",
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

    @Slot(
        displayedName="Acquire",
        allowedStates={State.ON})
    async def acquire(self):

        self.task = background(self.acquire_task)

        self.state = State.ACQUIRING
        self.status = "Acquisition Started"

    async def acquire_task(self):
        while True:
            try:
                img = self.camera.acquire(timeout=1)
                data = img.image  # ndarray
                ts = img.metadata.timestamp  # "ticks" since power up
                # XXX remove after testing
                self.logger.debug(f"Received new image: {data} {ts}")

                # XXX use HW timestamp
                # Use "TimestampClockFrequency" and "TimestampClock"
                # features to convert <ts> to Karabo timestamp

                await self.write_channels(data, encoding=EncodingType.GRAY)

            except CameraException as e:
                if not self.camera.CameraAcquiring:
                    # e.g. reached frame count in fixed cycle mode
                    self.state = State.ON
                    break
                elif e.err_code == ErrorCodes.AT_ERR_TIMEDOUT:
                    # e.g. waiting for external trigger
                    await sleep(0.1)
                    continue
                else:
                    self.logger.error(f"Exception in acquire_task: {e}")
                    self.state = State.ERROR
                    break

            except Exception as e:
                self.logger.error(f"Exception in acquire_task: {e}")
                self.state = State.ERROR
                break

        self.camera.flush()

    @Slot(
        displayedName="Stop",
        allowedStates=[State.ACQUIRING])
    async def stop(self):
        if self.task:
            self.task.cancel()
            self.task = None

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
    async def aoiWitdh(self, value):
        self.set_feature("aoiWitdh", value)

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
        displayedName="Pixel Encoding",
        # XXX read and inject options with self.camera.options_EnumFeatureName
        options=list(DATA_TYPE_MAP),
        defaultValue="Mono16",
        allowedStates={State.UNKNOWN, State.ON})
    async def pixelEncoding(self, value):
        self.set_feature("pixelEncoding", value)

    # XXX more properties
    # BitDepth: Enumerated
    # TriggerMode: Enumerated

    async def onInitialization(self):
        """ This method will be called when the device starts.

            Define your actions to be executed after instantiation.
        """

        # This is needed so that AndorSDK3 can find libatcore.so
        # XXX Set instead LD_LIBRARY_PATH in the server 'run' file
        karabo = os.environ['KARABO']
        path = f"{karabo}/extern/lib"
        if 'LD_LIBRARY_PATH' not in os.environ:
            os.environ['LD_LIBRARY_PATH'] = path
        elif path not in os.environ['LD_LIBRARY_PATH'].split(':'):
            ld_library_path = os.environ['LD_LIBRARY_PATH']
            os.environ['LD_LIBRARY_PATH'] = f"{path}:{ld_library_path}"

        self.task = None

        sdk3 = AndorSDK3()
        cameras = sdk3.cameras
        for cam in cameras:
            if cam.SerialNumber == self.serialNumber:
                self.camera = cam
                break

        if self.camera:
            self.status = f"Connected to {self.serialNumber}"
        else:
            self.status = f"No camera found with SN {self.serialNumber}"
            return

        # Apply settings to the camera
        for key, feature in FEATURE_MAP.items():
            value = getattr(self, key, None)
            if value is not None:
                try:
                    setattr(self.camera, feature, value.value)
                except Exception as e:
                    if self.state != State.ERROR:
                        self.state = State.ERROR
                    self.status = f"Could not set {feature} on camera"
                    self.logger.error(
                        f"Could not set {feature} on camera: {e}")

        self.camera.MetadataEnable = True

        self.cameraModel = self.camera.CameraModel

        heigth = self.camera.AOIHeight
        width = self.camera.AOIWidth
        shape = (heigth, width)
        pixel_encoding = self.camera.PixelEncoding
        dtype = DATA_TYPE_MAP[pixel_encoding]
        await self.update_output_schema(shape, EncodingType.GRAY, dtype)

        if self.state != State.ERROR:
            self.state = State.ON

    async def onDestruction(self):
        if self.camera:
            self.camera.AcquisitionStop()
            self.camera.flush()
