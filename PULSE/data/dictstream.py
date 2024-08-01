"""
:module: PULSE.data.dictstream
:author: Nathan T. Stevens
:email: ntsteven@uw.edu
:org: Pacific Northwest Seismic Network
:license: AGPL-3.0
:purpose:
    This contains the class definition for DictStream data objects that extend functionalities
    of :class:`~obspy.core.stream.Stream` and coordinates with functionalities of
    :class:`~PULSE.data.mltrace.MLTrace` class. It uses a *dictionary* to hold traces,
    rather than a *list* used by :class:`~obspy.core.stream.Stream`. This accelerates sorting, slicing,
    and querying individual traces (or sets of traces) via the hash-table functionality that 
    underlies python dictionaries. 
    
    In exchange, this places more restrictions on the objects that can be placed in a
    :class:`~PULSE.data.dictstream.DictStream` object in comparison to it's ObsPy forebearer
    as dictionaries require unique keys for each entry.

    We also added a **stats** attribute to :class:`~PULSE.data.dictstream.DictStream` objects
    (:class:`~PULSE.data.dictstream.DictStreamStats`) that provides summary metadata on the 
    contents of the DictStream, similar to the :class:`~obspy.core.trace.Stats` class.

TODO: Ensure import paths in documentation are up to date and in sphinx formatting
TODO: cleanup extraneous (developmental) methods that are commented out
TODO: 
"""

import fnmatch, os, obspy, logging
import pandas as pd
from obspy.core.utcdatetime import UTCDateTime
from obspy.core.stream import Stream
from obspy.core.trace import Trace
from obspy.core.util.attribdict import AttribDict
from obspy.core import compatibility
from PULSE.data.mltrace import MLTrace, wave2mltrace

###################################################################################
# Dictionary Stream Stats Class Definition ########################################
###################################################################################

class DictStreamStats(AttribDict):
    """
    A class to contain metadata for a :class:`~PULSE.data.dictstream.DictStream` object
    of the based on the ObsPy AttribDict (Attribute Dictionary) class. 

    This operates very similarly to :class:`~obspy.core.trace.Stats` objects

    """
    defaults = {
        'common_id': '*',
        'min_starttime': None,
        'max_starttime': None,
        'min_endtime': None,
        'max_endtime': None,
        'processing': []
    }

    _types = {'common_id': str,
              'min_starttime': (type(None), UTCDateTime),
              'max_starttime': (type(None), UTCDateTime),
              'min_endtime': (type(None), UTCDateTime),
              'max_endtime': (type(None), UTCDateTime)}

    def __init__(self, header={}):
        """Initialize a DictStreamStats object

        A container for additional header information of a PULSE :class:`~PULSE.data.dictstream.DictStream` object


        :param header: Non-default key-value pairs to include with this DictStreamStats object, defaults to {}
        :type header: dict, optional
        """        
        super(DictStreamStats, self).__init__()
        self.update(header)
    
    def _pretty_str(self, priorized_keys=[], hidden_keys=[], min_label_length=16):
        """
        Return tidier string representation of this :class:`~PULSE.data.dictstream.DictStreamStats` object

        Based on the :meth:`~obspy.core.util.attribdict.AttribDict._pretty_str` method, and adds
        a `hidden_keys` argument

        :param priorized_keys: Keys of current AttribDict which will be
            shown before all other keywords. Those keywords must exists
            otherwise an exception will be raised. Defaults to [].
        :type priorized_keys: list, optional
        :param hidden_keys: Keys of current AttribDict that will be hidden, defaults to []
                        NOTE: does not supercede items in prioritized_keys.
        :param min_label_length: Minimum label length for keywords, defaults to 16.
        :type min_label_length: int, optional
        :return: String representation of object contents.
        """
        keys = list(self.keys())
        # determine longest key name for alignment of all items
        try:
            i = max(max([len(k) for k in keys]), min_label_length)
        except ValueError:
            # no keys
            return ""
        pattern = "%%%ds: %%s" % (i)
        # check if keys exist
        other_keys = [k for k in keys if k not in priorized_keys and k not in hidden_keys]
        # priorized keys first + all other keys
        keys = priorized_keys + sorted(other_keys)
        head = [pattern % (k, self.__dict__[k]) for k in keys]
        return "\n".join(head)


    def __str__(self):
        prioritized_keys = ['common_id',
                            'min_starttime',
                            'max_starttime',
                            'min_endtime',
                            'max_endtime',
                            'processing']
        return self._pretty_str(prioritized_keys)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))


    def update_time_range(self, trace):
        """
        Update the minimum and maximum starttime and endtime attributes of this :class:`~PULSE.data.dictstream.DictStreamStats` object using timing information from an obspy Trace-like object.

        :param trace: trace-like object with :attr:`stats` from which to query starttime and endtime information
        :type trace: obspy.core.trace.Trace
        """
        if self.min_starttime is None or self.min_starttime > trace.stats.starttime:
            self.min_starttime = trace.stats.starttime
        if self.max_starttime is None or self.max_starttime < trace.stats.starttime:
            self.max_starttime = trace.stats.starttime
        if self.min_endtime is None or self.min_endtime > trace.stats.endtime:
            self.min_endtime = trace.stats.endtime
        if self.max_endtime is None or self.max_endtime < trace.stats.endtime:
            self.max_endtime = trace.stats.endtime

###################################################################################
# Dictionary Stream Class Definition ##############################################
###################################################################################

