#!/usr/bin/env python3

import numpy as np
from ctapipe.io.datawriter import DataWriter, DATA_MODEL_VERSION
from ctapipe.utils import get_dataset_path
from ctapipe.io import EventSource, DataLevel
from ctapipe.calib import CameraCalibrator
from pathlib import Path
from ctapipe.instrument import SubarrayDescription
from copy import deepcopy
import tables
import logging
from astropy import units as u


def generate_dummy_dl2(event):
    """ generate some dummy DL2 info and see if we can write it """

    algos = ["Hillas", "ImPACT"]

    for algo in algos:
        for tel_id in event.dl1.tel:
            event.dl2.tel[tel_id].geometry[algo].alt = 70 * u.deg
            event.dl2.tel[tel_id].geometry[algo].az = 120 * u.deg
            event.dl2.tel[tel_id].energy[algo].energy = 10 * u.TeV

    event.dl2.stereo.geometry[algo].alt = 72 * u.deg
    event.dl2.stereo.geometry[algo].az = 121 * u.deg
    event.dl2.stereo.energy[algo].energy = 10 * u.TeV


def test_dl1(tmpdir: Path):
    """
    Check that we can write DL1 files

    Parameters
    ----------
    tmpdir :
        temp directory fixture
    """

    output_path = Path(tmpdir / "events.dl1.h5")
    source = EventSource(
        get_dataset_path("gamma_LaPalma_baseline_20Zd_180Az_prod3b_test.simtel.gz"),
        max_events=20,
        allowed_tels=[1, 2, 3, 4],
    )
    calibrate = CameraCalibrator(subarray=source.subarray)

    with DataWriter(
        event_source=source,
        output_path=output_path,
        write_parameters=False,
        write_images=True,
    ) as write_dl1:
        write_dl1.log.level = logging.DEBUG
        for event in source:
            calibrate(event)
            write_dl1(event)
        write_dl1.write_simulation_histograms(source)

    assert output_path.exists()

    # check we can get the subarray description:
    sub = SubarrayDescription.from_hdf(output_path)
    assert sub.num_tels > 0

    # check a few things in the output just to make sure there is output. For a
    # full test of the data model, a verify tool should be created.
    with tables.open_file(output_path) as h5file:
        images = h5file.get_node("/dl1/event/telescope/images/tel_001")
        assert images.col("image").max() > 0.0
        assert (
            h5file.root._v_attrs[
                "CTA PRODUCT DATA MODEL VERSION"
            ]  # pylint: disable=protected-access
            == DATA_MODEL_VERSION
        )
        shower = h5file.get_node("/simulation/event/subarray/shower")
        assert len(shower) > 0
        assert shower.col("true_alt").mean() > 0.0
        assert (
            shower._v_attrs["true_alt_UNIT"] == "deg"
        )  # pylint: disable=protected-access


def test_roundtrip(tmpdir: Path):
    """
    Check that we can write DL1+DL2 info to files and read them back

    Parameters
    ----------
    tmpdir :
        temp directory fixture
    """

    output_path = Path(tmpdir / "events.DL1DL2.h5")
    source = EventSource(
        get_dataset_path("gamma_LaPalma_baseline_20Zd_180Az_prod3b_test.simtel.gz"),
        max_events=20,
        allowed_tels=[1, 2, 3, 4],
    )
    calibrate = CameraCalibrator(subarray=source.subarray)

    events = []

    with DataWriter(
        event_source=source,
        output_path=output_path,
        write_parameters=False,
        write_images=True,
        transform_image=True,
        image_dtype="int32",
        image_scale=10,
        transform_peak_time=True,
        peak_time_dtype="int16",
        peak_time_scale=100,
        write_stereo_shower=True,
        write_mono_shower=True,
    ) as write:
        write.log.level = logging.DEBUG
        for event in source:
            calibrate(event)
            write(event)
            generate_dummy_dl2(event)
            events.append(deepcopy(event))
        write.write_simulation_histograms(source)
        assert DataLevel.DL1_IMAGES in write.output_data_levels
        assert DataLevel.DL1_PARAMETERS not in write.output_data_levels
        assert DataLevel.DL2 in write.output_data_levels

    assert output_path.exists()

    # check we can get the subarray description:
    sub = SubarrayDescription.from_hdf(output_path)
    assert sub.num_tels > 0

    # check a few things in the output just to make sure there is output. For a
    # full test of the data model, a verify tool should be created.
    with tables.open_file(output_path) as h5file:
        images = h5file.get_node("/dl1/event/telescope/images/tel_001")

        assert len(images) > 0
        assert images.col("image").dtype == np.int32
        assert images.col("peak_time").dtype == np.int16
        assert images.col("image").max() > 0.0

        # check that DL2 info is there
        dl2_energy = h5file.get_node("/dl2/event/stereo/energy/ImPACT")
        assert np.allclose(dl2_energy.col("energy"), 10)

        dl2_tel_energy = h5file.get_node("/dl2/event/mono/energy/Hillas")
        assert np.allclose(dl2_tel_energy.col("energy"), 10)

        assert len(dl2_tel_energy.col("energy")) > len(dl2_energy.col("energy"))

    # make sure it is readable by the event source and matches the images

    for event in EventSource(output_path):

        for tel_id, dl1 in event.dl1.tel.items():
            original_image = events[event.count].dl1.tel[tel_id].image
            read_image = dl1.image
            assert np.allclose(original_image, read_image, atol=0.1)

            original_peaktime = events[event.count].dl1.tel[tel_id].peak_time
            read_peaktime = dl1.peak_time
            assert np.allclose(original_peaktime, read_peaktime, atol=0.01)
