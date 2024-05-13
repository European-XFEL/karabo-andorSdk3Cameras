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
import pytest

from karabo.middlelayer import State
from karabo.middlelayer.testing import AsyncDeviceContext, event_loop

from ..AndorSdk3Camera import AndorSdk3Camera

_DEVICE_CONFIG = {
    "_deviceId_": "TestAndorSdk3Camera",
    "serialNumber": "S01234"
}


@pytest.mark.timeout(30)
@pytest.mark.asyncio
async def test_greeting(event_loop: event_loop):
    device = AndorSdk3Camera(_DEVICE_CONFIG)
    async with AsyncDeviceContext(device=device) as ctx:
        assert ctx.instances["device"] is device
        assert device.state == State.UNKNOWN
