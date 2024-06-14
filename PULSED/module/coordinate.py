"""
:module: PULSED.module.coordinate
:author: Nathan T. Stevens
:email: ntsteven@uw.edu
:org: Pacific Northwest Seismic Network
:license: AGPL-3.0
:purpose:


Classes
-------
:class:`~PULSED.module.coordinate.PULSED_EW`
"""
import threading, logging, time, sys, configparser, inspect
from PULSED.util.pyew import is_wave_msg
from PULSED.module.bundle import SequenceMod
from PULSED.module.transact import PyEWMod

Logger = logging.getLogger(__name__)

###################################################################################
# PULSED CLASS DEFINITION ########################################################
###################################################################################
class PulsedMod_EW(SequenceMod):
    """
    The PULSED_EW class comprises an extended :class:`~PyEW.EWModule` object
    (:class:`~PULSED.module.ew_transact.PyEWMod`) and a sequence of PULSED modules
    that make an operational python module that communicates with the Earthworm message transport system
    
    This class inherits its sequencing methods and attributes from :class:`~PULSED.wyrms.sequencewyrm.sequenceWyrm`
    

    :param wait_sec: number of seconds to wait between pulses, defaults to 0
    :type wait_sec: int, optional
    :param default_ring_id: default ring ID to assign to PULSEDule, defaults to 1000
    :type default_ring_id: int, optional
    :param module_id: module ID that Earthworm will see for this PULSEDule, defaults to 193
    :type module_id: int, optional
    :param installation_id: installation ID, defaults to 255 - anonymous/nonexchanging installation
    :type installation_id: int, optional
    :param heartbeat_period: time in seconds between heartbeat message sends from this module to Earthworm, defaults to 15
    :type heartbeat_period: int, optional
    :param extra_connections: dictionary with {'NAME': RING_ID} formatting for additional Py<->EW connections
        to make in addition to the 'DEFAULT': default_ring_id connection
        defaults to {'WAVE': 1000, 'PICK': 1005}
    :type: dict, optional
    :param ewmodule_debug: should debugging level logging messages within the PULSEDule object
        be included if logging level is set to DEBUG? Defaults to False.
        (acts as an extra nit-picky layer for debugging)
    :type ewmodule_debug: bool, optional
    """

    def __init__(self, config_file):
        """Create a PULSED object
        Inherits the mod_dict attribute and pulse() method from sequenceWyrm

        :param wait_sec: number of seconds to wait between completion of one pulse sequence of
            the Wyrm-like objects in self.mod_dict and the next, defaults to 0
        :type wait_sec: float, optional
        :param default_ring_id: default ring ID to assign to EWModule, defaults to 1000
        :type default_ring_id: int, optional
        :param module_id: module ID that Earthworm will see for this EWModule, defaults to 200
        :type module_id: int, optional
        :param installation_id: installation ID, defaults to 255 - anonymous/nonexchanging installation
        :type installation_id: int, optional
        :param heartbeat_period: send heartbeat message to Earthworm every X seconds, defaults to 15
        :type heartbeat_period: int, optional
        :param mod_dict: dictionary of PULSED.core.wyrms-type objects that will be executed in a chain , defaults to {}
        :type mod_dict: dict, optional
            also see PULSED.core.wyrms.sequencewyrm.sequenceWyrm
        :param submodule_wait_sec: seconds to wait between execution of the **pulse** method of each
            Wyrm-like object
        """
        # Initialize config parser
        self.cfg = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation()
        )
        # Read configuration file
        self.cfg.read(config_file)

        # Ensure minimum required fields are present for module initialization
        demerits = 0
        for _rs in ['Earthworm','PULSED','Sequence']:
            if _rs not in self.cfg._sections.keys():
                Logger.critical(f'section {_rs} missing from config file! Will not initialize PULSED')
                demerits += 1
        if demerits > 0:
            sys.exit(1)
        else:
            Logger.debug('config file has all required sections')

        # Initialize PULSEDPyEWModule Object
        self.module = PULSEDModule(
            connections = eval(self.cfg.get('PULSED','connections')),
            module_id = self.cfg.getint('Earthworm', 'MOD_ID'),
            installation_id = self.cfg.getint('Earthworm', 'INST_ID'),
            heartbeat_period = self.cfg.getfloat('Earthworm', 'HB'),
            deep_debug = self.cfg.getboolean('PULSED', 'deep_debug')
        )        
        # Create a thread for the module process
        try:
            self.module_thread = threading.Thread(target=self.run)
        except:
            Logger.critical('Failed to start thread')
            sys.exit(1)
        Logger.info('PULSEDModule initialized')

        # Sequence submodules
        mod_dict = {}
        demerits = 0

        # Iterate across submodule names and section names
        for submod_name, submod_section in self.cfg['Sequence'].items():
            # Log if there are missing submodules
            if submod_section not in self.cfg._sections.keys():
                Logger.critical(f'submodule {submod_section} not defined in config_file. Will not compile!')
                demerits += 1
            # Construct if the submodule has a section
            else:
                # Parse the class name and __init__ kwargs
                submod_class, submod_init_kwargs = \
                    self.parse_config_section(submod_section)
                # Run import to local scope
                parts = submod_class.split('.')
                path = '.'.join(parts[:-1])
                clas = parts[-1]
                try:
                    exec(f'from {path} import {clas}')
                except ImportError:
                    Logger.critical(f'failed to import {submod_class}')
                    sys.exit(1)
                submod_object = eval(clas)(**submod_init_kwargs)
                # Attach object to mod_dict
                mod_dict.update({submod_name: submod_object})
                Logger.info(f'{submod_name} initialized')
        # If there are any things that failed to compile, exit
        if demerits > 0:
            sys.exit(1)
        
        PULSED_init = self.parse_config_section('PULSED')
        sequence_params = inspect.signature(SequenceMod).parameters
        sequence_init = {'mod_dict': mod_dict}
        for _k, _v in PULSED_init.items():
            if _k in sequence_params.keys():
                sequence_init.update({_k: _v})

        # Initialize SequenceMod inheritance
        super().__init__(**sequence_init)

        # Set runs flag to True
        self.runs = True
        Logger.critical('ALL OK - PULSED Initialized!')

    ###########################################
    ### MODULE CONFIGURATION PARSING METHOD ###
    ###########################################
        
    def parse_config_section(self, section):
        submod_init_kwargs = {}
        submod_class = None
        for _k, _v in self.cfg[section].items():
            # Handle special case where class is passed
            if _k == 'class':
                submod_class = _v
            # Handle special case where module is passed
            elif _k == 'module':
                _val = self.module
            # Handle case where the parameter value is bool-like    
            elif _v in ['True', 'False', 'yes', 'no']:
                _val = self.cfg.getboolean(section, _k)
            # For everything else, use eval statements
            else:
                _val = eval(self.cfg.get(section, _k))
            
            if _k != 'class':
                submod_init_kwargs.update({_k: _val})
        
        if submod_class is None:
            return submod_init_kwargs
        else:
            return submod_class, submod_init_kwargs

    ######################################
    ### MODULE OPERATION CLASS METHODS ###
    ######################################

    def start(self):
        """
        Start Module Command
        runs ```self._thread.start()```
        """
        if len(self.mod_dict) == 0:
            Logger.warning('No Wyrm-type sub-/base-modules contained in this PULSED Module')
        self.module_thread.start()

    def stop(self):
        """
        Stop Module Command
        sets self.runs = False
        """
        self.runs = False

    def run(self, input=None):
        """
        Run the PyEW.EWModule housed by this PULSED with the option
        of an initial input that is shown to the first wyrm in 
        this PULSED' mod_dict attribute.

        :param input: input for the pulse() method of the first wyrm in PULSED.mod_dict, default None
        :type input: varies, optional
        """
        Logger.critical("Starting Module Operation")     
        print('Im doing science')   
        while self.runs:
            if self.module.mod_sta() is False:
                break
            time.sleep(0.001)
            if self.module.debug:
                Logger.debug('running PULSED pulse')
            # Run pulse inherited from sequenceWyrm
            _ = super().pulse(input)
        # Note shutdown in logging
        Logger.critical("Shutting Down Module") 
        # Gracefully shut down
        self.module.goodbye()
    

    def pulse(self):
        """
        Overwrites the inherited :meth:`~PULSED.wyrms.sequencewyrm.sequencewyrm.pulse` method
        that broadcasts a pair of logging errors pointing to use PULSED.run()
        as the operational 
        """        
        Logger.error("pulse() method disabled for PULSED.core.PULSED.PULSED")
        Logger.error("Use PULSED.run() to start module operation")
        return None, None