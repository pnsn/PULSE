"""
:module: wyrm.core.coordinate
:auth: Nathan T. Stevens
:email: ntsteven (at) uw.edu
:org: Pacific Northwest Seismic Network
:license: AGPL-3.0

:purpose:
    This module houses classes used to coordinate operation and execution
    of parallel and serial sets of wyrms and operate the core PyEW.EWModule
    object that defines this collection of wyrms as an Earthworm module.

    Classes:
        TubeWyrm - submodule for executing sequential sets of wyrms wherein
                the output of one wyrm's pulse() method is taken as the input
                to the next wyrm's pulse() method. Final outputs are housed
                in a queue (collections.deque)

                deque(x) -> TubeWyrm -> deque(y)
                    with y = wyrm3.pulse(wyrm2.pulse(wyrm1.pulse(wyrm0.pulse(x))))
        
        CanWyrm - TubeWyrm child class - submodule for executing parallel sets of wyrms
                where the input to all wyrms is the same and the output is written to a
                dictionary keyed by a name given to each wyrm
                              / Wyrm0.pulse(x) -> {wyrm0: y0}
                x -> CanWyrm {  Wyrm1.pulse(x) -> {wyrm1: y1}
                              \ WyrmN.pulse(x) -> {wyrmN: yN}
        
        HeartWyrm - TubeWyrm child class - submodule housing the PyEW.EWModule instance
                that facilitates communication between the Earthworm Message Transport
                System and Python


TODO:
    - Update HeartWyrm with wcc
    - Finish cleanup of CanWyrm                                              
"""
from wyrm.core._base import Wyrm
import wyrm.util.compatability as wcc
from collections import deque
from threading import Thread
from time import sleep
import pandas as pd
import numpy as np
# import PyEW



