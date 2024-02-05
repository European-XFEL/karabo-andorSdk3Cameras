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

from karabo.middlelayer import Device, Slot, String

from ._version import version as deviceVersion


class AndorSdk3Cameras(Device):
    __version__ = deviceVersion

    greeting = String()

    @Slot()
    async def hello(self):
        self.greeting = "Hello world!"

    def __init__(self, configuration):
        super().__init__(configuration)

    async def onInitialization(self):
        """ This method will be called when the device starts.

            Define your actions to be executed after instantiation.
        """
