from dataclasses import dataclass
from oemof import solph
from typing import Optional, Union, List
from oemof.thermal_building_model.helpers.path_helper import get_project_root
import pandas as pd
import os
@dataclass
class Demand:
    name: str
    nominal_value = 1
    bus: Optional[Union[solph.buses.Bus]] = None
    value_list: List = None
    level: int = None


    def create_demand(self) -> solph.components.Sink:
        """Creates a solph sink with revenue as variable cost."""
        if self.level:
            # Ensure `self.bus` is a dictionary
            if isinstance(self.bus, dict):
                assert (isinstance(self.bus, dict) or
                        len(self.bus) == 1), ("Expected self.bus to be a dictionary with one entry, "
                                                    "when self.levle is defined.")
                # Extract the single key-value pair
                bus_level, bus = next(iter(self.bus.items()))
                # Ensure `self.level` matches the key of the bus dictionary
                assert self.level == bus_level, (f"Expected self.level ({self.level}) to match "
                                                 f"the bus key ({bus_level}).")
            elif isinstance(self.bus, solph.buses.Bus):
                # If `self.bus` is a single Bus instance, skip the dictionary check
                bus = self.bus
            else:
                raise TypeError("self.bus must be either a dictionary or a single Bus object.")
            self.oemof_component_name = f"{self.name.lower()}_lvl{self.level}_demand"
            return solph.components.Sink(
                label=f"{self.name.lower()}_lvl{self.level}_demand",
                inputs={bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value
                )}
            )
        else:
            self.oemof_component_name = f"{self.name.lower()}_demand"
            return solph.components.Sink(
                label=f"{self.name.lower()}_demand",
                inputs={self.bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value
                )
                }
            )
    def get_oemof_component_name(self):
        return self.oemof_component_name
@dataclass
class ElectricityDemand(Demand):
    name: str = "Electricity"

    def __post_init__(self):
        if self.value_list is None:
            main_path = get_project_root()
            # Elect Demand
            df_elect = pd.read_csv(
                os.path.join(
                    main_path,
                    "thermal_building_model",
                    "input",
                    "sfh_example",
                    "SumProfiles.Electricity.csv",
                ),
                delimiter=";",
            )
            elect_demand_df = (
                df_elect.groupby(df_elect.index // 60)["Sum [kWh]"]
                .sum()
                .to_frame(name="Hourly_Sum")["Hourly_Sum"]
            )
            elect_demand_in_watt = elect_demand_df * 1000
            self.value_list = elect_demand_in_watt
@dataclass
class HeatDemand(Demand):
    name: str = "Heat"
    level:float = 30

@dataclass
class WarmWater(Demand):
    name: str = "WarmWater"
    base_temperature:float = 35
    demand_temperature:float = 10

    def __post_init__(self):
        if self.value_list is None:
            main_path = get_project_root()
            df_warm_water = pd.read_csv(
                os.path.join(
                    main_path,
                    "thermal_building_model",
                    "input",
                    "sfh_example",
                    "SumProfiles.Warm Water.csv",
                ),
                delimiter=";",
            )
            warm_water_demand_df = (
                df_warm_water.groupby(df_warm_water.index // 60)["Sum [L]"]
                .sum()
                .to_frame(name="Hourly_Sum")["Hourly_Sum"]
            )
            heat_capacity_water = 4.18  # [kJ/(kg/K)
            warm_water_demand_in_watt = (
                    (35 - 10) * heat_capacity_water * warm_water_demand_df * (1000 / 3600)
            )
            self.value_list = warm_water_demand_in_watt