class TubeWyrm(Wyrm):
    """
    Wyrm child-class facilitating chained execution of pulse(x) class methods
    for a sequence wyrm objects, with each wyrm.pulse(x) taking the prior
    member's pulse(x) output as its input.

    The pulse method operates as follows
    for wyrm_dict = {key0: <wyrm0>, key2: <wyrm2> , key1: <wyrm1>}
        tubewyrm.pulse(x) = wyrm1.pulse(wyrm2.pulse(wyrm0.pulse(x)))

        Note that the dictionary ordering dictates the execution order!
    """

    def __init__(self, wyrm_dict={}, wait_sec=0.0, max_pulse_size=1, debug=False):
        """
        Create a tubewyrm object
        :: INPUT ::
        :param wyrm_dict: [dict], [list], or [deque] of [Wyrm-type] objects
                        that are executed in their provided order. dict-type
                        entries allow for naming of component wyrms for 
                        user-friendly assessment. list, deque, and Wyrm-type
                        inputs use a 0-indexed naming system.
        :param wait_sec: [float] seconds to wait between execution of each
                        Wyrm in wyrm_dict
        :param max_pulse_size: [int] number of times to run the sequence of pulses
                        Generally, this should be 1.
        :param debug: [bool] run in debug mode?

        :: OUTPUT ::
        Initialized TubeWyrm object
        """
        # Inherit from Wyrm
        super().__init__(max_pulse_size=max_pulse_size, debug=debug)

        # wyrm_dict compat. checks
        if isinstance(wyrm_dict, Wyrm):
            self.wyrm_dict = {'_tmp': wyrm_dict}
        elif isinstance(wyrm_dict, dict):
            if all(isinstance(_w, Wyrm) for _w in wyrm_dict.values()):
                self.wyrm_dict = wyrm_dict
            else:
                raise TypeError('All elements in wyrm_dict must be type Wyrm')
        # Handle case where a list or deque are provided
        elif isinstance(wyrm_dict, (list, deque)):
            if all(isinstance(_w, Wyrm) for _w in wyrm_dict):
                # Default keys are the sequence index of a given wyrm
                self.wyrm_dict = {_k: _v for _k, _v in enumerate(wyrm_dict)}
            else:
                raise TypeError('All elements in wyrm_dict must be type Wyrm')
        else:
            raise TypeError('wyrm_dict must be a single Wyrm-type object or a list or dictionary thereof')
        
        # wait_sec compat. checks
        self.wait_sec = wcc.bounded_floatlike(
            wait_sec,
            name='wait_sec',
            minimum=0,
            maximum=None,
            inclusive=True
        )
        # Create a list representation of keys
        self.names = list(wyrm_dict.keys())

        # Enforce debug setting on all subsequent wyrms
        for _w in self.wyrm_dict.values():
            _w.debug = self.debug
        
        # Get input and output types from wyrm_dict
        self._in_type = self.wyrm_dict[self.names[0]]._in_type
        self._out_type = self.wyrm_dict[self.names[0]]._out_type

    def update(self, new_dict):
        """
        Apply update to wyrm_dict using the 
        dict.update(new_dict) builtin_function_or_method
        and then update relevant attributes of this TubeWyrm

        This will update existing keyed entries and append new
        at the end of self.wyrm_dict (same behavior as dict.update)

        :: INPUT ::
        :param new_dict: [dict] of [Wyrm] objects

        :: OUTPUT ::
        :return self: [TubeWyrm] enables cascading
        """
        if not isinstance(new_dict, dict):
            raise TypeError('new_dict must be type dict')
        elif not all(isinstance(_w, Wyrm) for _w in new_dict.values()):
            raise TypeError('new_dict can only have values of type Wyrm')
        else:
            pass
        # Run updates on wyrm_dict, enforce debug, and update names list
        self.wyrm_dict.update(new_dict)
        for _w in self.wyrm_dict.values():
            _w.debug = self.debug
        self.names = list(self.wyrm_dict.keys())
        return self
    
    def remove(self, key):
        """
        Convenience wrapper of the dict.pop() method
        to remove an element from self.wyrm_dict and
        associated attributes

        :: INPUT ::
        :param key: [object] valid key in self.wyrm_dict.keys()

        :: RETURN ::
        :return popped_item: [tuple] popped (key, value)
        """
        if key not in self.wyrm_dict.keys():
            raise KeyError(f'key {key} is not in self.wyrm_dict.keys()')
        
        val = self.wyrm_dict.pop(key)
        self.names = list(self.wyrm_dict.keys())
        return (key, val)

    def reorder(self, reorder_list):
        """
        Reorder the current contents of wyrm_dict using either
        an ordered list of wyrm_dict

        :: INPUT ::
        :reorder_list: [list] unique list of keys from self.wyrm
        """
        # Ensure reorder_list is a list
        if not isinstance(reorder_list, list):
            raise TypeError('reorder_list must be type list')

        # Ensure reorder_list is a unique set
        tmp_in = []
        for _e in reorder_list:
            if _e not in tmp_in:
                tmp_in.append(_e)
        if tmp_in != reorder_list:
            raise ValueError('reorder_list has repeat entries - all entries must be unique')

        # Conduct reordering if checks are passed
        # Handle input (re)ordered wyrm_dict key list
        if all(_e in self.wyrm_dict.keys() for _e in reorder_list):
            tmp = {_e: self.wyrm_dict[_e] for _e in reorder_list}
        # Handle input (re)ordered index list
        elif all(_e in np.arange(0, len(reorder_list)) for _e in reorder_list):
            tmp_keys = list(self.wyrm_dict.keys())
            tmp = {_k: self.wyrm_dict[_k] for _k in tmp_keys}

        # Run updates
        self.wyrm_dict = tmp
        self.names = list(tmp.keys())
        return self


    def __str__(self, extended=False):
        rstr = super().__str__()
        rstr = "(wait: {self.wait_sec} sec)\n"
        for _i, (_k, _v) in enumerate(self.wyrm_dict.items()):
            # Provide index number
            rstr += f'({_i:<2}) '
            # Provide labeling of order
            if _i == 0:
                rstr += "(head) "
            elif _i == len(self.wyrm_dict) - 1:
                rstr += "(tail) "
            else:
                rstr += "  ||   "
            rstr += f"{_k} | "
            if extended:
                rstr += f'{_v.__str__()}\n'
            else:
                rstr += f'{type(_v)}\n'
        return rstr


    def pulse(self, x):
        """
        Initiate a chained pulse for elements of wyrm_queue.

        E.g.,
        tubewyrm.wyrm_dict = {name0:<wyrm0>,
                              name1:<wyrm1>,
                              name2:<wyrm3>}
        y = tubewyrm.pulse(x)
            is equivalent to
        y = wyrmw.pulse(wyrmq.pulse(wyrm0.pulse(x)))

        Between each successive wyrm in the wyrm_dict there
        is a pause of self.wait_sec seconds.

        :: INPUT ::
        :param x: Input `x` for the first Wyrm object in wyrm_dict

        :: OUTPUT ::
        :param y: Output `y` from the last Wyrm object in wyrm_dict
        """
        for _i, _wyrm in enumerate(self.wyrm_list):
            x = _wyrm.pulse(x)
            # if not last step, wait specified wait_sec
            if _i + 1 < len(self.wyrm_list):
                sleep(self.wait_sec)
        y = x
        return y


