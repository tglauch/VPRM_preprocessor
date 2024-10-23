# from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
import sys
import os
import time
from shapely.geometry import Point, Polygon, box
import rioxarray as rxr
import zipfile
import glob
from pyproj import Transformer
import geopandas as gpd
from pyVPRM.lib import downmodis
import math
from pyproj import Proj
from affine import Affine
from rioxarray.rioxarray import affine_to_coords
import requests
from requests.auth import HTTPDigestAuth
from rioxarray import merge
import yaml
import warnings

warnings.filterwarnings("ignore")
from matplotlib.colors import LinearSegmentedColormap
from lxml import etree
from datetime import datetime
from rasterio.warp import calculate_default_transform
import h5py
from dateutil import parser
import xarray as xr
from datetime import datetime, timedelta, date
import numpy as np
from pyVPRM.sat_managers.base_manager import earthdata
from loguru import logger

class VIIRS(earthdata):
    # Class to download and load VIIRS data

    def __init__(self, datapath=None, sat_image_path=None, sat_img=None):
        super().__init__(datapath, sat_image_path, sat_img)
        self.use_keys = []
        self.load_kwargs = {"variable": self.use_keys}
        self.sat = "VIIRS"
        self.path = "VIIRS"
        self.product = 'VNP09GA.001' 
        self.pixel_size = 463.312716527778

    def get_files(self, dest):
        return glob.glob(os.path.join(dest, "*.h5"))

    def set_sat_img(self, ind):
        # implements ones M and L bands are used. Currently only M bands implemented.
        return

    def set_band_names(self):
        logger.info("Trying to set reflectance bands assuming standard naming for VIIRS")
        bands = []
        for k in list(self.sat_img.data_vars):
            if ("SurfReflect_I" not in k) & ("SurfReflect_M" not in k):
                continue
            bands.append(k)
        self.bands = bands

    def individual_loading(self):
        t = rxr.open_rasterio(self.sat_image_path, masked=True, cache=False)
        obs_time = parser.parse(t[0].attrs['RangeBeginningDate']) + timedelta(hours=12)
        for key in ['HDFEOS_GRIDS_VNP_Grid_1km_2D_Data_Fields_SurfReflect_QF1_1',
                    'HDFEOS_GRIDS_VNP_Grid_1km_2D_Data_Fields_SurfReflect_QF2_1',
                    'HDFEOS_GRIDS_VNP_Grid_1km_2D_Data_Fields_SurfReflect_QF6_1']:
            test = t[0][key].sel(x=t[1].coords['x'], y=t[1].coords['y'], method='nearest')
            test.coords['x'] = t[1].coords['x']
            test.coords['y'] = t[1].coords['y']
            t[1][key] = test 
        t[1]= t[1].assign_coords({'time': obs_time})
        self.sat_img = t[1]
        self.set_band_names()
        return

    def mask_bad_pixels(self, bands=None):
        if bands is None:
            bands = self.bands

        band_nums = [int(band[-1]) for band in bands]
        masks = dict()

        for b in band_nums:
            if b > 2:  ## VIIRS only has quality mask for band1 and band2
                continue
            start_bit = b * 4  # Start Bit
            end_bit = b * 4 + 3  # End Bit  (inclusive)
            num_bits_to_extract = end_bit - start_bit + 1
            bit_mask = (1 << num_bits_to_extract) - 1
            masks[b] = (
                np.array(self.sat_img["SurfReflect_QC_500m"].values, dtype=np.uint32)
                >> start_bit
            ) & bit_mask

        for mask_int in masks.keys():
            masks[mask_int] = masks[mask_int] != int("0000", 2)
            self.sat_img["SurfReflect_I{}".format(mask_int)] = xr.where(
                masks[mask_int],
                np.nan,
                self.sat_img["SurfReflect_I{}".format(mask_int)],
            )
            # self.sat_img['SurfReflect_I{}'.format(mask_int)].values[masks[mask_int]] = np.nan
        return

    def mask_clouds(self, bands=None):
        if bands is None:
            bands = self.bands

        start_bit = 2  # Start Bit
        end_bit = 3  # End Bit  (inclusive)
        num_bits_to_extract = end_bit - start_bit + 1
        bit_mask = (1 << num_bits_to_extract) - 1
        mask1 = (
            (
                np.array(t[1]['HDFEOS_GRIDS_VNP_Grid_1km_2D_Data_Fields_SurfReflect_QF1_1'].values, dtype=np.uint32)
                >> start_bit
            )
            & bit_mask
        ) != int("00", 2)
        
        #Cloud Shadow
        start_bit = 3  # Start Bit
        end_bit = 3  # End Bit  (inclusive)
        num_bits_to_extract = end_bit - start_bit + 1
        bit_mask = (1 << num_bits_to_extract) - 1
        mask2 = (
            (
                np.array(t[1]['HDFEOS_GRIDS_VNP_Grid_1km_2D_Data_Fields_SurfReflect_QF2_1'].values, dtype=np.uint32)
                >> start_bit
            )
            & bit_mask
        ) != int("0", 2)

        for b in bands:
            self.sat_img[b] = xr.where((mask1 | mask2), np.nan, self.sat_img[b])
        return

    def mask_snow(self, bands=None):
        if bands is None:
            bands = self.bands
        start_bit = 5  # Start Bit
        end_bit = 5  # End Bit  (inclusive)
        num_bits_to_extract = end_bit - start_bit + 1
        bit_mask = (1 << num_bits_to_extract) - 1
        mask = (
            (
                np.array(t[1]['HDFEOS_GRIDS_VNP_Grid_1km_2D_Data_Fields_SurfReflect_QF2_1'].values, dtype=np.uint32)
                >> start_bit
            )
            & bit_mask
        ) != int("0", 2)
        for b in bands:
            self.sat_img[b] = xr.where(mask, np.inf, self.sat_img[b])
        return

    def get_recording_time(self):
        date0 = datetime.strptime(
            self.meta_data["RangeBeginningDate"]
            + "T"
            + self.meta_data["RangeBeginningTime"]
            + "Z",
            "%Y-%m-%dT%H:%M:%S.%fZ",
        )
        date1 = datetime.strptime(
            self.meta_data["RangeEndingDate"]
            + "T"
            + self.meta_data["RangeEndingTime"]
            + "Z",
            "%Y-%m-%dT%H:%M:%S.%fZ",
        )
        return date0 + (date1 - date0) / 2