class DictStream(Stream):
    """
    Dictionary like object of multiple PULSE :class:`~PULSE.data.mltrace.MLTrace` objects

    :param traces: initial list of ObsPy Trace-lke objects, defaults to []
    :type traces: list of :class:`~obspy.core.trace.Trace` (or children) objects, optional
        NOTE: all ingested traces are converted into :class:`~PULSE.data.mltrace.MLTrace` objects
    :param header: initial dictionary of key-value pairs to pass to PULSE :meth:`~PULSE.data.dictstream.DictStreamStats.__init__`, defaults to {}
    :type header: dict-like, optional
    :param key_attr: attribute of each trace in traces to use for their unique key values such that a DictStream.traces entry is {tr.key_attr: tr}, defaults to 'id'
    :type key_attr: str, optional
        Based on N.S.L.C.M.W from PULSE :class:`~PULSE.data.mltrace.MLTraceStats`
            Network.Station.Location.Channel.Model
            with Channel = SEED Channel naming convention
                Character 0: Band character
                Character 1: Instrument character
                Character 2: Component character

        Supported values:
            'id' - N.S.L.C(.M.W) code (see :class: `~PULSE.data.mltrace.MLTrace`)
            'site' - N.S code
            'inst' - Band+Instrument characters
            'instrument' - N.S.L.BandInst?(.M.W)
            'component' - component character
            'mod': - M.W code

        also see :meth: `~PULSE.data.mltrace.MLTrace.get_id_element_dict`
    :param **options: key word argument gatherer that passes optional kwargs to
        :meth: `~PULSE.data.dictstream.DictStream.__add__` for merging input
        traces that have the same `key_attr`
        NOTE: This is how DictStream objects handle matching trace ID's (key_attr values)
        for multiple traces.
    :type **options: kwargs

    .. rubric:: Basic Usage

    >>> from obspy import read
    >>> st = read()
    >>> traces = [tr for tr in st]
    >>> dst = DictStream(traces=traces)
    >>> dst
    --Stats--
           common_id: BW.RJOB.--.EH?..
       min_starttime: 2009-08-24T00:20:03.000000Z
       max_starttime: 2009-08-24T00:20:03.000000Z
         min_endtime: 2009-08-24T00:20:32.990000Z
         max_endtime: 2009-08-24T00:20:32.990000Z
          processing: []
    -------
    3 MLTrace(s) in DictStream
    BW.RJOB.--.EHZ.. : BW.RJOB.--.EHZ.. | 2009-08-24T00:20:03.000000Z - 2009-08-24T00:20:32.990000Z | 100.0 Hz, 3000 samples
    BW.RJOB.--.EHN.. : BW.RJOB.--.EHN.. | 2009-08-24T00:20:03.000000Z - 2009-08-24T00:20:32.990000Z | 100.0 Hz, 3000 samples
    BW.RJOB.--.EHE.. : BW.RJOB.--.EHE.. | 2009-08-24T00:20:03.000000Z - 2009-08-24T00:20:32.990000Z | 100.0 Hz, 3000 samples

    >>> dst = DictStream(traces=traces, key_attr='component')
    >>> dst
    --Stats--
           common_id: BW.RJOB.--.EH?..
       min_starttime: 2009-08-24T00:20:03.000000Z
       max_starttime: 2009-08-24T00:20:03.000000Z
         min_endtime: 2009-08-24T00:20:32.990000Z
         max_endtime: 2009-08-24T00:20:32.990000Z
           processing: []
    -------
    3 MLTrace(s) in DictStream
    Z : BW.RJOB.--.EHZ.. | 2009-08-24T00:20:03.000000Z - 2009-08-24T00:20:32.990000Z | 100.0 Hz, 3000 samples
    N : BW.RJOB.--.EHN.. | 2009-08-24T00:20:03.000000Z - 2009-08-24T00:20:32.990000Z | 100.0 Hz, 3000 samples
    E : BW.RJOB.--.EHE.. | 2009-08-24T00:20:03.000000Z - 2009-08-24T00:20:32.990000Z | 100.0 Hz, 3000 samples

    
    .. rubric:: Supported Operations
    ``DictStream = DictStreamA + DictStreamB``
        Merges all mltraces within the two DictStream objects
        see: :meth:`DictStream.__add__`
    
    ``DictStreamA += DictStreamB
        Extends the DictStream object ``DictStreamA`` with all traces from ``DictStreamB``.
        see: :meth:`DictStream.__iadd__`
    
    ``str(DictStream)``
        Containts the 
    
    NOTE: 
    Not all inherited methods from ObsPy :class:`~obspy.core.stream.Stream` are gauranteed to supported. 
    
    Please submit a bug report if you find one that you'd like to use that hasn't been supported!
    """
    _max_processing_info = 100
    def __init__(self, traces=[], header={}, key_attr='id', **options):
        # initialize as empty stream
        super().__init__()
        # Create logger
        self.logger = logging.getLogger(__name__)

        # Create stats attribute with DictStreamStats
        self.stats = DictStreamStats(header=header)
        # Redefine self.traces as dict
        self.traces = {}
        self._attr_keys = ['id', 'site','inst','instrument','mod','component']
        if key_attr in self._attr_keys:
            self.default_key_attr = key_attr
        else:
            raise ValueError
        
        self.__iadd__(traces, key_attr=self.default_key_attr, **options)
        self.stats.common_id = self.get_common_id()

    #####################################################################
    # MAGIC METHOD UPDATES ##############################################
    #####################################################################
            
    def __iter__(self):
        """
        Return a robust iterator for DictStream.traces.values()
        :returns: (*list*) -- list of values in DictStream.traces.values
        """
        return list(self.traces.values()).__iter__()
    
    def __getitem__(self, index):
        """
        Fusion between the __getitem__ method for lists and dictionaries.

        This accepts integer and slice indexing to access items in DictStream.traces, as well as str-type key values. 

        __getitem__ calls that retrieve a single trace return a MLTrace-like object whereas calls that retrieve multiple traces return a DictStream object

        Explainer
        The DictStream class defaults to using trace.id values for keys (which are str-type), so this approach remove the ambiguity in the expected type for self.traces' keys.

        
        :param index: indexing value with behaviors based on index type
        :type index: int, slice, str, list
        
        :returns:
             - for *int* index -- returns the i^{th} trace in list(self.traces.values())
             - for *slice* index -- returns a DictStream with the specified slice from list(self.traces.values()) and associated keys
             - for *str* index -- returns the trace corresponding to self.traces[index]
             - for *list* of *str* -- returns a DictStream containing the traces as specified by a list of trace keys
        """
        # Handle single item fetch
        if isinstance(index, int):
            trace = self.traces[list(self.traces.keys())[index]]
            out = trace
        # Handle slice fetch
        elif isinstance(index, slice):
            keyslice = list(self.traces.keys()).__getitem__(index)
            traces = [self.traces[_k] for _k in keyslice]
            out = self.__class__(traces=traces)
        # Preserve dict.__getitem__ behavior for string arguments
        elif isinstance(index, str):
            if index in self.traces.keys():
                out = self.traces[index]
            else:
                raise KeyError(f'index {index} is not a key in this DictStream\'s traces attribute')
        elif isinstance(index, list):
            if all(isinstance(_e, str) and _e in self.traces.keys() for _e in index):
                traces = [self.traces[_k] for _k in index]
                out = self.__class__(traces=traces)
            else:
                raise KeyError('not all keys in index are str-type and keys in this DictStream\'s traces attribute')
        else:
            raise TypeError('index must be type int, str, list, or slice')
        return out
    
    def __setitem__(self, index, trace):
        """Provides options to __setitem__ for string and int type indexing consistent with :meth:`~PULSE.data.dictstream.DictStream.__getitem__` behaviors.

        :param index: index to assign trace object to, either a string-type key value or int-type index value
        :type index: int or str
        :param trace: Trace-like object to add, will be converted into a :class:`~PULSE.data.mltrace.MLTrace` object if a :class:`~obspy.core.trace.Trace` is provided
        :type trace: obspy.core.trace.Trace
        """
        if not isinstance(trace, Trace):
            raise TypeError(f'input object trace must be type obspy.core.trace.Trace or child. Not {type(trace)}')
        elif not isinstance(trace, MLTrace):
            trace = MLTrace(trace)
        elif isinstance(trace, MLTrace):
            pass
        else:
            raise TypeError('Shouldn\'t have gotten here...')
                
        if isinstance(index, int):
            key = list(self.traces.keys())[index]
        elif isinstance(index, str):
            key = index
        else:
            raise TypeError(f'index type {type(index)} not supported. Only int and str')
        self.traces.update({key: trace})

    def __delitem__(self, index):
        """Provides options to __delitem__ for string and int type indexing consistent with :meth:`~PULSE.data.dictstream.DictStream.__getitem__` behaviors

        :param index: _description_
        :type index: _type_
        :raises TypeError: _description_
        :return: _description_
        :rtype: _type_
        """        
        if isinstance(index, str):
            key = index
        elif isinstance(index, int):
            key = list(self.traces.keys())[index]
        else:
            raise TypeError(f'index type {type(index)} not supported. Only int and str')   
        return self.traces.__delitem__(key)


    def __getslice__(self, i, j, k=1):
        """
        Updated __getslice__ that leverages the :meth:`~PULSE.data.dictstream.DictStream.__getitem__` for retrieving integer-indexed slices of DictStream.traces values. 

        :param i: leading index value, must be non-negative
        :type i: int
        :param j: trailing index value, must be non-negative
        :type j: int
        :param k: index increment, defaults to 1
        :type k: int, optional

        :return: view of this DictStream
        :type: PULSE.data.dictstream.DictStream
        """
        return self.__class__(traces=self[max(0,i):max(0,j):k])

    def __add__(self, other, **options):
        """Add the contents of this DictStream object and another iterable set of ObsPy :class:`~obspy.core.trace.Trace` objects into a list and initialize a new :class:`~PULSE.data.dictstream.DictStream` object.

        :param other: ObsPy Trace (or child-class) object or iterable comprising several Traces
        :type other: obspy.core.trace.Trace, or list-like thereof
        :param **options: key-word argument gatherer that passes to DictStream.__init__
        :type **options: kwargs
            # NOTE: If key_attr is not specified in **options, 
            #     the new DictStream uses key_attr = self.default_key_attr
        :raises TypeError: If other's type does not comply
        :return: new DictStream object containing traces from self and other
        :rtype: PULSE.data.dictstream.DictStream
        """
        if isinstance(other, Trace):
            other = [other]
        if not all(isinstance(tr, Trace) for tr in other):
            raise TypeError
        traces = [tr for tr in self.traces] + other
        if 'key_attr' not in options.keys():
            options.upate({'key_attr': self.default_key_attr}) 
        return self.__class__(traces=traces, **options)

    def __iadd__(self, other, **options):
        """
        Alias for the DictStream.extend() method to allow
        use of the += operator

        """
        self.extend(other, **options) 
        return self           

    def extend(self, other, key_attr=None, **options):
        """
        Wrapper method for the _add_trace() method that
        allows input of single or sets of Trace-type objects
        to append to this DictStream with a specified key_attribute
        """
        if key_attr is None:
            key_attr = self.default_key_attr
        elif key_attr not in self._attr_keys:
            raise ValueError

        if isinstance(other, Trace):
            self._add_trace(other, key_attr=key_attr, **options)
        elif isinstance(other, Stream):
            self._add_stream(other, key_attr=key_attr, **options)
        elif isinstance(other, (list, tuple)):
            if all(isinstance(_tr, Trace) for _tr in other):
                self._add_stream(other, key_attr=key_attr, **options)
            else:
                raise TypeError('other elements are not all Trace-like types')
        else:
            raise TypeError(f'other type "{type(other)}" not supported.')

    def _add_trace(self, other, key_attr=None, **options):
        """
        Add a trace-like object `other` to this DictStream using elements from
        the trace's id as the dictionary key in the DictStream.traces dictionary

        :: INPUTS ::
        :param other: ObsPy Trace-like object to add
        :type: other: obspy.core.trace.Trace-like
        :param key_attr: name of the attribute to use as a key, default is None
                        Supercedes the default value set in DictStream.__init__()
                        Supported Values:
                            'id' - full N.S.L.C(.M.W) code
                            'site' - Net + Station
                            'inst' - Location + Band & Instrument codes from Channel
                            'instrument'- 'site' + 'inst'
                            'mod' - Model + Weight codes
                            'component' - component code from Channel
        :type key_attr: str, optional
        :param **options:key-word argument gatherer to pass to the 
                        MLTrace.__add__() or MLTraceBuffer.__add__() method
        :type **options: kwargs
        """
        if key_attr is None:
            key_attr = self.default_key_attr
        elif key_attr not in self._attr_keys:
            raise ValueError
        
        # If potentially appending a wave
        if isinstance(other, dict):
            try:
                other = wave2mltrace(other)
            except SyntaxError:
                pass
        # If appending a trace-type object
        elif isinstance(other, Trace):
            # If it isn't an MLTrace, __init__ one from data & header
            if not isinstance(other, MLTrace):
                other = MLTrace(data=other.data, header=other.stats)
            else:
                pass
        # Otherwise
        else:
            raise TypeError(f'other {type(other)} not supported.')
        
        if isinstance(other, MLTrace):
            # Get id of MLTrace "other"
            key_opts = other.key_opts
            # If id is not in traces.keys() - use dict.update
            key = key_opts[key_attr]
            # If new key
            if key not in self.traces.keys():
                self.traces.update({key: other})
            # If key is in traces.keys() - use __add__
            else:
                self.traces[key].__add__(other, **options)
            self.stats.update_time_range(other)
            self.stats.common_id = self.get_common_id()

    def _add_stream(self, stream, **options):
        """
        Supporting method to iterate across a stream-like object
        and apply the _add_trace() DictStream class method

        :: INPUTS ::
        :param stream: iterable object containing obspy Trace-like objects
        :type stream: obspy.core.stream.Stream or other list-like of obspy.core.trace.Trace-like objects
        :param **options: optional key-word argument gatherer
                        to pass kwargs to the DictStream._add_trace method
        :type **options: kwargs, optional
        """
        for _tr in stream:
            self._add_trace(_tr, **options)

    def __str__(self):
        """string representation of the full module/class path of
        :class:`~PULSE.data.dictstream.DictStream`

        :return rstr: representative string
        :rtype rstr: str
        """
        rstr = 'PULSE.data.dictstream.DictStream'
        return rstr

    def __repr__(self, extended=False):
        """string representation of the contents of this PULSE.data.dictstream.DictStream` object
        Always shows the representation of the DictStream.stats object,
        Truncates the representation of Trace-like objects in the DictStream
        if there are more than 20 Trace-like objects.

        :param extended: print full list of Trace-likes?, defaults to False
        :type extended: bool, optional
        :return rstr: representative string
        :rtype rstr: str

        ..rubric:: Use

        >> dst = DictStream(read('example_file.mseed'))
        >> print(dst.__repr__(extended=True))
        >> print(dst.__repr__(extended=False))
        

        """        
        rstr = f'--Stats--\n{self.stats.__str__()}\n-------'
        if len(self.traces) > 0:
            id_length = max(len(_tr.id) for _tr in self.traces.values())
        else:
            id_length=0
        if len(self.traces) > 0:
            rstr += f'\n{len(self.traces)} {type(self[0]).__name__}(s) in {type(self).__name__}\n'
        else:
            rstr += f'\nNothing in {type(self).__name__}\n'
        if len(self.traces) <= 20 or extended is True:
            for _l, _tr in self.traces.items():
                rstr += f'{_l:} : {_tr.__str__(id_length)}\n'
        else:
            _l0, _tr0 = list(self.traces.items())[0]
            _lf, _trf = list(self.traces.items())[-1]
            rstr += f'{_l0:} : {_tr0.__repr__(id_length=id_length)}\n'
            rstr += f'...\n({len(self.traces) - 2} other traces)\n...\n'
            rstr += f'{_lf:} : {_trf.__repr__(id_length=id_length)}\n'
            rstr += f'[Use "print({type(self).__name__}.__repr__(extended=True))" to print all labels and MLTraces]'
        return rstr
    

    #####################################################################
    # SEARCH METHODS ####################################################
    #####################################################################
    
    def fnselect(self, fnstr, key_attr=None, ascopy=False):
        """
        Find DictStream.traces.keys() strings that match the
        input `fnstr` string using the fnmatch.filter() method
        and compose a view (or copy) of the subset DictStream

        :: INPUTS ::
        :param fnstr: Unix wildcard compliant string to use for searching for matching keys
        :type fnstr: str
        :param key_attr: key attribute for indexing the view/copy
                            of the source DictStream (see DictStream.__init__)
                         None defaults to the self.default_key_attr attribute
                            value of the source DictStream object
        :type key_attr: str or None, optional
        :param ascopy: should the returned DictStream be...
                Default (False) a view (i.e., accessing the same memory blocks)
                        (True) or a copy of the traces contained within?
        :type ascopy: bool, optional
        :return out: DictStream containing subset traces that match the specified `fnstr`
        :rtype out: PULSE.data.dictstream.DictStream
        """
        matches = fnmatch.filter(self.traces.keys(), fnstr)
        out = self.__class__(header=self.stats.copy(), key_attr = self.default_key_attr)
        for _m in matches:
            if ascopy:
                _tr = self.traces[_m].copy()
            else:
                _tr = self.traces[_m]
            out.extend(_tr, key_attr=key_attr)
        out.stats.common_id = out.get_common_id()
        return out
    
    def fnpop(self, fnstr, key_attr=None):
        """Use a fnmatch.filter() search for keys that match the provided
        fn string and pop them off this DictStream-like object into a new 
        DictStream-like object

        :param fnstr: unix wildcard compliant string for matching to keys that will be popped off this DictStream object
        :type fnstr: str
        :param key_attr: alternative key attribute to use for the output DictStream object, defaults to None
        :type key_attr: NoneType or str, optional
        :return out: popped items hosted in a new DictStream-like object
        :rtype: PULSE.data.dictstream.DictStream-like
        """        
        matches = fnmatch.filter(self.traces.keys(), fnstr)
        out = self.__class__(header=self.stats.copy(), key_attr=self.default_key_attr)
        for _m in matches:
            out.extend(self.pop(_m), key_attr = key_attr)
        out.stats.common_id = out.get_common_id()
        return out
            
    
    def isin(self, iterable, key_attr=None, ascopy=False):
        """
        Return a subset view (or copy) of the contents of this
        DictStream with keys that conform to an iterable set
        of strings.

        Generally based on the behavior of the pandas.series.Series.isin() method

        :: INPUTS ::
        :param iterable: [list-like] of [str] - strings to match
                            NOTE: can accept wild-card strings 
                                (also see DictStream.fnselect)
        :param key_attr: [str] - key attribute for indexing this view/copy
                        of the source DictStream (see DictStream.__init__)
                         [None] - defaults to the .default_key_attr attribute
                         value of the source DictStream object
        :param ascopy: [bool] return as an independent copy of the subset?
                        default - False
                            NOTE: this creates a view that can
                            alter the source DictStream's contents
        :: OUTPUT ::
        :return out: [PULSE.data.dictstream.DictStream] subset view/copy
        """
        out = self.__class__(header=self.stats.copy(), key_attr = self.default_key_attr)
        matches = []
        for _e in iterable:
            matches += fnmatch.filter(self.traces.keys(), _e)
        for _m in matches:
            if ascopy:
                _tr = self.traces[_m].copy()
            else:
                _tr = self.traces[_m]
            out.extend(_tr, key_attr=key_attr)
        out.stats.common_id = out.get_common_id()
        return out

    def exclude(self, iterable, key_attr=None, ascopy=False):
        out = self.__class__(header=self.stats.copy(), key_attr = self.default_key_attr)
        matches = []
        for _e in iterable:
            matches += fnmatch.filter(self.traces.keys(), _e)
        for _k in self.traces.keys():
            if _k not in matches:
                if ascopy:
                    _tr = self.traces[_k].copy()
                else:
                    _tr = self.traces[_k]
                out.extend(_tr, key_attr=key_attr)
        out.stats.common_id = out.get_common_id()
        return out


    def get_unique_id_elements(self):
        """
        Compose a dictionary containing lists of
        unique id elements: Network, Station, Location,
        Channel, Model, Weight in this DictStream

        :: OUTPUT ::
        :return out: [dict] output dictionary keyed
                by the above elements and valued
                as lists of strings
        """
        N, S, L, C, M, W = [], [], [], [], [], []
        for _tr in self:
            hdr = _tr.stats
            if hdr.network not in N:
                N.append(hdr.network)
            if hdr.station not in S:
                S.append(hdr.station)
            if hdr.location not in L:
                L.append(hdr.location)
            if hdr.channel not in C:
                C.append(hdr.channel)
            if hdr.model not in M:
                M.append(hdr.model)
            if hdr.weight not in W:
                W.append(hdr.weight)
        out = dict(zip(['network','station','location','channel','model','weight'],
                       [N, S, L, C, M, W]))
        return out
    
    def get_common_id_elements(self):
        """
        Return a dictionary of strings that are 
        UNIX wild-card representations of a common
        id for all traces in this DictStream. I.e.,
            ? = single character wildcard
            * = unbounded character count widlcard

        :: OUTPUT ::
        :return out: [dict] dictionary of elements keyed
                    with the ID element name
        """
        ele = self.get_unique_id_elements()
        out = {}
        for _k, _v in ele.items():
            if len(_v) == 0:
                out.update({_k:'*'})
            elif len(_v) == 1:
                out.update({_k: _v[0]})
            else:
                minlen = 999
                maxlen = 0
                for _ve in _v:
                    if len(_ve) < minlen:
                        minlen = len(_ve)
                    if len(_ve) > maxlen:
                        maxlen = len(_ve)
                _cs = []
                for _i in range(minlen):
                    _cc = _v[0][_i]
                    for _ve in _v:
                        if _ve[_i] == _cc:
                            pass
                        else:
                            _cc = '?'
                            break
                    _cs.append(_cc)
                if all(_c == '?' for _c in _cs):
                    _cs = '*'
                else:
                    if minlen != maxlen:
                        _cs.append('*')
                    _cs = ''.join(_cs)
                out.update({_k: _cs})
        return out

    def get_common_id(self):
        """
        Get the UNIX wildcard formatted common common_id string
        for all traces in this DictStream

        :: OUTPUT ::
        :return out: [str] output stream
        """
        ele = self.get_common_id_elements()
        out = '.'.join(ele.values())
        return out

    def update_stats_timing(self):
        for tr in self:
            self.stats.update_time_range(tr)
        return None                
    
    def split_on_key(self, key='instrument', **options):
        """
        Split this DictStream into a dictionary of DictStream
        objects based on a given element or elements of the
        constituient traces' ids.

        :: INPUTS ::
        :param key: [str] name of the attribute to split on
                    Supported:
                        'id', 'site','inst','instrument','mod','component',
                        'network','station','location','channel','model','weight'
        :param **options: [kwargs] key word argument gatherer to pass
                        kwargs to DictStream.__add__()
        :: OUTPUT ::
        :return out: [dict] of [DictStream] objects
        """
        if key not in MLTrace().key_opts.keys():
            raise ValueError(f'key {key} not supported.')
        out = {}
        for _tr in self:
            key_opts = _tr.key_opts
            _k = key_opts[key]
            if _k not in out.keys():
                out.update({_k: self.__class__(traces=_tr)})
            else:
                out[_k].__add__(_tr, **options)
        return out
    

    #####################################################################
    # UPDATED METHODS FROM OBSPY STREAM #######################################
    #####################################################################
    # @_add_processing_info
    def trim(self,
             starttime=None,
             endtime=None,
             pad=True,
             keep_empty_traces=True,
             nearest_sample=True,
             fill_value=None):
        """
        Slight adaptation of :meth: `~obspy.core.stream.Stream.trim` to accommodate to facilitate the dict-type self.traces
        attribute syntax.

        see obspy.core.stream.Stream.trim() for full explanation of the arguments and behaviors
        
        :: INPUTS ::
        :param starttime: [obspy.core.utcdatetime.UTCDateTime] or [None]
                        starttime for trim on all traces in DictStream
        :param endtime: [obspy.core.utcdatetime.UTCDateTime] or [None]
                        endtime for trim on all traces in DictStream
        :param pad: [bool]
                        should trim times outside bounds of traces
                        produce masked (and 0-valued fold) samples?
                        NOTE: In this implementation pad=True as default
        :param keep_empty_traces: [bool]
                        should empty traces be kept?
        :param nearest_sample: [bool]
                        should trim be set to the closest sample(s) to 
                        starttime/endtime?
        :param fill_value: [int], [float], or [None]
                        fill_value for gaps - None results in masked
                        data and 0-valued fold samples in gaps

        """
        if not self:
            return self
        # select start/end time fitting to a sample point of the first trace
        if nearest_sample:
            tr = self[0]
            try:
                if starttime is not None:
                    delta = compatibility.round_away(
                        (starttime - tr.stats.starttime) *
                        tr.stats.sampling_rate)
                    starttime = tr.stats.starttime + delta * tr.stats.delta
                if endtime is not None:
                    delta = compatibility.round_away(
                        (endtime - tr.stats.endtime) * tr.stats.sampling_rate)
                    # delta is negative!
                    endtime = tr.stats.endtime + delta * tr.stats.delta
            except TypeError:
                msg = ('starttime and endtime must be UTCDateTime objects '
                       'or None for this call to Stream.trim()')
                raise TypeError(msg)
        for trace in self:
            trace.trim(starttime, endtime, pad=pad,
                       nearest_sample=nearest_sample, fill_value=fill_value)
            self.stats.update_time_range(trace)
        if not keep_empty_traces:
            # remove empty traces after trimming
            self.traces = {_k: _v for _k, _v in self.traces.items() if _v.stats.npts}
            self.stats.update_time_range(trace)
        self.stats.common_id = self.get_common_id()
        return self
    
    # 
    def normalize_traces(self, norm_type ='peak'):
        """Normalize traces in this :class:`~PULSE.data.dictstream.DictStream`, using :meth:`~PULSE.data.mltrace.MLTrace.normalize` on each trace

        :param norm_type: normalization method, defaults to 'peak'
        :type norm_type: str, optional
            Supported values: 'peak', 'std'
        """        
        for tr in self:
            tr.normalize(norm_type=norm_type)
    
    #####################################################################
    # I/O METHODS #######################################################
    #####################################################################


    # TODO: Determine if this method is sufficient for development purposes
    def write(self, base_path='.', path_structure='mltraces', name_structure='{wfid}_{iso_start}', **options):
        """
        Write a DictStream object to disk as a series of MSEED files using the MLTrace.write() method/file formatting
        in a prescribed directory structure

        :: INPUTS ::
        :param base_path: [str] path to the directory that will contain the save file structure. If it does
                    not exist, a directory (structure) will be created
        :type base_path: str
        :param path_structure: [None] - no intermediate path structure
                                [str] - format string based on the metadata of individual MLTrace objects contained
                                        in this DictStream. In addition to standard kwargs in the MLTrace.stats
                                        that can be used as elements of this format string, additional options are
                                        provided for datetime information:
                                            epoch_start - starttimes converted into a timestamp
                                            epoch_end - endtimes converted into timestamps
                                            iso_start - starttimes converted into isoformat strings
                                            iso_ends - endtimes converted into isoformat strings
                                            wfid - waveform ID (Net.Sta.Loc.Chan.Mod.Wgt)
                                            site - Net.Sta code string
                                            inst - Loc.Chan (minus the component character) code string
                                            mod - Mod.Wgt code string
                                            instrument - site.inst (as defined above) code string
        :type path_structure: str or NoneType
                                        
        :param name_structure: [str] - format string with the opions as described for path_structure
        :param **options: [kwargs] optional key word argument collector for 

        :ATTRIBUTION: Based on path sturcturing and syntax from the ObsPlus WaveBank class
        
        """
        # # Ensure OS-appropriate path formatting
        # base_parts = os.path.split(base_path)
        # base_path = os.path.join(base_parts)

        # Get elements of the save directory structure as an OS-agnostic list of directory names
        if path_structure is None:
            path_parts = [base_path]
        else:
            path_parts = [base_path] + path_structure.split('/')
        # Iterate across traces in this DictStream
        for tr in self.traces.values():
            # Ge the formatting dictionary 
            fmt_dict = {'wfid': tr.id,
                        'epoch_start': tr.stats.starttime.timestamp,
                        'iso_start': tr.stats.starttime.isoformat(),
                        'epoch_end': tr.stats.endtime.timestamp,
                        'iso_end': tr.stats.endtime.isoformat()}
            fmt_dict.update(tr.stats)
            if isinstance(tr, MLTrace):
                fmt_dict.update({'component': tr.comp,
                                 'site': tr.site,
                                 'inst': tr.inst,
                                 'mod': tr.mod,
                                 'instrument': tr.instrument})

            save_path = os.path.join(*path_parts).format(**fmt_dict)
            save_name = f'{name_structure.format(**fmt_dict)}.mseed'
            file_name = os.path.join(save_path, save_name)
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            tr.write(file_name=file_name, **options)

    def read(mltrace_mseed_files):
        """
        Read a list-like set of file names for mseed files created by a
        MLTrace.write() call (i.e., MSEED files containing a data and fold trace)

        also see :meth:`~PULSE.data.mltrace.MLTrace.write`
                 :meth:`~PULSE.data.mltrace.MLTrace.read`
        """
        if isinstance(mltrace_mseed_files, str):
            mltrace_mseed_files = [mltrace_mseed_files]
        dst = DictStream()
        for file in mltrace_mseed_files:
            if not os.path.isfile(file):
                raise FileExistsError(f'file {file} does not exist')
            else:
                mltr = MLTrace.read(file)
            dst.extend(mltr)
        return dst


    


    #######################
    # VISUALIZATION TOOLS #  
    #######################
    # TODO: Determine if this section should be migrated to a visualization submodule
    def _to_vis_stream(self, fold_threshold=0, normalize_src_traces=True, attach_mod_to_loc=True):
        """PRIVATE METHOD - prepare a copy of the traces in this DictStream for visualization

        :param fold_threshold: _description_, defaults to 0
        :type fold_threshold: int, optional
        :param normalize_src_traces: _description_, defaults to True
        :type normalize_src_traces: bool, optional
        :param attach_mod_to_loc: _description_, defaults to True
        :type attach_mod_to_loc: bool, optional
        :return: _description_
        :rtype: _type_
        """        
        st = obspy.Stream()
        for mltr in self:
            tr = mltr.copy()
            if normalize_src_traces:
                if mltr.stats.weight == mltr.stats.defaults['weight']:
                    tr = tr.normalize(norm_type='max')
            st += tr.to_trace(fold_threshold=fold_threshold,
                              attach_mod_to_loc=attach_mod_to_loc)
        return st
    
    def plot(self, fold_threshold=0, attach_mod_to_loc=True, normalize_src_traces=False, **kwargs):
        """Plot the contents of this DictStream using the obspy.core.stream.Stream.plot backend
        
        """
        st = self._to_vis_stream(fold_threshold=fold_threshold,
                                 normalize_src_traces=normalize_src_traces,
                                 attach_mod_to_loc=attach_mod_to_loc)
        outs = st.plot(**kwargs)
        return outs
    
    def snuffle(self, fold_threshold=0, attach_mod_to_loc=True, normalize_src_traces=True,**kwargs):
        """Launch a snuffler instance on the contents of this DictStream

        NOTE: Imports from Pyrocko and runs :meth:`~pyrocko.obspy_compat.plant()`

        :param fold_threshold: fold_threshold for "valid" data (invalid data are masked), defaults to 0
        :type fold_threshold: float, optional
        :param attach_mod_to_loc: should model and weight names be appended to the trace's location string, defaults to True
        :type attach_mod_to_loc: bool, optional
        :param normalize_src_traces: normalized traces for traces that have default weight codes, defaults to True
        :type normalize_src_traces: bool, optional
        :return: standard output from :meth: `obspy.core.stream.Stream.snuffle` which is added to Stream
            via :class: `pyrocko.obspy_compat`
        :rtype: tuple
        """        
        if 'obspy_compat' not in dir():
            from pyrocko import obspy_compat
            obspy_compat.plant()
        st = self._to_vis_stream(fold_threshold=fold_threshold,
                                 normalize_src_traces=normalize_src_traces,
                                 attach_mod_to_loc=attach_mod_to_loc)
        outs = st.snuffle(**kwargs)
        return outs
                    
    

    ####################
    # Group Triggering #
    ####################
    # TODO: Determine if this should be migrated into a method associated with triggering
    def prediction_trigger_report(self, thresh, exclude_list=None, **kwargs):
        """Wrapper around the :meth:`~PULSE.data.mltrace.MLTrace.prediction_trigger_report`
        method. This method executes the Trace-level method on each trace it contains using
        shared inputs

        :TODO: Update to the `notin` method (develop notin from the code in here)

        :param thresh: trigger threshold value
        :type thresh: float
        :param exclude_list: :meth: `~PULSE.data.dictstream.DictStream.notin` compliant strings
                        to exclude from trigger processing, defaults to None
        :type exclude_list: list of str, optional
        :param **kwargs: gatherer for key word arguments to pass to :meth: `~PULSE.data.mltrace.MLTrace.prediction_trigger_report`
        :type **kwargs: key word arguments, optional
        :return df_out: trigger report
        :rtype df_out: pandas.core.dataframeDataFrame
        """        
        df_out = pd.DataFrame()
        if 'include_processing_info' in kwargs.keys():
            include_proc = kwargs['include_processing_info']
        else:
            include_proc = False
        if include_proc:
            df_proc = pd.DataFrame()
        if exclude_list is not None:
            if isinstance(exclude_list, list) and all(isinstance(_e, str) for _e in exclude_list):
                view = self.exclude(exclude_list)
            else:
                raise TypeError('exclude_list must be a list of strings or NoneType')
        else:
            view = self
        for tr in view.traces.values():
            out = tr.prediction_trigger_report(thresh, **kwargs)
            # Parse output depening on output type
            if not include_proc and out is not None:
                idf_out = out
            elif include_proc and out is not None:
                idf_out = out[0]
                idf_proc = out[1]
            # Concatenate outputs
            if out is not None:
                df_out = pd.concat([df_out, idf_out], axis=0, ignore_index=True)
                if include_proc:
                    df_proc = pd.concat([df_proc, idf_proc], axis=0, ignore_index=True)
            else:
                continue
        if len(df_out) > 0:
            if include_proc:
                return df_out, df_proc
            else:
                return df_out
        else:
            return None


