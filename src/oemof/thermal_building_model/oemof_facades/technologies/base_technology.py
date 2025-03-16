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

class CHP:
    def create_converter(self,input_bus:Bus,
                         output_bus: Bus,
                         conversion_factor_input:float=1,
                         conversion_factor_output:float=1) -> solph.components.Converter:
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        if self.investment:
            if self.investment:
                epc = self.economics_model.calculate_epc()  # Get EPC from economics model

                return solph.components.Converter(
                    label=f"{self.name.lower()}_resource",
                    inputs={input_bus: solph.Flow()},
                    outputs={input_bus: solph.Flow(
                        custom_attributes={"co2": self.co2_model.per_flow if self.co2_model else 0.00},
                        nominal_value=solph.Investment(
                            maximum=self.economics_model.maximum_capacity,
                            minimum=self.economics_model.maximum_capacity,
                            ep_costs=epc,
                            nonconvex=True,
                            custom_attributes={
                                "co2": {
                                    "offset": self.co2_model.offset_capacity if self.co2_model else 0.00
                                },
                                "cost": self.co2_model.per_capacity if self.co2_model else 0.00
                            }
                        )
                    )},
                    conversion_factors={input_bus: conversion_factor_input, output_bus: conversion_factor_output},
                    # ✅ Fixed conversion factors
                )
        else:
            return solph.components.Converter(
                label=f"{self.name.lower()}_resource",
                inputs={input_bus: solph.Flow()},
                outputs={input_bus: solph.Flow()},
                conversion_factors={input_bus: conversion_factor_input, output_bus: conversion_factor_output},
            )