from pyproj import Proj
import math
import pandas as pd
import pytz
from tzwhere import tzwhere
from dateutil import parser
import numpy as np 

def lat_lon_to_modis(lat, lon):
    CELLS = 2400
    VERTICAL_TILES = 18
    HORIZONTAL_TILES = 36
    EARTH_RADIUS = 6371007.181
    EARTH_WIDTH = 2 * math.pi * EARTH_RADIUS

    TILE_WIDTH = EARTH_WIDTH / HORIZONTAL_TILES
    TILE_HEIGHT = TILE_WIDTH
    CELL_SIZE = TILE_WIDTH / CELLS
    MODIS_GRID = Proj(f'+proj=sinu +R={EARTH_RADIUS} +nadgrids=@null +wktext')
    x, y = MODIS_GRID(lon, lat)
    h = (EARTH_WIDTH * .5 + x) / TILE_WIDTH
    v = -(EARTH_WIDTH * .25 + y - (VERTICAL_TILES - 0) * TILE_HEIGHT) / TILE_HEIGHT
    return int(h), int(v)



class flux_tower_data:
    # Class to store flux tower data in unique format
    
    def __init__(self, t_start, t_stop, ssrd_key, t2m_key,
                 site_name, lon, lat, land_cover_type):
        self.tstart = t_start
        self.tstop = t_stop
        self.t2m_key = t2m_key
        self.ssrd_key = ssrd_key
        self.land_cover_type = land_cover_type
        self.len = None
        self.site_dict = None
        self.site_name = site_name
        self.lon = lon
        self.lat = lat 
        return
    
    def get_utcs(self):
        return self.site_dict[list(self.site_dict.keys())[0]]['flux_data']['datetime_utc'].values

    def get_lonlat(self):
        return (self.lon, self.lat)

    def get_site_name(self):
        return self.site_name
    
    def get_data(self):
        return self.flux_data
    
    def get_len(self):
        return len(self.flux_data)
        
    def get_land_type(self):
        return self.land_cover_type
    
    def drop_rows_by_index(self, indices):
        self.flux_data = self.flux_data.drop(indices)
        
    def add_columns(self, add_dict):
        for i in add_dict.keys():
            self.flux_data[i] = add_dict[i]
        return
        
class fluxnet(flux_tower_data):
    
    def __init__(self, t_start, t_stop, ssrd_key, t2m_key, site_name,
                 lon, lat, land_cover_type, use_vars=None):
        super().__init__(t_start, t_stop, ssrd_key, t2m_key,
                         site_name, lon, lat, land_cover_type)
        if use_vars is None:
            self.vars = variables = ['NEE_CUT_REF', 'NEE_VUT_REF', 'NEE_CUT_REF_QC', 'NEE_VUT_REF_QC',
                                    'GPP_NT_VUT_REF', 'GPP_NT_CUT_REF', 'GPP_DT_VUT_REF', 'GPP_DT_CUT_REF',
                                    'TIMESTAMP_START', 'TIMESTAMP_END', 'WD', 'WS', 
                                    'SW_IN_F', 'TA_F', 'USTAR', 'RECO_NT_VUT_REF']
        else:
            self.vars = use_vars

        return

    def add_flux_tower(self, datapath):
        idata = pd.read_csv(datapath, usecols=lambda x: x in self.vars)
        idata.rename({self.ssrd_key: 'ssrd', self.t2m_key: 't2m'}, inplace=True, axis=1)
        tzw = tzwhere.tzwhere()
        timezone_str = tzw.tzNameAt(self.lat, self.lon) 
        timezone = pytz.timezone(timezone_str)
        dt = parser.parse('200001010000') # pick a date that is definitely standard time and not DST 
        datetime_u = []
        for i, row in idata.iterrows():
            datetime_u.append(parser.parse(str(int(row['TIMESTAMP_END'])))  -  timezone.utcoffset(dt))
        datetime_u = np.array(datetime_u)
        mask = (datetime_u >= self.tstart) & (datetime_u <= self.tstop)
        idata['datetime_utc'] = datetime_u
        flux_data = idata[mask]
        this_len = len(flux_data)
        print(this_len)
        if this_len < 2:
            print('No data for {} in given time range'.format(self.site_name))
            years = np.unique([t.year for t in datetime_u])
            print('Data only available for the following years {}'.format(years))
            return False
        else:
            self.flux_data = flux_data
            return True

    

        
        