class CanWyrm(TubeWyrm):
    """
    Child class of TubeWyrm.
    It's pulse(x) method runs the dict of *wyrm_n.pulse(x)'s
    sourcing inputs from a common input `x` and creating a dict
    of each wyrm_n.pulse(x)'s output `y_n`.

    NOTE: This class runs items in serial, but with some modification
    this would be a good candidate class for orchestraing multiprocessing.
    """

    def __init__(self,
                 wyrm_dict={},
                 wait_sec=0.,
                 method='append',
                 max_pulse_size=1,
                 debug=False):
        """
        
        """
        # Initialize from Wyrm inheritance
        super().__init__(wyrm_dict=wyrm_dict, wait_sec=wait_sec, debug=debug, max_pulse_size=max_pulse_size)

        

        # method compat. checks
        for _v in self.wyrm_dict.values():
            if 


        self.names = list(self.wyrm_dict.keys())
        self.buffer = {_k: None for _k in self.names}


    def __str__(self, view='all', **options):
        rstr = super().__repr__()
        rstr += f'\nWyrms in sequence: {len(self.names)}'
        if view in ['all', 'buffer']:
            rstr += '\n--- BUFFER ---'
            for _i, _n in enumerate(self.names):
                rstr += f'\n<{_i}>==v^v====v^v----*\n{self.buffer[_n].__str__(**options)}'
            rstr += '\n... BUFFER ...'
        elif view in ['all', 'wyrms']:
            rstr += '\n--- WYRMS ---'
            for _i, _n in enumerate(self.names):
                rstr += f'\n<{_i}>==v^v====v^v----*\n{self.wyrm_dict[_n].__str__()}'
            rstr += '\n... WYRMS ...'
        return rstr
    
    def __repr__(self):
        rstr = 'wyrm.wyrms.coordinate.CanWyrm('
        rstr += f'wyrm_dict={self.wyrm_dict}, '
        rstr += f'wait_sec={self.wait_sec}, '
        rstr += f'max_pulse_size={self.max_pulse_size}, '
        rstr += f'debug={self.debug})'
        return rstr

    def pulse(self, x):
        
        for _ in range(self.max_pulse_size):
            for _n in self.names:
                y = self.wyrm_dict[_n].pulse(x)
                # If empty buffer element
                if self.buffer[_n] is None:
                    # Use dict.update class method to create initial population
                    self.buffer.update({_n: y})
                # Otherwise
                else:
                    # Use the append class method
                    eval_str = f'self.buffer[_n].{self.method}(y)'
                    eval(eval_str)
        y = self.buffer
        return y


    def pulse(self, x):
        """
        Iterate across wyrms in wyrm_queue that all feed
        from the same input variable x and gather each
        iteration's output y in a deque assembled with an
        appendleft() at the end of each iteration

        :: INPUT ::
        :param x: [variable] Single variable that every
                    Wyrm (or the head-wyrm in a tubewyrm)
                    in the wyrm_queue can accept as a
                    pulse(x) input.

        :: OUTPUT ::
        :return y: [deque] or [self.output_method]
                    Serially assembled outputs of each Wyrm
                    (or the tail-wyrm in a tubewyrm)
        """
        y = self.output_type()
        for _wyrm in self.wyrm_queue:
            _y = _wyrm.pulse(x)
            eval(f'y.{self.concat_method}(_y)')
            sleep(self.wait_sec)
        return y

