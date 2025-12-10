# AndorSdk3Camera Device (MiddleLayer)

![Karabo Badge](https://img.shields.io/badge/andorSdk3Cameras-blue?style=social&logo=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAYAAADgdz34AAAAAXNSR0IArs4c6QAAAIRlWElmTU0AKgAAAAgABQESAAMAAAABAAEAAAEaAAUAAAABAAAASgEbAAUAAAABAAAAUgEoAAMAAAABAAIAAIdpAAQAAAABAAAAWgAAAAAAAABIAAAAAQAAAEgAAAABAAOgAQADAAAAAQABAACgAgAEAAAAAQAAABigAwAEAAAAAQAAABgAAAAAEQ8YrgAAAAlwSFlzAAALEwAACxMBAJqcGAAAAVlpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IlhNUCBDb3JlIDYuMC4wIj4KICAgPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4KICAgICAgPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIKICAgICAgICAgICAgeG1sbnM6dGlmZj0iaHR0cDovL25zLmFkb2JlLmNvbS90aWZmLzEuMC8iPgogICAgICAgICA8dGlmZjpPcmllbnRhdGlvbj4xPC90aWZmOk9yaWVudGF0aW9uPgogICAgICA8L3JkZjpEZXNjcmlwdGlvbj4KICAgPC9yZGY6UkRGPgo8L3g6eG1wbWV0YT4KGV7hBwAAB4lJREFUSA1tVQlwU9cVPX%2FXZmuxZcuSjWyMwQaDsUvLWmo7bEOHLSnETckQBgITWpO2CSmTlqnatEyazNCWpmEZYEpCS7DLpA3FbVPWTAIJ2GZfHNsgL1iWZGuz9S19Sf%2F1fWfSYdpeaeZ96f13l3PPuY%2FZsuWA0CfdZlFWhsDR22pb28EUHrOT2yt2jcrJpWlVcqWUaFEqMcDprTXQm10RNtF%2FNdfQ%2BeLiN0bvPXZk%2FLHW4%2BH1NhvH%2FPeG9vvNG4PGHXd99p3Xji%2FfZn3j93ZrHkZVFhkIAKMDUkGVVSJsJg00%2B585v73i%2BT0vS6PDCYur56mV1YE6hqE7X5gWwFD5zafdtvKaCpImlUl5pJIjqFCM5pLcRMi41%2FV6anIR9W0ATz8cVDDQjsehen1Qfte3WdfElaIkPqSOESZgMFt6ddlZDxgl0clmZXfwjUdOt930DRUakTFF%2FX6M%2BANIyTLUTAZ9LEfez%2FmRUC%2BnhVyavMAQEOpbSbHwj4H9LAHd5VA0Q4LtiFA4IEoOnSA4THbH10IZgqlmmlUKnFU0ZJv0AqvqbHZic5dkFDlOg4wwylic%2B2Uwxey8F4FFL8GpE5EhBB1yAoiNAkYd5hZO5MrLdCqnN6YFSa%2BC40k6EmIu3HnI1q36Bs%2FHlNSVzjPnViS7vCn3E3Ml5%2FQqTjLbkFGSFAuCRckxxKNhhINBDA08wmg4jEpnAXKnToTRagMr6UEYhiWEsDq9Af23buLRgSO00GIms2JhiOd5od9sz8GN0wcYX0cvlr5qRv6kMqR1OgR6e8BxPLLyXLC4iuGunAllNEobTVvHsEiMxDD84C6sBQWw5ORgqNeLwJV2JGFSMd%2FNyWk1wDM879VlmSiyZaS8qhj%2F3H0YmDwFVfWVkD%2B9gs7rXrjnTYO1uAiumhqIhixEB%2FrRc%2FlT9LV7oUS8KJhZDZ%2FMAZ8HqZ8RTDQaSFDgkQIJsYIk9PCShBxE2Ps3OvHK7k349Y4VCN%2FroM79KJnsQs%2Blh7j%2Bp99AHh4Gy%2FNIRKPoPncMlmwB2TnFiJuy8NOty%2FDR1bew81db8SB%2BFVUuO1SWC%2FOEZfoLCp34BEXc6k215OUXnmVyzCY8tWoZdh9sxv6feFA%2Bax7utxKKzBey4UQBkjQXVjaDjuEUDr2yGasXzKTEiOE7y79OHnhfRbfNDYHjo2yByA2yBkMK65exP%2FvBc0SJjyIwOIgiuwVb1i4FapYg2toPkRaf0ZSlGQ2UR1Lo8N7Fih%2BuQVWxAx237%2BDa9Tuwm41YvmgB00ZFIzGIsjkWw7BKyDCsFhj0OlWWxzAYGEZz8wcoddjw7i82w4cgyqAgnc6M%2B%2BdYFn3K55Qo89CweB7I2Ag4UURl1XRkOAnJRBIOWiUYEmW%2FXzszSsXhAysgGhtRbTkWHD58AuXlZcjONmHJnBn49s5G3EE7skQeVAYQqTPAhKcbFqK6rAjuCS44CvIRDkUotQE5HmcHKa15UYyyFFciZFKPcOEmzXxIpWFRUuwET1mgqiosJj1qZ5QCdd9DfukkpKk%2BDDYb8jZvhSNLD53AYcAXxIWLn%2BHGjbuIyQly9szHTFlkCGlWiLJazVQovRp13953nPTSl1etXIre3gGEwxGwHAdWGxB5FjACLZuWQHUFSa8fz1Y7393thd8fRGGhA5%2B03sTfmvaj1JkHJZ2JjQeQVaZ3%2BdxKtPzlIHP67CUUuSdgWsUkdHY%2BBE%2FxNpuzKb3HQOh80pyDqHSuEiRSaToZeOTbbVi5vA7Fk0px7OSHNKQFyaRCURAj4wF4ke%2BP0D%2FMFJ9dLx4ll9pvw1lUiK%2FOqkJfIIQP%2FnERViFDhaMpmLKJBnFLPPZ7jqG55TyKSidCpYrfd%2BQ9nP%2FzvrTZOBWixQomkx6j8qNMXLvJSjuyUVb0fNh7LX300DlIFpYR9Abm5789ivfe8qBQpmp35cFI8U%2FEIuj61zlEHj3Ah6daESWjePfURfX4xfuZKdVzhOr1a%2BDIsb6zcIp5v9Z0eDwetrt4weZ4PL4r1NNTqFHurC%2BQxuG%2FU%2FBjQulXytHddg3T161BWX09Yo96cea1A8iblAcmMAp%2FuVuZv2Sh6HS5wMgjQ26XY9ubDU80a7413jEehqHswUFP68CxLlPWS4qiND43o9ouz6rBpUPvJLrbung6rHmGNlzDX1utJXYEuryqmOVQVjQ8qTMaKaOSoyfqqmq%2Bu2FRxTCwliOkibC0azRLoLGlRfLMcsrHNtS%2FJqrxqnhgcA8RhPi0b63W2adP4JP4OJGKyxqF6JdB%2BGGnwjmd6vzGdTo9q%2FrsJPHMH7Y3NGjOG%2Fe2SPQy1VRJxiHSAmhW6znPw%2B3lL2zcSG8UYP3bf52SFsQdY7K8yd%2FZhajPl6mor1Pl4SDpuXVLnDJ7NnKzjX%2BcnZ%2F%2F0vOr5vixtonzTAPn8axTtPP0jqCp%2FB9b29QkBu%2Fa1QueuvHhs%2BXk5ZpYOPpjJZV%2BkvISybE4DKoSKMrN3bbn2cUnx13s3St5QqEU7acG97hpAb58%2Ft%2BVbm450EqV9R89YcOJj%2BY37DvV%2BsLB90%2B1tHfatUNNTU3cXgrvl8609bFn7t8fxThrSai%2FQAAAAABJRU5ErkJggg%3D%3D)
![GitHub language count](https://img.shields.io/github/languages/count/European-XFEL/Karabo-andorSdk3Cameras)
![GitHub top language](https://img.shields.io/github/languages/top/European-XFEL/Karabo-andorSdk3Cameras)
![GitHub contributors](https://img.shields.io/github/contributors/European-XFEL/Karabo-andorSdk3Cameras)


## Overview

This package provides a Karabo control device for Andor sCMOS cameras.

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