# TODO: Determine if this method should be removed
# def read_mltraces(data_files, obspy_read_kwargs={}, add_options={}):
#     """
#     Wrapper around :meth:`~PULS# .data.mltrace.MLTrace.read_mltrace`
#     to reconstitute multiple MLTrace objects from the _DATA, _FOLD, _PROC
#     files generated by the MLTrace.write() method and populate a DictStream
#     object. 

#     :: INPUTS ::
#     :param data_files: [str] file name of a 
#                     file that contains MLTrace data and header information
#                        [list] list of valid data_file name strings
#                     also see PULS# .data.mltrace.read_mltrace()
#     :obspy_read_kwargs: [dict] dictionar of keyword arguments to pass to
#                     obspy.core.stream.read()
#     :add_options: [dict] dictionary of keyword arguments to pass to
#                     PULS# .data.dictstream.DictStream.__add__

#     :: OUTPUT ::
#     :return dst: [PULS# .data.dictstream.DictStream] assembled DictStream object
    
#     {common_name}_DATA.{extension} 
#     """
#     if isinstance(data_files, str):
#         data_files = [data_files]
#     elif not isinstance(data_files, list):
#         raise TypeError
#     else:
#         if not all(isinstance(_e, str) for _e in data_files):
#             raise TypeError
    
