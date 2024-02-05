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
import os.path as op
import subprocess

import andorSdk3Cameras

IGNORE_LIST = ["setup.py", "__init__.py"]


def get_python_files():
    """Get all python files from this package
    """
    common_dir = op.abspath(op.dirname(andorSdk3Cameras.__file__))
    flake_check = []
    for dirpath, _, filenames in os.walk(common_dir):
        for fn in filenames:
            if op.splitext(fn)[-1].lower() == ".py" and fn not in IGNORE_LIST:
                path = op.join(dirpath, fn)
                flake_check.append(path)

    return flake_check


def test_code_quality_flake8():
    files = get_python_files()
    command = ["flake8", *[op.abspath(py_file) for py_file in files]]
    subprocess.check_call(command)
