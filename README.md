# AndorSdk3Camera Device (MiddleLayer)

## Overview

This package provides a Karabo control device Andor sCMOS cameras.

The device class inherits from the ImageSourcePy class from the 'imageSourcePy' package.
Therefore its images are available via an output channel under the schema key
'output.schema.data.image'.


## Dependencies

This package depends on the 'imageSourcePy' and the 'processingUtils' Karabo
packages.

It also needs the Andor SDK3 from Andor.


## Setup

The ``LD_LIBRARY_PATH`` environment variable  must be set so that the
``pyAndorSDK3`` module can find the SDK provided libraries.

This can be done e.g. by adding this line to the middle-layer server run
script:


    export LD_LIBRARY_PATH=$KARABO/lib:$KARABO/extern/lib

Also, in order to make the Andor cameras accessible to a normal (non-root)
user, appropriate USB rules need to be defined.

This is done by root by creating the ``99-andor-cameras.rules`` in
``/etc/udev/rules.d/``.

For the Andor Zyla camera the file has to contain

    ATTRS{idVendor}=="136e",ATTRS{idProduct}=="0014",MODE="0666",GROUP="exfel"

After the rules have been created, they can be loaded by rebooting the host,
or by executing

    sudo service udev restart
    sudo udevadm trigger --action=change


## Testing

Every Karabo device in Python is shipped as a regular python package.
In order to make the device visible to any device-server you have to install
the package to Karabo's own Python environment.

Simply type:

    pip install -e .

in the directory of where the ``setup.py`` file is located, or use the ``karabo``
utility script:

    karabo develop andorSdk3Cameras

## Running

If you want to manually start a server using this device, simply type:

    karabo-middlelayerserver serverId=middleLayerServer/1 deviceClasses=AndorSdk3Camera

Or just use (a properly configured):

    karabo-start


## Contact

For questions, please contact opensource@xfel.eu.


## License and Contributing

This software is released by the European XFEL GmbH as is and without any
warranty under the GPLv3 license.
If you have questions on contributing to the project, please get in touch at
opensource@xfel.eu.
