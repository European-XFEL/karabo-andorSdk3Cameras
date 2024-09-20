# AndorSdk3Camera Device (MiddleLayer)

## Setup

The ``LD_LIBRARY_PATH`` environment variable  must be set so that the
``pyAndorSDK3`` module can find the SDK provided libraries.

This can be done e.g. by adding this line to the middle-layer server run
script:


    export LD_LIBRARY_PATH=$KARABO/lib:$KARABO/extern/lib

Also, in order to make the Andor cameras accessible to a normal (non-root)
user, appropriate USB rules need to be defined.

This is done by root by copying the ``99-andor-cameras.rules`` file from
``$KARABO/extern/andor/etc/`` to ``/etc/udev/rules.d/``.

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