class HeartWyrm(TubeWyrm):
    """
    This class encapsulates a PyEW.EWModule object and provides the `run`,
    `start` and `stop` class methods required for running a continuous
    instance of a PyEW.EWModule interface between a running instance
    of Earthworm.

    This class inherits the pulse method from wyrm.core.base_wyrms.TubeWyrm
    and adds the functionality of setting a "wait_sec" that acts as a pause
    between instances of triggering pulses to allow data accumulation.
    """

    def __init__(
        self,
        wait_sec,
        DR_ID,
        MOD_ID,
        INST_ID,
        HB_PERIOD,
        wyrm_list=[],
        debug=False
    ):
        """
        ChildClass of wyrm.core.base_wyrms.TubeWyrm

        Initialize a HeartWyrm object that contains the parameters neededto
        initialize an EWModule object assocaited with a running instance of
        Earthworm.

        The __init__ method populates the attributes necessary to initialize
        the EWModule object with a subsequent heartwyrm.initialize_module().

        :: INPUTS ::
        :param wait_sec: [float] wait time in seconds between pulses
        :param DR_ID: [int-like] Identifier for default reference memory ring
        :param MOD_ID: [int-like] Module ID for this instace of Wyrms
        :param INST_ID: [int-like] Installation ID (Institution ID)
        :param HB_PERIOD: [float-like] Heartbeat reporting period in seconds
        :param debug: [BOOL] Run module in debug mode?
        :param wyrm_list: [list-like] iterable set of *wyrm objects
                            with sequentially compatable *wyrm.pulse(x)

        :: PUBLIC ATTRIBUTES ::
        :attrib module: False or [PyEW.EWModule] - Holds Module Object
        :attrib wait_sec: [float] rate in seconds to wait between pulses
        :attrib connections: [pandas.DataFrame]
                            with columns 'Name' and 'Ring_ID' that provides
                            richer indexing and display of connections
                            made to the EWModule via EWModule.add_ring(RING_ID)
                            Updated using heartwyrm.add_connection(RING_ID)
        :attrib wyrm_list: [list] list of *wyrm objects
                            Inherited from TubeWyrm

        :: PRIVATE ATTRIBUTES ::
        :attrib _default_ring_id: [int] Saved DR_ID input
        :attrib _module_id: [int] Saved MOD_ID input
        :attrib _installation_id: [int] Saved INST_ID input
        :attrib _HBP: [float] Saved HB_PERIOD input
        :attrib _debug: [bool] Saved debug input
        """
        super().__init__(
            wyrm_list=wyrm_list,
            wait_sec=wait_sec,
            max_pulse_size=None,
            debug=debug)
        
        # Public Attributes
        self.module = False
        self.conn_info = pd.DataFrame(columns=["Name", "RING_ID"])

        # Private Attributes
        self._default_ring_id = self._bounded_intlike_check(DR_ID, name='DR_ID', minimum=0, maximum=9999)
        self._module_id = self._bounded_intlike_check(MOD_ID, name='MOD_ID', minimum=0, maximum=255)
        self._installation_id = self._bounded_intlike_check(INST_ID, name='INST_ID', minimum=0, maximum=255)
        self._HBP = self._bounded_floatlike_check(HB_PERIOD, name='HB_PERIOD', minimum=1)

        # Module run attributes
        # Threading - TODO - need to understand this better
        self._thread = Thread(target=self.run)
        self.runs = True

    def __repr__(self):
        # Start with TubeWyrm __repr__
        rstr = f"{super().__repr__()}\n"
        # List Pulse Rate
        rstr += f"Pulse Wait Time: {self.wait_sec:.4f} sec\n"
        # List Module Status and Parameters
        if isinstance(self.module, PyEW.EWModule):
            rstr += "Module: Initialized\n"
        else:
            rstr += "Module: NOT Initialized\n"
        rstr += f"MOD: {self._module_id}"
        rstr += f"DR: {self._default_ring_id}\n"
        rstr += f"INST: {self._installation_id}\n"
        rstr += f"HB: {self._HBP} sec\n"
        # List Connections
        rstr += "---- Connections ----\n"
        rstr += f"{self.conn_info}\n"
        rstr += "-------- END --------\n"
        return rstr

    def initialize_module(self, user_check=True):
        if user_check:
            cstr = "About to initialize the following PyEW.EWModule\n"
            cstr += f"Default ring ID: {self._default_ring_id:d}\n"
            cstr += f"Module ID: {self._module_id:d}\n"
            cstr += f"Inst. ID: {self._installation_id:d}\n"
            cstr += f"Heartbeat: {self._HBP:.1f} sec\n"
            cstr += f"Debug?: {self.debug}\n"
            cstr += "\n Do you want to continue? [(y)/n]"
            ans = input(cstr)
            if ans.lower().startswith("y") or ans == "":
                user_continue = True
            elif ans.lower().startswith("n"):
                user_continue = False
            else:
                print("Invalid input -> exiting")
                exit()
        else:
            user_continue = True
        if user_continue:
            # Initialize PyEarthworm Module
            if not self.module:
                try:
                    self.module = PyEW.EWModule(
                        self._default_ring_id,
                        self._module_id,
                        self._installation_id,
                        self._HBP,
                        debug=self.debug,
                    )
                except RuntimeError:
                    print("HeartWyrm: There is already a EWModule running!")
            elif isinstance(self.module, PyEW.EWModule):
                print("HeartWyrm: Module already initialized")
            else:
                print(
                    f"HeartWyrm.module is type {type(self.module)}\
                    -- incompatable!!!"
                )
                raise RuntimeError
        else:
            print("Canceling module initialization -> exiting")
            exit()

    def add_connection(self, RING_ID, RING_Name):
        """
        Add a connection between target ring and the initialized self.module
        and update the conn_info DataFrame.

        Method includes safety catches
        """
        # === RUN COMPATABILITY CHECKS ON INPUT VARIABLES === #
        # Enforce integer RING_ID type
        RING_ID = self._bounded_intlike_check(RING_ID,name='RING_ID', minimum=0, maximum=9999)
        
        # Warn on non-standard RING_Name types and convert to String
        if not isinstance(RING_Name, (int, float, str)):
            print(
                f"Warning, RING_Name is not type (int, float, str) -\
                   input type is {type(RING_Name)}"
            )
            print("Converting RING_Name to <type str>")
            RING_Name = str(RING_Name)

        # --- End Input Compatability Checks --- #

        # === RUN CHECKS ON MODULE === #
        # If the module is not already initialized, try to initialize module
        if not self.module:
            self.initialize_module()
        # If the module is already initialized, pass
        elif isinstance(self.module, PyEW.EWModule):
            pass
        # Otherwise, raise TypeError with message
        else:
            print(f"Module type {type(self.module)} is incompatable!")
            raise TypeError
        # --- End Checks on Module --- #

        # === MAIN BLOCK === #
        # Final safety check that self.module is an EWModule object
        if isinstance(self.module, PyEW.EWModule):
            # If there isn't already an established connection to a given ring
            if not any(self.conn_info.RING_ID == RING_ID):
                # create new connection
                self.module.add_connection(RING_ID)

                # If this is the first connection logged, populate conn_info
                if len(self.conn_info) == 0:
                    self.conn_info = pd.DataFrame(
                        {"RING_Name": RING_Name, "RING_ID": RING_ID}, index=[0]
                    )

                # If this is not the first connection, append to conn_info
                elif len(self.conn_info) > 0:
                    new_conn_info = pd.DataFrame(
                        {"RING_Name": RING_Name, "RING_ID": RING_ID},
                        index=[self.conn_info.index[-1] + 1],
                    )
                    self.conn_info = pd.concat(
                        [self.conn_info, new_conn_info], axis=0, ignore_index=False
                    )

            # If connection exists, notify and provide the connection IDX in the notification
            else:
                idx = self.conn_info[self.conn_info.RING_ID == RING_ID].index[0]
                print(
                    f"IDX {idx:d} -- connection to RING_ID {RING_ID:d}\
                       already established"
                )

        # This shouldn't happen, but if somehow we get here...
        else:
            print(f"Module type {type(self.module)} is incompatable!")
            raise RuntimeError

    ######################################
    ### MODULE OPERATION CLASS METHODS ###
    ######################################

    def start(self):
        """
        Start Module Command
        """
        self._thread.start()

    def stop(self):
        """
        Stop Module Command
        """
        self.runs = False

    def run(self):
        """
        Module Execution Command
        """
        while self.runs:
            if self.module.mod_sta() is False:
                break
            sleep(self.wait_sec)
            # Run Pulse Command inherited from TubeWyrm
            self.pulse()  # conn_in = conn_in, conn_out = conn_out)
        # Polite shut-down of module
        self.module.goodbye()
        print("Exiting HeartWyrm Instance")
