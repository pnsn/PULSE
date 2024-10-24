# PULSE  
# ~~|^v~~~  
## **P**rocessing (**P**ython) **U**tility for **L**ive **S**eismic **E**vents  
Integrating emerging python seismic analysis codes into live-streaming seismic data workflows.

## About  
PULSE is an open-source python project that provides an adaptable framework for integrating python-based seismic analysis tools into live-streaming seismic data analysis systems. This initial version of the project focuses on integrating machine-learning enhanced phase detection and labeling workflows hosted in [`SeisBench`](https://seisbench.readthedocs.io/en/stable/) into [`Earthworm`](http://www.earthwormcentral.org). In future releases we hope to incorporate hosting capabilities for computationally efficient phase association and denoising workflows.

PULSE workflows center around sequences of single-task modules that progressively process data objects as they become available. This cascading data flow operates in discrete pulses (via the **pulse** class method for each module) that can be tuned Each module has a **pulse** method that conducts some number of actions 

PULSE uses and augments popular Python API's for routine seismic data analyses ([`ObsPy`](https://docs.obspy.org) and [`NumPy`](https://numpy.org)) to provide familar  and the key open-source package [`PyEarthworm`](https://github.com/Boritech-Solutions/PyEarthworm) for Python/Earthworm integration.

In future releases we plan to incorporate 

**We thank each of these development teams for their dedication to open-source scientific software.**  
### License
This project is distributed under a GNU Affero General Public License (AGPL-3.0) to comform with licensing terms of its key dependencies and inspirations.  
<a title="Affero General Public License" href="https://en.wikipedia.org/wiki/GNU_Affero_General_Public_License">
    <img width="256" alt="AGPLv3 Logo" src="https://upload.wikimedia.org/wikipedia/commons/0/06/AGPLv3_Logo.svg">
</a>  

# Getting Started

PULSE consists of a collection of single-task-oriented module classes housed in `PULSE.module`,
modified ObsPy data classes housed in `PULSE.data`, and pre-composed sequences of modules housed
in `PULSE.sequences`. Supporting python methods are housed in `PULSE.util`

 Supporting methods

## For new users 
We recommend installing `PULSE` and working through the **Pure-Python Tutorials** first to get familiar with the python-side aspects of the API.  
Once you're comfortable with these parts of the project, proceed with installing `Earthworm`, a Test Suite dataset, and `PyEarthworm` and try out the **Earthworm-Integrated Tutorials**

### Installation Instructions  

### Installing `PULSE`
We recommend creating a `conda` environment with clean installs of `pip` and `git` for the current distribution:  
```
conda create --name PULSE pip git
conda activate PULSE
pip install git+https://github.com/pnsn/PULSE.git@develop
``` 

#### Pure-Python Tutorials (No Earthworm Required)

| Examples                        | Source Data  |  Notebook    | Reference                    |  
| ------------------------------- | ------------ | ------------ | ---------------------------- |
| Introduction to PULSE Data Classes | local | PLACEHOLDER | | 
| ObsPy Signal Processing | local        | PLACEHOLDER  |                              |
| PhaseNet on One Station         | local        | PLACEHOLDER  | [Retailleau et al. (2022)](https://doi.org/10.1785/0220210279)   |
| EQTransformer on Many Stations  | local        | PLACEHOLDER  | [Ni et al. (2023)](https://doi.org/10.26443/seismica.v2i1.368) | 
| Ensembling Model Predictions    | local        | PLACEHOLDER  | [Yuan et al. (2023)](https://doi.org/10.1109/TGRS.2023.3320148) | 
| PhaseNet + GaMMA Pick/Associate | local        | PLACEHOLDER  | |


### Installing `Earthworm` and a Test Suite
Follow  
* Directions on Earthworm 7.10 installation can be found [here](https://gitlab.rm.ingv.it/earthworm/earthworm)  
* The Univerity of Memphis Test Suite can be downloaded directly [here] (http://www.earthwormcentral.org/distribution/memphis_test.zip)

**NOTE**: The PNSN is developing an PNW test suite to showcase PULSE' functionalities. Stay tuned!  

### Installing `PyEarthworm`
#### `pip` install from `main`
**NOTE**: This is an abstraction from the PyEarthworm install instructions, refer to their repository for authoritative installation instructions  

Source your `Earthworm` OS-specific environment (e.g., for the Memphis Test Suite example installed on a Mac)     
```
source /usr/local/earthworm/memphis/params/ew_macosx.bash
```

Install `PyEarthworm` from `main`  
```
pip install git+https://github.com/Boritech-Solutions/PyEarthworm
```  

#### Earthworm Integrated Tutorials  

| Examples                        | Source Data  |  Notebook    | 
| ------------------------------- | ------------ | ------------ |
| PhaseNet RING2DISK Prediction   | Tankplayer   | PLACEHOLDER  | 
| ObsPy Picker RING2RING          | Tankplayer   | PLACEHOLDER  |
| PhaseNet Picker RING2RING       | TankPlayer   | PLACEHOLDER  | 
| Ensemble Picker RING2RING       | TankPlayer   | PLACEHOLDER  |
| GaMMA Association RING2RING     | TankPlayer   | PLACEHOLDER  |
| PhaseNet + GaMMA RING2RING        | TankPlayer   | PLACEHOLDER  |


## Installation In A Nutshell (For Experienced Users)
```
conda create --name PULSE pip git
```
```
conda activate PULSE
```
```
pip install git+https://github.com/pnsn/PULSE@develop
```
```
source </path/to/your/ew_env.bash>
```
```
pip install git+https://github.com/Boritech-Solutions/PyEarthworm
```

## Adding Visualization Tools for `class DictStream` (For Experienced Users)  
PULSE includes data visualization methods for the `DictStream` class that use elements of the [Pyrocko](https://pyrocko.org) project, namely `snuffler`. To add these tools to the environment described above, install the Pyrocko library following their instructions [here](https://pyrocko.org/docs/current/install/). These functionalities are not required for typical module operation with PULSE, but users may find them handy.  

```
conda install -c pyrocko pyrocko
```

# Documentation (Work In Progress)  
Sphinx documentation in ReadTheDocs formatting is under construction - stay tuned!  
Resource: https://sphinx-rtd-tutorial.readthedocs.io/en/latest/  


<!-- ### Install with `conda`  
The same as above, but using a *.yaml  
```
wget https://github.com/pnsn/PULSE/conda_env_create.yaml
``` -->



# Additional Information

## Primary Developer  
Nathan T. Stevens  
email: ntsteven (at) uw.edu  
org: Pacific Northwest Seismic Network

## Project Dependencies & Resources
[`Earthworm`](http://www.earthwormcentral.org)  
[`NumPy`](https://numpy.org)  
[`ObsPy`](https://docs.obspy.org)  
[`PyEarthworm`](https://github.com/Boritech-Solutions/PyEarthworm)  
[`PyEarthworm Workshop`](https://github.com/Fran89/PyEarthworm_Workshop)  
[`Pyrocko`](https://pyrocko.org)  
[`SeisBench`](https://github.com/seisbench/seisbench)  

## Branching Plan/Development Notes

Current development version: ALPHA 

The current developmental version of this code is hosted on the `develop` branch. Starting with version 0.0.1 the `main` branch will host deployment read code, `develop` will contain code that is in beta (debug only), and subsidiary `feature-*` branches will host new functionalities under development..  

Developed with Python 3.1X, Apple M2 chipset, and Earthworm 7.10  


<!-- ## Notes on the Initial Package Development
This initial version focuses on body wave detection and labeling tasks using the EarthquakeTransformer (EQT; Mousavi et al., 2018) and PhaseNet (Zhu et al., 2019) model architectures, along with the following pretrained model weights available through `SeisBench` (Woollam et al., 2020).

| Model  | Weight   | Appeal                              | Reference               | DOI |
|:------:| -------- | ----------------------------------- | ----------------------- | ------ |
| EQT    | pnw      | PNSN Data Transfer Learning         | Ni et al. (2023)        | https://doi.org/10.26443/seismica.v2i1.368 |
| EQT/PN | instance | Extensive Training Augmentation     | Michelini et al. (2021) | https://doi.org/10.13127/INSTANCE |
| EQT/PN | stead    | "Go-To" Benchmark Training Dataset  | Mousavi et al. (2019)   | https://doi.org/10.1109/ACCESS.2019.2947848 |
| EQT/PN | iquique  | Subduction Zone Aftershock Sequence | Woollam et al. (2019)   | https://doi.org/10.1785/0220180312 |
| EQT/PN | lendb    | Local Seismicity                    | Magrini et al. (2020)   | https://doi.org/10.1016/j.aiig.2020.04.001; http://doi.org/10.5281/zenodo.3648232 |
| PN     | diting   | Large mag range & event diversity   | Zhao et al. (2022)      | https://doi.org/10.1016/j.eqs.2022.01.022 |  

Abstracted from `SeisBench` documentation: https://seisbench.readthedocs.io/en/stable/pages/benchmark_datasets.html#  
 -->
