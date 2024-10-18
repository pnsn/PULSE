from pathlib import Path
from obspy import read, Trace
from obspy.core.trace import Stats
import numpy as np

def load_townsend_example():
    data_path = Path(__file__).parent.parent
    data = data_path / 'files' / 'uw61965081_PortTownsend_M4.3.mseed'
    # data = os.path.join('PULSE','test','files','uw61965081_PortTownsend_M4.3.mseed')
    st = read(data)
    return st

def load_logo_vector():
    data = [0,0,0,2,4,6,4,2,0,-2,-4,-6,-4,-2,0,-1,-2,-1,0,-1,-2,-1,0,0,1,0,0,-1,0,0]
    return np.array(data, dtype=np.float64)

def load_logo_trace():
    tr = Trace(data=load_logo_vector(),
               header={'network':'UW',
                       'station':'PULSE',
                       'location':'LO',
                       'channel':'GO1'})
    return tr.copy()

def make_gappy_trace(tr,fill_value=-999, frac1=0.25, frac2=0.5):
    ii = int(round(frac1*tr.stats.npts))
    jj = int(round(frac2*tr.stats.npts))
    mtr = tr.copy()
    mtr.data = np.ma.MaskedArray(data=mtr.data,
                                 mask=[False]*tr.stats.npts,
                                 fill_value=fill_value)
    mtr.data.mask[ii:jj] = True
    return mtr


def assert_common_trace(tracelike0, tracelike1):
    # Check types
    assert isinstance(tracelike0, Trace)
    assert isinstance(tracelike1, Trace)
    # Check data
    np.testing.assert_array_equal(tracelike0.data, tracelike1.data)
    # Check dtype
    assert tracelike0.data.dtype == tracelike1.data.dtype
    # Check stats
    for _k in Stats.defaults.keys():
        assert tracelike0.stats[_k] == tracelike1.stats[_k]


def assert_common_trace_set(traceset0, traceset1):
    # Test that both have __iter__
    assert hasattr(traceset0, '__iter__')
    assert hasattr(traceset1, '__iter__')
    