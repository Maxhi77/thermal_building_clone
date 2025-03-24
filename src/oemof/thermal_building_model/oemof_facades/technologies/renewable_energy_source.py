from oemof.thermal_building_model.oemof_facades.base_component import BaseComponent, InvestmentComponents
from typing import Optional, List
from oemof import solph
from oemof.network import Bus
from oemof.thermal_building_model.helpers.path_helper import get_project_root
import pandas as pd
import os
from dataclasses import dataclass, field

from oemof.thermal_building_model.input.economics.investment_components import pv_system_config
@dataclass
class RenewableEnergySource(BaseComponent):
    timesteps : float = 3
    nominal_power: Optional[float] = None
    investment_component: Optional[InvestmentComponents] = None
    fixed_data : Optional[List[float]] = None

    def create_source(self, output_bus: Optional[Bus] = None):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        self.oemof_component_name = f"{self.name.lower()}_source"
        self.output_bus = output_bus
        if self.investment:
            epc = self.investment_component.calculate_epc()  # Get EPC from economics model

            return solph.components.Source(
                label=self.oemof_component_name ,
                outputs={output_bus: solph.Flow(
                    fix = self.fixed_data,
                    nominal_value= solph.Investment(ep_costs=epc,
                                                    maximum=self.investment_component.maximum_capacity,
                                                    minimum=self.investment_component.minimum_capacity,
                                                    offset=self.investment_component.cost_offset,
                                                    nonconvex=True,
                                     custom_attributes={
                                         "co2": {
                                             "offset": self.investment_component.co2_offset if self.investment_component else 0.00,
                                              "cost": self.investment_component.co2_per_capacity if self.investment_component else 0.00
                                              }
                                      }
                        ),
                    )
                }
                ,

            )
        else:
            return solph.components.Source(
                label=self.oemof_component_name ,
                outputs={
                    output_bus: solph.Flow(
                        fix=self.fixed_data,
                        nominal_value=self.nominal_power)
                }
            )

    def post_process(self,results,component):
        capacity, invest_status = self.get_capacity(results,component)
        investment_cost = self.get_investment_cost(capacity,invest_status)
        investment_co2 = self.get_investment_co2(capacity,invest_status)
        flow_from_grid = self.get_flow_from_grid(results,component)
        return {"capacity":capacity,
                "investment_cost":investment_cost,
                "investment_co2":investment_co2,
                "flow_from_grid":flow_from_grid}

    def get_capacity(self,results, component):
        if self.investment:
            return (solph.views.node(results, self.output_bus)[
                "scalars"][ ((component, self.output_bus), "invest")],
                    solph.views.node(results, self.output_bus)["scalars"].get(((component, self.output_bus), "invest_status"), 0))
        else:
            return component.outputs[self.output_bus].nominal_capacity,0

    def get_investment_cost(self,capacity,invest_status):
        if self.investment:
            return capacity * self.investment_component.cost_per_unit + self.investment_component.cost_offset * invest_status
        else:
            return 0
    def get_investment_co2(self, capacity, invest_status):
        if self.investment:
            if self.investment_component.co2_offset > 0 and invest_status == 0 and capacity > 0:
                raise ValueError(f"Error: 'invest_status' is None/0, so NonConvex=False, but co2_offset > 0 for component {self.name}")
            else:
                invest_status = 0
            return capacity * self.investment_component.co2_per_capacity + self.investment_component.co2_offset * invest_status
        else:
            return 0
    def get_flow_from_grid(self,results,component):
        return results[component, self.output_bus]["sequences"]["flow"]

@dataclass
class PVSystem(RenewableEnergySource):
    name: str = "PVSystem"
    nominal_power: Optional[float] = 1000
    investment_component: InvestmentComponents = field(default_factory=lambda: pv_system_config)
    def __post_init__(self):
        if self.fixed_data is None:
            main_path = get_project_root()
            self.fixed_data = pd.read_csv(
                os.path.join(
                    main_path,
                    "thermal_building_model",
                    "input",
                    "sfh_example",
                    "pvwatts_hourly_1kW.csv",
                )
            )["AC System Output (W)"] / 1000