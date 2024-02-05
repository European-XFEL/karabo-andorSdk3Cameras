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


def test_import_sub_modules():
    """Check the device package for forbidden subimports"""
    try:
        from karabo.common.api import has_sub_imports
        from karabo.middlelayer.testing import get_ast_objects
    except (ModuleNotFoundError, ImportError):
        print("Testing the imports of sub modules is not possible with "
              " existing karabo version.")
        return

    ignore = ["karabo.middlelayer.testing"]
    ast_objects = get_ast_objects(andorSdk3Cameras)
    for ast_obj in ast_objects:
        for mod in ["karabo.middlelayer", "karabo.middlelayer_api"]:
            assert not len(has_sub_imports(ast_obj, mod, ignore))
