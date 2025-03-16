from thermal_building_model.oemof_facades.base_component import BaseComponent, EconomicsInvestmentComponents, CO2Components
from typing import Optional, Union, List
from oemof import solph
from dataclasses import dataclass
from oemof.network import Bus
from thermal_building_model.helpers.path_helper import get_project_root
import pandas as pd
import os

@dataclass
class RenewableEnergySource(BaseComponent):
    timesteps : float = 3
    nominal_power: Optional[float] = None
    economics_model: Optional[EconomicsInvestmentComponents] = None
    co2_model: Optional[CO2Components] = None
    fixed_data : Optional[List[float]] = None

    def create_source(self, output_bus: Optional[Bus] = None):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        if self.investment:
            epc = self.economics_model.calculate_epc()  # Get EPC from economics model

            return solph.components.Source(
                label=f"{self.name.lower()}",
                outputs={output_bus: solph.Flow(
                    fix = self.fixed_data,
                    nominal_value= solph.Investment(ep_costs=epc,
                                     custom_attributes={
                                         "co2": {
                                             "offset": self.co2_model.offset_capacity if self.co2_model else 0.00,
                                              "cost": self.co2_model.per_capacity if self.co2_model else 0.00
                                              }
                                      }
                        ),
                    )
                }
                ,

            )
        else:
            return solph.components.Source(
                label=f"{self.name.lower()}",
                outputs={
                    output_bus: solph.Flow(
                        fix=self.fixed_data,
                        nominal_value=self.nominal_power)
                }
            )

@dataclass
class PVSystem(RenewableEnergySource):
    name: str = "PVSystem"
    nominal_power: Optional[float] = 1000

    def __post_init__(self):
        main_path = get_project_root()
        self.fixed_data = pd.read_csv(
            os.path.join(
                main_path,
                "thermal_building_model",
                "input",
                "sfh_example",
                "pvwatts_hourly_1kW.csv",
            )
        )["AC System Output (W)"][12:(12+self.timesteps)]
        self.fixed_data = [0,20,0]