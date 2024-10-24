"""
:module: PULSE.data.window
:auth: Nathan T. Stevens
:email: ntsteven (at) uw.edu
:org: Pacific Northwest Seismic Network
:license: AGPL-3.0

.. rubric:: Purpose
This module provides the class definitions for :class:`~PULSE.data.window.Window` and :class:`~PULSE.data.window.WindowStats`
that are child classes of :class:`~PULSE.data.dictstream.DictStream` and :class:`~PULSE.data.dictstream.DictStreamStats`, respectively.

The Window class keys :class:`~PULSE.data.mltrace.MLTrace`-type objects by their component code, rather than full **id** attribute
and provides additional class methods for pre-processing one or more MLTrace objects into a data tensor ready for input to a machine
learning model (i.e., those derived from :class:`~seisbench.models.WaveformModel`.
"""
import logging, os, sys, warnings
import numpy as np
import pandas as pd
import seisbench.models as sbm
from obspy import Trace, Stream
from PULSE.data.dictstream import DictStream
from PULSE.data.mltrace import MLTrace
from PULSE.data.header import WindowStats
    
###############################################################################
# Window Class Definition ###########################################
###############################################################################

Logger = logging.getLogger(__name__)

class Window(DictStream):
    """A child-class of :class:`~PULSE.data.dictstream.DictStream` that uses trace component codes as
    keys and is intended to faciliate processing of a collection of windowed traces from a single seismometer. 

    :param traces: list of MLTrace-like objects to insert at initialization
    :type traces: list or PULSE.data.mltrace.MLTrace-like
    :param primary_component: component code for the primary trace used in assessing data completeness, defaults to "Z".
    :type primary_component: str, optional
    :param header: non-default values to pass to the :class:`~PULSE.data.header.WindowStats` object on initialization, defaults to {}.
    :type header: dict, optional
    
    **options: collector for key-word arguments passed to :meth:`~PULSE.data.window.Window.__add__` in determining
        how entries in `traces` with matching component codes are merged.
        also see :meth:`~PULSE.data.dictstream.DictStream.__add__`
    """
    def __init__(
            self,
            traces,
            primary_component='Z',
            target_starttime=None,
            target_sampling_rate=None,
            target_window_npts=None,
            header={},
            **options):
        """
        Initialize a PULSE.data.window.Window object

        :param traces: list of MLTrace-like objects to insert at initialization
        :type traces: list or PULSE.data.mltrace.MLTrace-like
        :param primary_component: reference component code, used in assessing data completeness, defaults to "Z".
        :type primary_component: str, optional
        :param header: non-default values to pass to the header of this Window object, defaults to {}.
        :type header: dict, optional
        
        **options: collector for key-word arguments passed to :meth:`~PULSE.data.window.Window.__add__` in determining
            how entries in `traces` with matching component codes are merged.
            also see :meth:`~PULSE.data.dictstream.DictStream.__add__`
        """
        # Initialize & inherit from DictStream as an empty dictstream using 'comp' key attributes
        super().__init__(key_attr='comp')
        header.update({'primary_component': primary_component,
                       'target_starttime': target_starttime,
                       'target_sampling_rate': target_sampling_rate,
                       'target_window_npts': target_window_npts})
        # Initialize WindowStats Header & use this to compatability check other components
        self.stats = WindowStats(header=header)

        # Add traces - safety checks for repeat components handled in extend()
        self.extend(traces, **options)
        # Update common_id -- TODO: may want to shift this to a DictStreamStats method?
        self.stats.common_id = self.get_common_id()

        # Primary component present check
        if self.stats.primary_component not in self.traces.keys():
            raise ValueError(f'No traces in this Window have the primary_component code {self.stats.primary_component}.')
        

    def get_primary(self):
        return self[self.stats.primary_component]
    
    primary = property(get_primary)


    # def __repr__(self, extended=False):
    #     """
    #     Provide a user-friendly string representation of the contents and key parameters of this
    #     Window object. 

    #     :param extended: option to show an extended form of the Window should 
    #                      there be a large number of unique component codes (an uncommon use case)
    #     :type extend: bool, optional

    #     :return rstr: representative string
    #     :rtype rstr: str
    #     """
    #     rstr = self.stats.__str__()
    #     if len(self.traces) > 0:
    #         id_length = max(len(_tr.id) for _tr in self.traces.values())
    #     else:
    #         id_length=0
    #     if len(self.traces) > 0:
    #         rstr += f'\n{len(self.traces)} {type(self[0]).__name__}(s) in {type(self).__name__}\n'
    #     else:
    #         rstr += f'\nNothing in {type(self).__name__}\n'
    #     if len(self.traces) <= 20 or extended is True:
    #         for _l, _tr in self.traces.items():
    #             rstr += f'{_l:} : {_tr.__str__(id_length)}\n'
    #     else:
    #         _l0, _tr0 = list(self.traces.items())[0]
    #         _lf, _trf = list(self.traces.items())[-1]
    #         rstr += f'{_l0:} : {_tr0.__repr__(id_length=id_length)}\n'
    #         rstr += f'...\n({len(self.traces) - 2} other traces)\n...\n'
    #         rstr += f'{_lf:} : {_trf.__repr__(id_length=id_length)}\n'
    #         rstr += f'[Use "print({type(self).__name__}.__repr__(extended=True))" to print all labels and MLTraces]'
    #     return rstr

    

    ###############################################################################
    # METADATA CHECKING METHODS ###################################################
    ###############################################################################

    def check_fvalid(self, key, tolerance=1e-3):
        """Check if the fraction of valid data in a given trace meets threshold
        criteria

        :param key: key of the intended trace in **Window.traces**
        :type key: str
        :param tolerance: Small-value tolerance bound to account for machine precision rounding
            or data modifications (e.g., resampling) that might slightly reduce a previously
            passing fvalid trace below the specified threshold in **Window.stats**.
            Must be a value in :math:`\in[0, 1)`, defaults to 1e-3.
        :type tolerance: float, optional
        :return:
         - **passing** (*bool*) -- does this trace pass it's assigned threshold criterion?
        """        
        # Compatability check for tolerance
        if not isinstance(tolerance, float):
            raise TypeError('tolerance must be type float')
        if 0 <= tolerance < 1:
            pass
        else:
            raise ValueError('tolerance must be a value in [0, 1)')
        # Compatability check for key
        if key not in self.traces.keys():
            raise KeyError(f'{key} is not present.')
        else:
            fv = self[key].get_fvalid_subset(starttime=self.stats.target_starttime,
                                             endtime=self.stats.target_endtime,
                                             threshold=self.stats.fold_threshold_level)
        
        if key == self.stats.primary_component:
            if fv >= self.stats.primary_threshold - tolerance:
                passing = True
            else:
                passing = False  
        else:
            if fv >= self.stats.secondary_threshold - tolerance:
                passing = True
            else:
                passing = False
        return passing
    
    def run_fvalid_checks(self, tolerance=1e-3):
        """Run :meth:`~PULSE.data.window.Window.check_fvalid` on all traces
        present in this Window and return a dictionary keyed with component
        codes and valued with True/False indicating if traces pass or fail
        the fvalid threshold check. The primary_component keyed trace has 
        the primary_threshold applied, while all other traces have the secondary_threshold
        applied.

        also see :meth:`~PULSE.data.window.Window.check_fvalid`

        :param tolerance: tolerance level for :meth:`~PULSE.data.window.Window.check_fvalid`, defaults to 1e-3.
        :type tolerance: float, optional
        :return:
         - **results** (*dict*) -- check_fvalid results for each MLTrace in this Window
        """ 
        return {_k: self.check_fvalid(_k, tolerance=tolerance) for _k in self.traces.keys()}

    
    def check_target_attribute(self, key, attr='starttime'):
        """Determine if a given mltrace in this Window object meets the target value
        of a given attribute in **Window.stats**.

        :param key: key from **Window.traces** to test
        :type key: str
        :param attr: name of the mltrace header attribute to check, defaults to 'starttime'.
            Supported values: starttime, endtime, sampling_rate, npts
        :type attr: str, optional
        :return:
         - **result** (*bool*) -- does the value match?
        
        """
        if key not in self.keys():
            raise KeyError(f'key {key} not present')
        else:
            _mltr = self[key]
        if attr.lower() in ['starttime','endtime','sampling_rate','npts']:
            attr = attr.lower()
            tattr = 'target_%s'%(attr)
        else:
            raise ValueError(f'attr value {attr} not supported.')
        result = _mltr.stats[attr] == self.stats[tattr]
        return result

    def check_windowing_status(self, mode='summary'):
        """Check if all traces present in this :class:`~PULSE.data.window.Window` object
        have starttime, sampling_rate, npts, endtime values that match target attribute values
        in its **Window.stats** attribute.

        :param mode: determines how the **output** is formatted, defaults to 'summary'.
            'summary' - a single bool value if all tests pass or not for all channels
            'channel' - a dictionary keyed by mltrace channel codes and valued with a single bool value
                    whether the channel passes all tests.
            'full' - a dictionary keyed by attribute names and valued with dictionaries as
        :type mode: str, optional
        :return:
         - **output** (*dict* or *bool*) - output as determined by specified **mode** selection.
        """        
        results = {}
        for key in self.keys():
            results.update({key: {}})
            for attr in ['starttime','sampling_rate','npts','endtime']:
                result = self.check_target_attribute(key, attr=attr)
                results[key].update({attr: result})
        
        if mode.lower() == 'summary':
            output = all(all(_v2 for _v2 in _v1.values()) for _v1 in results.values())
        elif mode.lower() == 'channel':
            output = {key: all(result[key].values()) for key in results.keys()}
        elif mode.lower() == 'full':
            output = results
        else:
            raise ValueError(f'mode {mode} not supported.')

        return output

    def check_tensor_readiness(self, target_ntraces=3, mode='summary'):
        report = {'ntraces': len(self) == target_ntraces,
                  'attr': self.check_windowing_status(mode=mode)}
        if mode.lower() == 'summary':
            output = all(report.values())
        
    ##################################
    # SECONDARY COMPONENT METHODS ####
    ##################################

    def set_secondary_components(self, secondary_components='NE'):
        # Compatability check for secondary_components
        if not isinstance(secondary_components, str):
            raise TypeError('secondary_components must be type str.')
        elif len(secondary_components) != 2:
            raise ValueError('Must provide 2 secondary_components. E.g., "12", "NE".')
        elif secondary_components[0] == secondary_components[1]:
            raise ValueError('Elements of secondary_components must be unique characters')
        else:
            component_list = secondary_components + self.stats.primary_component
        # Set component_list
        self.stats.secondary_components = secondary_components
        # De-index any non-listed traces
        popped_traces = []
        for _k in self.traces.keys():
            if _k not in component_list:
                popped_traces.append(self.traces.pop(_k))
        
        return popped_traces

    ##########################
    # PREPROCESSING METHODS ##
    ##########################

    def align_to_targets(self, fill_value=0, window='hann', **kwargs):
        """Wrapper for the :meth:`~PULSE.data.mltrace.MLTrace.treat_gaps` and
        :meth:`~PULSE.data.mltrace.MLTrace.align_sampling` methods, which are
        which is applied to all traces in this Window using target attribute values 
        (starttime, npts, sampling_rate) as inputs. 


        :param fill_value: fill_value used by subroutine calls of :meth:`~PULSE.data.mltrace.MLTrace.trim`,
            defaults to 0
        :type fill_value: int, float, or None, optional
        :param window: name of the windowing method to use in subroutine calls of :meth:`~PULSE.data.mltrace.MLTrace.resample`,
            defaults to 'hann'
        :type window: str, optional
        :param kwargs: key-word argument collector passed to subroutine calls of :meth:`~PULSE.data.mltrace.MLTrace.interpolate`
        """
        # Run safety check that no reference values are none
        if any(self.stats[_e] is None for _e in ['target_starttime','target_npts','target_sampling_rate']):
            raise TypeError('Cannot use this method if any target value is NoneType')
        # Run checks up front to skip a lot of logic tree steps if things are copacetic 
        check_results = self.check_windowing_status(mode='full')
        # Iterate across all traces in this Window
        for comp, _mlt in self.items():
            # Get their specific results
            result = check_results[comp]
            
            # Check 1: All checks passed by this component - continue to next component
            if all(result.values()):
                continue
            else:
                _mlt.align_sampling(
                    starttime=self.stats.target_starttime,
                    sampling_rate=self.stats.target_sampling_rate,
                    npts=self.stats.target_npts,
                    fill_value=fill_value,
                    window=window,
                    **kwargs)

    def 

    ########################
    # FILL RULE METHODS ####
    ########################

    def apply_fill_rule(self, secondary_components='NE', rule='clone_primary_fill', tolerance=1e-3):
        """Apply a component-fill rule to this Window that uses the primary component trace
        and specified secondary components. If secondary components do not exist or have an insufficient
        valid amount of data (i.e., fvalid < secondary_threshold - tolerance) they will be generated
        following the specified component-fill rule. If there are traces in this Window that do not
        match the primary or secondary components specified, they will be removed from this Window and
        returned as an output of this method.

        Documentation for specific rules:
         - :meth:`~PULSE.data.window.Window.zeros_fill` - fill missing/below-threshold secondary traces with 0-data/fold traces
         - :meth:`~PULSE.data.window.Window.clone_primary_fill` - fill missing/below-threshold secondary traces with primary-data/0-fold traces
         - :meth:`~PULSE.data.window.Window.clone_secondary_fill` - try to fill missing/below-threshold secondary trace with present & passing secondary trace,
            failing that reverts to `clone_primary_fill` behavior

        :param secondary_components: 2-element string that , defaults to 'NE'
        :type secondary_components: str, optional
        :param rule: name of the fill method to apply, defaults to 'clone_primary_fill'. See options above.
        :type rule: str, optional
        :param tolerance: allowable tolerance for small fvalid misfits when compared to threshold values in **Window.stats**, defaults to 1e-3.
            Must be a value in [0, 1)
        :type tolerance: float, optional
        :return: 
         - **popped_traces** (*list* of *PULSE.data.mltrace.MLTrace*) -- list of traces removed from the window that do not match the
                primary or secondary component codes provided. See :meth:`~PULSE.data.window.Window.set_secondary_components
        """        
        # Compatability check for rule
        if rule not in ['zeros_fill','clone_primary_fill','clone_secondary_fill']:
            raise ValueError(f'rule {rule} not supported.')
        else:
            pass

        # Set secondary_components and form component list
        popped_traces = self.set_secondary_components(secondary_components=secondary_components)
        component_list = self.stats.primary_component + self.stats.secondary_components
        
        # Run valid fraction checks
        fv_checks = self.run_fvalid_checks(tolerance=tolerance)
        for comp in component_list:
            if comp not in fv_checks.keys():
                fv_checks.update({comp: False})
        
        # If all checks pass, do nothing
        if all(_v for _v in fv_checks.values()):
            pass
        elif rule == 'zeros_fill':
            self.zeros_fill(fv_checks)
        elif rule == 'clone_primary_fill':
            self.clone_primary_fill(fv_checks)
        elif rule == 'clone_secondary_fill':
            self.clone_secondary_fill(fv_checks)
        else:
            raise ValueError(f'rule has somehow been changed to a non-compliant value {rule}...')
        
        return popped_traces


    def zeros_fill(self, fv_checks):
        """Apply the fill rule from :cite:`Retailleau2022` for missing horizontal components.
        
        For any secondary component mltraces that did not pass the fv_check, or are absent:

        Replace them with a copy of the primary_component mltrace that has 0-vectors for both its data and fold attributes (a 0-trace).
        The component code of the failing/absent secondary component is applied to the 0-trace.

        Uses the following methods from :class:`~PULSE.data.mltrace.MLTrace`:
         - :meth:`~PULSE.data.mltrace.MLTrace.to_zero` with **method='both'**
         - :meth:`~PULSE.data.mltrace.MLTrace.set_comp`

        :param fv_checks: dictionary with primary and secondary component character keys and True/False values
            Generated by :meth:`~PULSE.data.window.Window.check_fvalid`
        :type fv_checks: dict
        """
        
        if self.stats.primary_component not in self.traces.keys():
            raise KeyError(f'primary_component {self.stats.primary_component} is not a key in this Window.')        
        # If the primary trace has enough data
        elif fv_checks[self.stats.primary_component]:
            # Create a 0-trace with metadata copied from the primary trace
            tr0 = self.primary.copy().to_zero(method='both')
        # If the primary has insufficient data, kick error
        else:
            raise ValueError('primary component has insufficient data')

        # Iterate across component codes and threshold statuses
        for _k, _v in fv_checks.items():
            # If this is a secondary trace
            if _k != self.stats.primary_component:
                # If the trace did not pass the fvalid threshold
                if not _v:
                    # Replace with 0-trace copy with updated component code
                    self.traces.update({_k:tr0.copy().set_comp(_k)})
                # If the secondary trace passed fvalid threshold, retain it
                else:
                    continue
            # If this is the primary trace, continue to next iteration
            else:
                continue

                
    def clone_primary_fill(self, fv_checks):
        """Apply the fill rule from :cite:`Ni2023` for missing horizontal components.
        
        For any secondary component mltraces that did not pass the fv_check, or are absent:
        Replace them with a clone of the primary_component mltrace that retains its data vector, but has
        a 0-vector for its fold attribute to convey that no unique information is provided by the clone. 
        The component code of the failing/absent secondary component is applied to the clone. 

        Uses the following methods from :class:`~PULSE.data.mltrace.MLTrace`:
         - :meth:`~PULSE.data.mltrace.MLTrace.to_zero` with **method='fold'**
         - :meth:`~PULSE.data.mltrace.MLTrace.set_comp`

        :param fv_checks: dictionary with primary and secondary component character keys and True/False values
            Generated by :meth:`~PULSE.data.window.Window.run_fvalid_checks` for the primary_component and secondary_components codes
        :type fv_checks: dict
        """
        if self.stats.primary_component not in self.traces.keys():
            raise KeyError(f'primary_component {self.stats.primary_component} is not a key in this Window.')  
        elif fv_checks[self.stats.primary_component]:
            tr0 = self.primary.copy().to_zero(method='fold')
        else:
            raise ValueError('primary component trace has insufficient data')
        # Iterate over all test results
        for _k, _v in fv_checks.items():
            # If this is not the primary component
            if _k != self.stats.primary_component:
                # If the secondary_component failed
                if not _v:
                    # Replace it with a 0-trace clone with the appropriate component code
                    self.traces.update({_k:tr0.copy().set_comp(_k)})
                # If secondary_component passed, continue to next component
                else:
                    continue
            # If this is the primary component, continue to the next component
            else:
                continue
    
    def clone_secondary_fill(self, fv_checks):
        """Apply the fill rule from :cite:`Lara2023` if only one secondary component is present and passing, 
        otherwise apply the fill rule from :cite:`Ni2023` -- :meth:`~PULSE.data.window.Window.clone_primary_fill`.
        
        If only one secondary compoent mltrace is present and passes the fv_check, clone that secondary component
        mltrace to fill in for the other missing/failing secondary trace. The clone has it's fold attribute
        set to a 0-vector to convey that no unique information is provided by the clone.

        Uses the following methods from :class:`~PULSE.data.mltrace.MLTrace`:
         - :meth:`~PULSE.data.mltrace.MLTrace.to_zero` with **method='fold'**
         - :meth:`~PULSE.data.mltrace.MLTrace.set_comp`

        If both secondary component mltraces are absent or fail the fv_check, :meth:`~PULSE.data.window.Window.clone_primary_fill`
        is used instead.

        :param fv_checks: dictionary with primary and secondary component character keys and True/False values
            Generated by :meth:`~PULSE.data.window.Window.run_fvalid_checks`
        :type fv_checks: dict
        """
        # Safety check on primary_components
        if self.stats.primary_component not in self.traces.keys():
            raise KeyError(f'primary_component {self.stats.primary_component} is not a key in this Window.')  
        elif fv_checks[self.stats.primary_component]:
            pc = self.stats.primary_component
        else:
            raise ValueError('primary component trace has insufficient data')
        # Safety check on secondary_components reflects a 3-component 
        scc = self.stats.get_unique_secondary_components()
        if len(scc) != 2:
            raise NotImplementedError('Current version of this rule only works with 3-component data')
        else:
            pass
        # Case 1: all components pass, do nothing
        if all(fv_checks.values()):
            return
        # Case 2: both secondary components fail, use clone_primary_fill
        elif not any(fv_checks[_s] for _s in scc) and fv_checks[pc]:
            self.clone_primary_fill(fv_checks)
        # Case 3: one secondary component passes
        elif fv_checks[scc[0]] != fv_checks[scc[1]]:
            # If the first listed component is present and valid
            if fv_checks[scc[0]]:
                self.traces[scc[1]] = self.traces[scc[0]].copy().to_zero(method='fold').set_comp(scc[1])
            # If the second listed component is present and valid
            elif fv_checks[scc[1]]:
                self.traces[scc[0]] = self.traces[scc[1]].copy().to_zero(method='fold').set_comp(scc[0])
        # Safety catch
        else:
            raise ValueError('Logic error - should not get here')



    
    ###############################################################################
    # Synchronization Methods #####################################################
    ###############################################################################
            
    def check_windowing_status(self,
                               target_starttime=None,
                               target_sampling_rate=None,
                               target_npts=None,
                               mode='summary'):
        """
        Check if the data timing and sampling in this Window are synchronized
        with the target_* [starttime, sampling_rate, npts] attributes in its Stats object
        or those specified as arguments in this check_sync() call. Options are provided for
        different slices of the boolean representation of trace-attribute-reference sync'-ing

        This method also checks if data are masked, using the truth of np.ma.is_masked(tr.data)
        as the output

        :: INPUTS ::
        :param target_starttime: if None - use self.stats.target_starttime
                                    if UTCDateTime - use this value for sync check on starttime
        :type target_starttime: None or obspy.core.utcdatetime.UTCDateTime
        :param target_sampling_rate: None - use self.stats.target_sampling_rate
                                    float - use this value for sync check on sampling_rate
        :type target_sampling_rate: None or float
        :param target_npts: None - use self.stats.target_npts
                                    int - use this value for sync check on npts
        :type target_npts: None or int
        :param mode: output mode
                        'summary' - return the output of bool_array.all()
                        'trace' - return a dictionary of all() outputs of elements 
                                subset by trace
                        'attribute' - return a dictionary of all() outputs of elements
                                subset by attribute
                        'full' - return a pandas DataFrame with each element, labeled
                                with trace component codes (columns) and 
                                attribute names (index)
        :type mode: str
        :param sample_tol: fraction of a sample used for timing mismatch tolerance, default is 0.1
        :type sample_tol: float
        :return status: [bool] - for mode='summary'
                        [dict] - for mode='trace' or 'attribute'
                        [DataFrame] - for mode='full'
        :rtype status: bool, dict, or pandas.core.dataframe.DataFrame
        """
        ref = {}
        if target_starttime is not None:
            ref.update({'starttime': target_starttime})
        elif self.stats.target_starttime is not None:
            ref.update({'starttime': self.stats.target_starttime})
        else:
            raise ValueError('Neither stats.target_starttime or kwarg target_starttime are assigned')
        
        if target_sampling_rate is not None:
            ref.update({'sampling_rate': target_sampling_rate})
        elif self.stats.target_sampling_rate is not None:
            ref.update({'sampling_rate': self.stats.target_sampling_rate})
        else:
            raise ValueError('Neither stats.target_sampling_rate or kwarg target_sampling_rate are assigned')
             
        if target_npts is not None:
            ref.update({'npts': target_npts})
        elif self.stats.target_npts is not None:
            ref.update({'npts': self.stats.target_npts})
        else:
            raise ValueError('Neither stats.target_npts or kwarg target_npts are assigned')
        
        holder = []
        for _tr in self.traces.values():
            line = []
            for _k, _v in ref.items():
                # if _k == 'starttime':
                #     line.append(abs(getattr(_tr.stats,_k) - _v) <= sample_tol*ref['sampling_rate'])
                # else:
                line.append(getattr(_tr.stats,_k) == _v)
            line.append(not np.ma.is_masked(_tr.data))
            holder.append(line)
        
        bool_array = np.array(holder)
        if mode == 'summary':
            status=bool_array.all()
        elif mode == 'attribute':
            status = dict(zip(list(ref.keys()) + ['mask_free'], bool_array.all(axis=0)))
        elif mode == 'trace':
            status = dict(zip(self.traces.keys(), bool_array.all(axis=1)))
        elif mode == 'full':
            status = pd.DataFrame(bool_array,
                                  columns=list(ref.keys()) + ['mask_free'],
                                  index=self.traces.keys()).T
        return status

    def treat_gaps(self,
                   filterkw={'type': 'bandpass', 'freqmin': 1, 'freqmax': 45},
                   detrendkw={'type': 'linear'},
                   resample_method='resample',
                   resamplekw={},
                   taperkw={'max_percentage': None, 'max_length': 0.06},
                   mergekw={},
                   trimkw={'pad': True, 'fill_value':0}):
        """Execute a PULSE.data.mltrace.MLTrace.treat_gaps() method on each trace
        in this Window using common kwargs (see below) and reference sampling data
        in the Window.stats

        filter -> detrend* -> resample* -> taper* -> merge* -> trim

        For expanded explanation of key word arguments, see PULSE.data.mltrace.MLTrace.treat_gaps

        :param filterkw: kwargs to pass to MLTrace.filter(), defaults to {'type': 'bandpass', 'freqmin': 1, 'freqmax': 45}
        :type filterkw: dict, optional
        :param detrendkw: kwargs to pass to MLTrace.detrend(), defaults to {'type': 'linear'}
        :type detrendkw: dict, optional
        :param resample_method: resampling method to use, defaults to 'resample'
                supported values - 'resample','interpolate','decimate'
        :type resample_method: str, optional
        :param resamplekw: kwargs to pass to specified resample_method, defaults to {}
        :type resamplekw: dict, optional
                            obspy.core.trace.Trace.interpolate
                            obspy.core.trace.Trace.decimate
        :param taperkw: kwargs to pass to MLTrace.taper(), defaults to {}
        :type taperkw: dict, optional
        :param mergekw: kwargs to pass to MLTrace.merge, defaults to {}
        :type mergekw: dict, optional
        :param trimkw: kwargs to pass to MLTrace.trim, defaults to {'pad': True, 'fill_value':0}
        :type trimkw: dict, optional
        """        
        # Get reference values from header
        ref = {}
        for _k in ['target_starttime','target_npts','target_sampling_rate']:
            ref.update({'_'.join(_k.split("_")[1:]): self.stats[_k]})
        resamplekw.update({'sampling_rate':ref['sampling_rate']})
        trimkw.update({'starttime': ref['starttime'],
                        'endtime': ref['starttime'] + (ref['npts'] - 1)/ref['sampling_rate']})
        for tr in self:
            tr.treat_gaps(
                filterkw = filterkw,
                detrendkw = detrendkw,
                resample_method=resample_method,
                resamplekw=resamplekw,
                taperkw=taperkw,
                mergekw=mergekw,
                trimkw=trimkw)
            if tr.stats.sampling_rate != ref['sampling_rate']:
                breakpoint()

    
    def sync_to_reference(self, fill_value=0., sample_tol=0.05, **kwargs):
        """Use a combination of trim and interpolate functions to synchronize
        the sampling of traces contained in this WindowWyrm

        Wraps the PULSE.data.mltrace.MLTrace.sync_to_window() method

        :param fill_value: fill value for, defaults to 0.
        :type fill_value: _type_, optional
        :raises ValueError: _description_
        :raises ValueError: _description_
        :raises ValueError: _description_
        :return: _description_
        :rtype: _type_
        """ 
        if not isinstance(sample_tol, float):
            raise TypeError('sample_tol must be float')
        elif not 0 <= sample_tol < 0.1:
            raise ValueError('sample_tol must be a small float value \in [0, 0.1)')
        starttime = self.stats.target_starttime
        if starttime is None:
            raise ValueError('target_starttime must be specified in this Window\'s `stats`')
        npts = self.stats.target_npts
        if npts is None:
            raise ValueError('target_npts must be specified in this Window\'s `stats`')
        sampling_rate = self.stats.target_sampling_rate
        if sampling_rate is None:
            raise ValueError('target_sampling_rate must be specified in this Window\'s `stats`')

        endtime = starttime + (npts-1)/sampling_rate

        # If any checks against windowing references fail, proceed with interpolation/padding
        if not self.check_windowing_status(mode='summary'):
            # df_full = self.check_windowing_status(mode='full')
            for _tr in self:
                _tr.sync_to_window(starttime=starttime, endtime=endtime, fill_value=fill_value, **kwargs)

        # Extra sanity check if timing is ever so slightly off
        if not self.check_windowing_status(mode='summary'):
            asy = self.check_windowing_status(mode='attribute')
            # If it is just a starttime rounding error
            if not asy['starttime'] and asy['sampling_rate'] and asy['npts'] and asy['mask_free']:
                # Iterate across traces
                for tr in self:
                    # If misfit is \in (0, tol_sec], just reassign trace starttime as reference
                    if 0 < abs(tr.stats.starttime - starttime) <= sample_tol/sampling_rate:
                        tr.stats.starttime = starttime
            else:
                breakpoint()

        return self


    ###############################################################################
    # Window to Tensor Methods ###########################################
    ###############################################################################
            
    def ready_to_burn(self, model):
        """
        Assess if the data contents of this Window are ready
        to convert into a torch.Tensor given a particular seisbench model

        NOTE: This inspects that the dimensionality, timing, sampling, completeness,
             and component aliasing of the contents of this Window are
             compliant with reference values in the metadata and in the input `model`'s
             metadata
              
             It does not check if the data have been processed: filtering, tapering, 
                normalization, etc. 

        :: INPUT ::
        :param model: [seisbench.models.WaveformModel] initialized model
                        object that prediction will be run on 
                        NOTE: This is really a child-class of sbm.WaveformModel
        :: OUTPUT ::
        :return status: [bool] - is this Window ready for conversion
                                using Window.to_torch(model)?
        """
        # model compatability check
        if not isinstance(model, sbm.WaveformModel):
            raise TypeError
        elif model.name == 'WaveformModel':
            raise ValueError('WaveformModel baseclass objects do not provide a viable prediciton method - use a child class thereof')
        if any(_tr is None for _tr in self):
            breakpoint()
        # Check that data are not masked
        if any(isinstance(_tr.data, np.ma.MaskedArray) for _tr in self):
            status = False
        # Check starttime sync
        elif not all(_tr.stats.starttime == self.stats.target_starttime for _tr in self):
            status = False
        # Check npts is consistent
        elif not all(_tr.stats.npts == model.in_samples for _tr in self):
            status = False
        # Check that all components needed in model are represented in the aliases
        elif not all(_k in model.component_order for _k in self.traces.keys()):
            status = False
        # Check that sampling rate is sync'd
        elif not all(_tr.stats.sampling_rate == self.stats.target_sampling_rate for _tr in self):
            status = False
        # Passing (or really failing) all of the above
        else:
            status = True
        return status
    
    def to_npy_tensor(self, model):
        """
        Convert the data contents of this Window into a numpy array that
        conforms to the component ordering required by a seisbench WaveformModel
        object
        :: INPUT ::
        :param model: []
        """
        if not self.ready_to_burn(model):
            raise ValueError('This Window is not ready for conversion to a torch.Tensor')
        
        npy_array = np.c_[[self[_c].data for _c in model.component_order]]
        return npy_array
        # tensor = torch.Tensor(npy_array)
        # return tensor

    def collapse_fold(self):
        """
        Collapse fold vectors into a single vector by addition, if all traces have equal npts
        """
        npts = self[0].stats.npts
        if all(_tr.stats.npts == npts for _tr in self):
            addfold = np.sum(np.c_[[_tr.fold for _tr in self]], axis=0)
            return addfold
        else:
            raise ValueError('not all traces in this Window have matching npts')
        


   # def extend(self, other, **options):
    #     """Extend (add more) trace(s) to this Window, checking if non-unique component codes are compliant
    
    #     LOGIC TREE
    #     If the component code(s) of the trace(s) is/are included in this object's `window.stats.aliases` attribute
    #         - If the component code is new, it is added using :meth:`~dict.update`
    #         - If the component code already exists in the Window, if the trace-like objects are compliant, they are merged using :meth:`~PULSE.data.mltrace.MLTrace.__add__` method

    #     Following a successful update/__add__ operation, the metadata held in this object's `window.stats`
    #     attribute are updated using the 

    #     :param other: trace-like object(s) to add to this Window, keying on their component codes
    #     :type other: obspy.core.trace.Trace like
        
    #     **options: collector for key-word arguments passed to :meth:`~PULSE.data.mltrace.MLTrace.__add__` (see description above)
    #     """
    #     # If extending with a single trace object
    #     if isinstance(other, Trace):
    #         other = [other]
    #     elif isinstance(other, (list, Stream)):
    #         if all(isinstance(_e, Trace) for _e in other):
    #             pass
    #         else:
    #             raise TypeError('Not all elements in other are obspy.core.trace.Trace-like.')
    #     else:
    #         raise TypeError('other must be obspy.core.trace.Trace-like, obspy.core.stream.Stream-like, or a list of Trace-like objects.')

    #     # Iterate across other
    #     for mlt in other:
    #         # If it is not an MLTrace, make it one
    #         if not isinstance(mlt, MLTrace):
    #             mlt = MLTrace(mlt)
    #         # If component is a primary key
    #         if mlt.comp in self.stats.primary_component:
    #             # And that key is not in the current holdings
    #             if comp not in self.traces.keys():
    #                 self.traces.update({comp: tr})
    #             else:
    #                 self.traces[comp].__add__(tr, **options)
    #             self.stats.update_time_range(self.traces[comp])
    #         # If component is an aliased key    
    #         elif comp in ''.join(self.stats.aliases.values()):
    #             # Get the matching alias/key pair
    #             for _k, _v in self.stats.aliases.items():
    #                 if comp in _v:
    #                     # If primary key not in current holdings
    #                     if _k not in self.traces.keys():
    #                         self.traces.update({_k: tr})
    #                     else:
    #                         self.traces[_k].__add__(tr, **options)
    #                     self.stats.update_time_range(self.traces[_k])
    #                     break
    #                 else:
    #                     pass
    #         # If component is not in the alias list, skip
    #         else:
    #             self.logger.debug(f'component code for {tr.id} is not in stats.aliases. Skipping this trace')
    #             pass
    #             # breakpoint()
    #             # raise ValueError('component code for {tr.id} is not in the self.stats.aliases dictionary')



    # def apply_fill_rule(self, rule='zeros'):
    #     """Summative class-method for assessing if channels have enough valid data
    #     in the "reference" and "other" components and apply the specified channel fill `rule`
    #     for addressing "other" components that have insufficient valid data or are missing.

    #     If one or more "other" component codes 

    #     If the "reference" channel does not have sufficient valid data the method will return a ValueError.

    #     Data validity for each trace is assessed using the :meth:`~PULSE.data.mltrace.MLTrace.get_fvalid_subset`
    #     method with the starttime `window.stats.target_starttime` attribute and the endtime implied by the
    #     `window.stats.target_npts` and `window.stats.target_sampling_rate` attributes. 
        
    #     The threshold criteria for a give trace to be considered "valid" is a get_fvalid_subset output value
    #     that meets or exceeds the relevant threshold value in `window.stats.thresholds`

    #     :param rule: channel fill rule to apply to non-reference channels that are
    #                 missing or fail to meet the `secondary_thresh` requirement, defaults to 'zeros'
    #                 Supported Values
    #                     'zeros' - fill missing/insufficient "other" traces with 0-valued data and fold vectors
    #                         - see :meth:`~PULSE.data.window.Window._apply_zeros`
    #                         - e.g., Retailleau et al. (2022)
    #                     'clone_ref' - clone the "reference" trace if any "other" traces are missing/insufficient
    #                         - see :meth:`~PULSE.data.window.Window._apply_clone_ref`
    #                         - e.g., Ni et al. (2023)
    #                     'clone_other' - if an "other" trace is missing/insufficient but one "other" trace is present and sufficient,
    #                         clone the present and sufficient "other" trace. If both "other" traces are missing, uses the "clone_ref" subroutine
    #                         - see :meth`~PULSE.data.window.Window._apply_clone_other`
    #                         - e.g., Lara et al. (2023)
    #     :type rule: str, optional
                
    #     """      


    #     thresh_dict = {}
    #     primary_thresh = self.stats.primary_threshold
    #     secondary_thresh = self.stats.secondary_threshold
    #     for _k in self.stats.aliases.keys():
    #         if _k == self.stats.primary_component:
    #             thresh_dict.update({_k: primary_thresh})
    #         else:
    #             thresh_dict.update({_k: secondary_thresh})

    #     # Check if all expected components are present and meet threshold
    #     checks = [thresh_dict.keys() == self.traces.keys(),
    #               all(_v.get_fvalid_subset() >= thresh_dict[_k] for _k, _v in self.traces.items())]
    #     # If so, do nothing
    #     if all(checks):
    #         pass
    #     # Otherwise apply rule
    #     elif rule == 'zeros':
    #         self._apply_zeros(thresh_dict)
    #     elif rule == 'clone_ref':
    #         self._apply_clone_ref(thresh_dict)
    #     elif rule == 'clone_other':
    #         self._apply_clone_other(thresh_dict)
    #     else:
    #         raise ValueError(f'rule {rule} not supported. Supported values: "zeros", "clone_ref", "clone_other"')

    # def _apply_zeros(self, thresh_dict): 
    #     """Apply the channel filling rule "zeros" (e.g., Retailleau et al., 2022)
    #     where both "other" (horzontal) components are set as zero-valued traces
    #     if one or both are missing/overly gappy.

    #     0-valued traces are assigned fold values of 0 to reflect the absence of
    #     added information.

    #     :param thresh_dict: directory with keys matching keys in 
    #                     self.traces.keys() (i.e., alised component characters)
    #                     and values :math:`\in [0, 1]` representing fractional completeness
    #                     thresholds below which the associated component is rejected
    #     :type thresh_dict: dict
    #     :raises ValueError: raised if the `ref` component has insufficient data
    #     """
    #     ref_comp = self.stats.primary_component
    #     primary_thresh = self.stats.thresholds['primary']
    #     ref_other = self.stats.thresholds['secondary']
    #     # Get reference trace
    #     ref_tr = self.traces[ref_comp]
    #     # Safety catch that at least the reference component does have enough data
    #     if ref_tr.get_fvalid_subset() < primary_thresh:
    #         # Attempted fix for small decrease in valid fraction due to resampling
    #         if np.abs((ref_tr.get_fvalid_subset() - primary_thresh)/primary_thresh) < 0.01:
    #             pass
    #         else:
    #             breakpoint()
    #             raise ValueError('insufficient valid data in reference trace')
    #     else:
    #         pass
    #     # Iterate across entries in the threshold dictionary
    #     for _k in thresh_dict.keys():
    #         # For "other" components
    #         if _k != ref_comp:
    #             # Create copy of reference trace
    #             tr0 = ref_tr.copy()
    #             # Relabel
    #             tr0.set_comp(_k)
    #             # Set data and fold to zero
    #             tr0.to_zero(method='both')
    #             # Update 
    #             self.traces.update({_k: tr0})

    # def _apply_clone_ref(self, thresh_dict):
    #     """
    #     Apply the channel filling rule "clone reference" (e.g., Ni et al., 2023)
    #     where the reference channel (vertical component) is cloned onto both
    #     horizontal components if one or both horizontal (other) component data
    #     are missing or are sufficiently gappy. 
        
    #     Cloned traces are assigned fold values of 0 to reflect the absence of
    #     additional information contributed by this trace.

    #     :: INPUTS ::
    #     :param thresh_dict: dictionary with keys matching keys in 
    #                     self.traces.keys() (i.e., alised component characters)
    #                     and values \in [0, 1] representing fractional completeness
    #                     thresholds below which the associated component is rejected
    #     :type thresh_dict: dict
    #     :raise ValueError: If ref trace has insufficient data
    #     """
    #     # Get reference trace
    #     ref_comp = self.stats.primary_component
    #     ref_tr = self[ref_comp]
    #     # Get 
    #     if ref_tr.fvalid < thresh_dict[ref_comp]:
    #         raise ValueError('insufficient valid data in reference trace')
    #     else:
    #         pass
    #     for _k in thresh_dict.keys():
    #         if _k != ref_comp:
    #             # Create copy of reference trace
    #             trC = ref_tr.copy()
    #             # Relabel component
    #             trC.set_comp(_k)
    #             # Zero-out fold on copies
    #             trC.to_zero(method='fold')
    #             # Update zero-fold copies as new "other" component(s)
    #             self.traces.update({_k: trC})

    # def _apply_clone_other(self, thresh_dict):
    #     """
    #     Apply the channel filling rule "clone other" (e.g., Lara et al., 2023)
    #     where the reference channel (vertical component) is cloned onto both
    #     horizontal components if both "other" component traces (horizontal components)
    #     are missing or are sufficiently gappy, but if one "other" component is present
    #     and valid, clone that to the missing/overly-gappy other "other" component.
        
    #     Cloned traces are assigned fold values of 0 to reflect the absence of
    #     additional information contributed by this trace.

    #     :param thresh_dict: dictionary with keys matching keys in 
    #                     self.traces.keys() (i.e., alised component characters)
    #                     and values \in [0, 1] representing fractional completeness
    #                     thresholds below which the associated component is rejected
    #     :type thresh_dict: dict
    #     """
    #     ref_comp = self.stats.primary_component
    #     # Run through each component and see if it passes thresholds
    #     pass_dict = {}
    #     for _k, _tr in self.traces.items():
    #         pass_dict.update({_k: _tr.fvalid >= thresh_dict[_k]})

    #     # If the reference component is present but fails to pass, kick error
    #     if ref_comp in pass_dict.keys():
    #         if not pass_dict[ref_comp]:
    #             raise ValueError('insufficient valid data in reference trace')
    #         else:
    #             pass
    #     # If the reference component is absent, kick error
    #     else:
    #         raise KeyError("reference component is not in this Window's keys")
        
    #     # If all expected components are present
    #     if pass_dict.keys() == thresh_dict.keys():
    #         # If all components pass thresholds
    #         if all(pass_dict.values()):
    #             # Do nothing
    #             pass

    #         # If at least one "other" component passed checks
    #         elif any(_v if _k != ref_comp else False for _k, _v in pass_dict.items()):
    #             # Iterate across components in 
    #             for _k, _v in pass_dict.items():
    #                 # If not the reference component and did not pass
    #                 if _k != ref_comp and not _v:
    #                     # Grab component code that will be cloned over
    #                     cc = _k
    #                 # If not the reference component and did pass
    #                 if _k != ref_comp and _v:
    #                     # Create a clone of the passing "other" component
    #                     trC = _v.copy()
    #             # Zero out the fold of the cloned component and overwrite it's component code
    #             trC.to_zero(method='fold').set_comp(cc)
    #             # Write cloned, relabeled "other" trace to the failing trace's position
    #             self.traces.update({cc: trC})

    #         # If only the reference trace passed, run _apply_clone_ref() method instead
    #         else:
    #             self._apply_clone_ref(thresh_dict)

    #     # If ref and one "other" component are present
    #     elif ref_comp in pass_dict.keys() and len(pass_dict) > 1:
    #         # ..and they both pass checks
    #         if all(pass_dict.items()):
    #             # Iterate across all expected components
    #             for _c in thresh_dict.keys():
    #                 # to find the missing component 
    #                 # (case where all components are present & passing is handled above) 
    #                 # catch the missing component code
    #                 if _c not in pass_dict.keys():
    #                     cc = _c
    #                 # and use the present "other" as a clone template
    #                 elif _c != ref_comp:
    #                     trC = self[_c].copy()
    #             # Stitch results from the iteration loop together
    #             trC.set_comp(cc)
    #             # Zero out fold
    #             trC.to_zero(method='fold')
    #             # And update traces with clone
    #             self.traces.update({cc: trC})
    #         # If the single "other" trace does not pass, use _apply_clone_ref method
    #         else:
    #             self._apply_clone_ref(thresh_dict)
    #     # If only the reference component is present & passing
    #     else:
    #         self._apply_clone_ref(thresh_dict)