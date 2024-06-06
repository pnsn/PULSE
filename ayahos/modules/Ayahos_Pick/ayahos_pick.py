import configparser, logging, sys
from ayahos import Ayahos
from ayahos.submodules import WaveInWyrm, SBMTubeWyrm, PickOutWyrm
import seisbench.models as sbm

Logger = logging.getLogger(__name__)

class AyahosPick(Ayahos):
    """
    This module-defining class inherits from the :class:`~ayahos.core.ayahos.Ayahos` class,
    hosts a sequence of sub-modules to create a ring-to-ring style processing workflow wherein
    P- and S- wave detection and labeling is conducted with a Machine Learning model. All arguments
    are passed to the submodules via a configparser formatted config file (ayahos_pick.d)

    Submodules:
        - 'Ayahos' -- :class:`~ayahos.core.ayahos.Ayahos` (super())
            Hosts the :class:`~ayahos.core.ayahosewmodule.AyahosEWModule`
            object that brokers Python<->Earthworm data exchanges and runs
            the module

        - 'WaveInWyrm' -- :class:`~ayahos.submodule.waveinwyrm.WaveInWyrm`
            Hosts a sequence of wyrm-type objects that read TYPE_TRACEBUFF2
            messages from a WAVE RING and conducts on-the-fly organization
            and buffering of messages into :class:`~ayahos.core.MLTraceBuffer`
            objects keyed on their S.N.C.L
            Base Modules:
                - class:`~ayahos.wyrms.ringwyrm.RingWyrm`,
                - :class:`~ayahos.wyrms.bufferwyrm.BufferWyrm`
            housed in a :class:`~ayahos.wyrms.tubewyrm.TubeWyrm` object
            
        - 'SBMTubeWyrm' -- :class:`~ayahos.submodule.sbmtubewyrm.SBMTubeWyrm`
            Hosts the on-the-fly windowing, waveform pre-processing and machine
            learning based phase detection and labeling with a sequence of
                - :class:`~ayahos.wyrms.windowwyrm.WindowWyrm`
                    windowing
                - :class:`~ayahos.wyrms.methodwyrm.MethodWyrm`
                    several instances for preprocessing tasks
                - :class:`~ayahos.wyrms.sbmwyrm.SBMWyrm
                    prediction
            housed in a :class:`~ayahos.wyrms.tubewyrm.TubeWyrm` object

        - 'PickOutWyrm' -- :class:`~ayahos.submodule.pickoutwyrm.PickOutWyrm`
            Host a sequence of wyrm-type objects that buffer prediction traces
            for P- and S- wave onset labels, conduct on-the-fly triggering and 
            phase picking, format picks into TYPE_PICK2K message formats and
            submit picks to the EW PICK RING.
            Base Modules:
                - :class:`~ayahos.wyrms.bufferwyrm.BufferWyrm`
                - :class:`~ayahos.wyrms.pickwyrm.PickWyrm`
                - :class:`~ayahos.wyrms.ringwyrm.RingWyrm`
            housed in a :class:`~ayahos.wyrms.tubewyrm.TubeWyrm` object
        """
    def __init__(self, config_file):
        init_kwargs = self.parse_config(config_file)
        # Nitpicky check to make sure only one model/weight combination is passed for this module
        # TODO: Need to implement a simple way to merge different model/weight's predictions
        wn = init_kwargs['SBMTubeWyrm']['weight_names']
        if isinstance(wn, list):
            if len(wn) > 1:
                Logger.error('This module only supports a single model/weight combination')
                Logger.error('weight_names in the config file should be a single element list')
                sys.exit(1)
        elif not isinstance(wn, str):
            Logger.error('weight_names must be type str or a list-like comprising 1 string')
            sys.exit(1)
        else:
            pass
        # Initialize Ayahos inheritance
        try:
            super().__init__(**init_kwargs['Ayahos'])
        except:
            Logger.critical('Could not initialize super()')
            sys.exit(1)
        # Initialize WaveInWyrm
        try:
            wiw = WaveInWyrm(self.module, **init_kwargs['WaveInWyrm'])
        except:
            Logger.critical('Could not initialize WaveInWyrm')
            sys.exit(1)
        # Initialize SeisBenchModelTubeWyrm
        try:
            stw = SBMTubeWyrm(**init_kwargs['SBMTubeWyrm'])
        except:
            Logger.critical('Could not initialize SBMTubeWyrm')
            sys.exit(1)
        try:
            pow = PickOutWyrm(self.module, **init_kwargs['PickOutWyrm - aborting'])
        except:
            Logger.critical('Could not initialize PickOutWyrm - aborting')
        Logger.info('Submodules successfully initialized - appending to AyahosPick.wyrm_dict')
        wyrm_dict = {
            'input':wiw, 'proc': stw, 'output': pow}
        self.update(wyrm_dict)
