Fritz Backward Search
=====================

The fritzCallMon script monitors the incoming and outgoing external calls in the Fritz!Box and calls the fritzBackwardSearch script.
This script queries the phone caller list for unknown callers using the TR-064 interface of a Fritz!Box, implemented with the
(https://pypi.python.org/pypi/fritzconnection) package, does a backward search in the internet and updates the Fritz phone book with the
number and name.

Full documentation can be found on [read the docs](https://fritz-backward-search.readthedocs.org/).