#     dst = DictStream()
#     for df in data_files:
#         mlt = read_mltrace(df, **obspy_read_kwargs)
#         dst.__add__(mlt, **add_options)
#     return dst
        

# TODO: Determine if this class method should be removed
# def write_to_mseed(
#         self,
#         savepath='.',
#         save_fold=True,
#         fmt_str='{ID}_{t0:.3f}_{t1:.3f}_{sampling_rate:.3f}sps',
#         save_processing=True,
#         save_empty=False,
#         **kwargs):
#     split_outs = {}
#     for _mlt in self.traces.items():
#         if not save_empty and _mlt.stats.npts == 0:
#             continue
#         else:
#             out = _mlt.write_to_tiered_directory(
#                 savepath=savepath,
#                 save_fold=save_fold,
#                 save_processing=save_processing,
#                 fmt_str = fmt_str,
#                 **kwargs)
#             split_outs.update({_mlt.id: out})
#     return split_outs

# TODO: Determine if this class method should be removed
# def write(
#         self,
#         save_path='.',
#         fmt='sac',
#         save_fold=True,
#         save_processing=True,
#         filename_format='{ID}_{starttime}_{sampling_rate:.3f}sps',
#         **obspy_write_options):
#     """
#     Wrapper around the PULSE# .data.mltrace.MLTrace.write() method
#     that saves data as 
    
#     """
#     for _mlt in self.traces.values():
#         _mlt.write(save_path=save_path,
#                    fmt=fmt,
#                    save_fold=save_fold,
#                    save_processing=save_processing,
#                    filename_format=filename_format,
#                    **obspy_write_options)