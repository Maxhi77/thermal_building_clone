from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Union
import pandas as pd
from pyomo.common.enums import maximize
from thermal_building_model.oemof_facades.base_component import BaseComponent

from oemof import solph
from oemof.network import Bus

@dataclass
class Technology(BaseComponent):
    input_bus: Optional[Bus] = None
    output_bus: Optional[Bus] = None
    nominal_capacity: float = False

@dataclass
class RenewableEnergySource(Technology):
    name:str = "RenewableEnergySource"

@dataclass
class ElectricBoiler(Technology):
    carrier: str = "ElectricBoiler"
    maximum_temperature: float = 90
    minimum_temperature: float = 10
    efficiency: float = 1

@dataclass
class DistrictHeatingGridConnection(Technology):
    max_supply_temp: float = 135.0  # °C
    min_supply_temp: float = 50.0   # °C (todo: check 80.0)
    min_delta_temp: float = 40.0    # K (todo: check 55.0)


@dataclass
class Photovoltaics(Technology):
    location: Tuple[float, float] = (55.0, 10.0)
    weather: Union[Dict[str, float], pd.DataFrame, None] = None
    surface_tilt: float = 35.0
    surface_azimuth: float = 180.0
    fixed: bool = True
    co2_per_unit = 0.91

class AirWaterHeatPumpConfig:
    cop_0_35: float = 4.6
    max_temp_primary: int = 25
    min_temp_primary: int = -10 #-20.0
    min_delta_temp_primary: int = 5
    max_temp_secondary: int = 70
    min_temp_secondary: int = 5 #5.0
    min_delta_temp_secondary: int = 5
    minimal: bool = False
