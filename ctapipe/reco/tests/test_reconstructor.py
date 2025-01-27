"""
Test for Reconstructor base class
"""


def test_plugin(subarray_prod5_paranal):
    from ctapipe.reco import Reconstructor

    subarray = subarray_prod5_paranal
    reconstructor = Reconstructor.from_name("PluginReconstructor", subarray)
    assert reconstructor.__module__ == "ctapipe_test_plugin"
    assert reconstructor.__class__.__name__ == "PluginReconstructor"
