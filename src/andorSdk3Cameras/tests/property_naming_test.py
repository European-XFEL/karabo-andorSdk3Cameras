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
import andorSdk3Cameras


def test_property_code_guideline():
    """Test that all properties and slots follow common code style"""
    try:
        from karabo.middlelayer.testing import check_device_package_properties
    except (ImportError, ModuleNotFoundError):
        print("Checking device properties not possible with existing "
              "karabo version.")
        return
    keys = check_device_package_properties(andorSdk3Cameras)
    msg = ("The key naming does not comply with our coding guidelines. "
           f"Please have a look at (class: paths): {keys}")
    assert not keys, msg
