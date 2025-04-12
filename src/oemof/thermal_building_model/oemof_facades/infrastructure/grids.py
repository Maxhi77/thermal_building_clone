from oemof import solph
from typing import Optional, Union, List
import copy
from oemof.thermal_building_model.oemof_facades.base_component import  InvestmentComponents
from dataclasses import dataclass, field
from oemof.thermal_building_model.oemof_facades.base_component import GridComponents
from oemof.thermal_building_model.input.economics.operation_grid_economics import gas_grid_config,electricity_grid_config,heat_grid_config
from oemof.thermal_building_model.input.economics.investment_components import heat_grid_config as heat_grid_config_inv
'''
CO2 in kg/kWh
prices in: Euro/kWh

more CO2-values for future Grids:
    name: str ="CO2"
    gas: float = 0.201
    oil: float = 0.288
    heat: float = 0.280
    pellets: float = 0.036
    electricity: float = 0.420
    wood: float = 0.027
'''

@dataclass
class Grid:
    name: str
    investment: bool = False
    analysis_period: Optional[int] = None
    max_peak_from_grid: Optional[float] = None
    max_peak_into_grid: Optional[float] = None# Number of years for price adjustment
    bus_from_grid: Optional[Union[solph.buses.Bus, List[solph.buses.Bus]]] = None
    bus_into_grid: Optional[Union[solph.buses.Bus, List[solph.buses.Bus]]] = None
    investment_component: Optional[InvestmentComponents] = None
    operation_grid: Optional[GridComponents] = None

    def __post_init__(self):
        self.bus_from_grid = solph.buses.Bus(label=f"b_{self.name.lower()}_from_grid")
        self.bus_into_grid = solph.buses.Bus(label=f"b_{self.name.lower()}_into_grid")
        self.name_source = None
        self.name_sink = None
    def get_bus_from_grid(self):
        return self.bus_from_grid
    def get_bus_into_grid(self):
        return self.bus_into_grid
    def calculate_average_price(self, base_price: float) -> float:
        """Calculates the average price over the analysis period using exponential growth."""
        if self.analysis_period is None or self.operation_grid.price_change_factor == 0:
            return base_price  # No adjustment needed

        n = self.analysis_period
        growth_rate = self.operation_grid.price_change_factor

        # Exponential increase formula: P_t = P_0 * (1 + g)^t
        total_price = sum(base_price * (1 + growth_rate) ** t for t in range(n))
        return total_price / n  # Average price over period

    def create_source(self) -> solph.components.Source:
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        price = self.calculate_average_price(self.operation_grid.working_rate)
        self.name_source = f"{self.name.lower()}_from_grid"
        if self.investment:
            epc = self.investment_component.calculate_epc()  # Get EPC from economics model

            return solph.components.Source(
                label=f"{self.name.lower()}_from_grid",
                outputs={self.bus_from_grid: solph.Flow(
                    variable_costs=price,
                    custom_attributes={"co2": self.operation_grid.co2_per_flow if self.operation_grid else 0.00},
                    nominal_value=solph.Investment(
                        maximum=self.investment_component.maximum_capacity,
                        minimum=self.investment_component.minimum_capacity,
                        offset=self.investment_component.cost_offset,
                        ep_costs=epc,
                        custom_attributes= {"co2":{"offset": self.investment_component.co2_offset if self.investment_component.co2_offset else 0.00,
                                                    "cost":  self.investment_component.co2_per_capacity if self.investment_component.co2_per_capacity else 0.00}},
                        nonconvex=True,
                    )

                )}
            )
        else:
            return solph.components.Source(
                label=f"{self.name.lower()}_from_grid",
                outputs={self.bus_from_grid: solph.Flow(variable_costs=price,
                                              custom_attributes={"co2": self.operation_grid.co2_per_flow if self.operation_grid else 0.00},
                                                        nominal_value=self.max_peak_from_grid),},
            )

    def create_sink(self) -> solph.components.Sink:
        """Creates a solph sink with revenue as variable cost."""
        price =  self.calculate_average_price(self.operation_grid.revenue)
        self.name_sink = f"{self.name.lower()}_into_grid"
        return solph.components.Sink(
            label=self.name_sink,
            inputs={self.bus_into_grid: solph.Flow(variable_costs= - price,
                                         custom_attributes={"co2": - self.operation_grid.co2_per_flow if self.operation_grid else 0.00},
                                                   nominal_value=self.max_peak_into_grid)},
        )
    def get_oemof_component_names(self):
        names = {"source":self.name_source,
                 "sink":self.name_sink}
        return names

    def post_process(self,
                     results,
                     component_source:solph.components.Source = None,
                     component_sink:solph.components.Sink = None):

        capacity, invest_status = self.get_capacity(results,component_source)
        investment_cost = self.get_investment_cost(capacity,invest_status)
        investment_co2 = self.get_investment_co2(capacity,invest_status)
        if component_source is not None:
            assert isinstance(component_source, solph.components.Source)
            flow_from_grid = self.get_flow_from_grid(results,component_source)
            flow_from_grid_co2 = self.get_flow_co2(flow_from_grid)
            flow_from_grid_cost = self.get_flow_from_grid_cost(flow_from_grid)
        else:
            flow_from_grid = None
            flow_from_grid_co2 = None
            flow_from_grid_cost = None
        if component_sink is not None:
            assert isinstance(component_sink, solph.components.Sink)
            flow_into_grid = self.get_flow_into_grid(results, component_sink)
            flow_into_grid_co2 = self.get_flow_co2(flow_into_grid)
            flow_into_grid_revenue = self.get_flow_into_grid_revenue(flow_into_grid)
        else:
            flow_into_grid = None
            flow_into_grid_co2 = None
            flow_into_grid_revenue = None

        return {"capacity":capacity,
                "investment_cost":investment_cost,
                "investment_co2":investment_co2,
                "flow_from_grid":flow_from_grid,
                "flow_into_grid":flow_into_grid,
                "flow_from_grid_cost": flow_from_grid_cost,
                "flow_into_grid_revenue": flow_into_grid_revenue,
                "flow_from_grid_co2":flow_from_grid_co2,
                "flow_into_grid_co2":flow_into_grid_co2,
                "peak_into_grid": max(flow_into_grid) if flow_into_grid is not None else None,
                "peak_from_grid": max(flow_from_grid) if flow_from_grid is not None else None,}
    def get_capacity(self,results,component):
        if self.investment:
            return (solph.views.node(results, self.bus_from_grid)[
                "scalars"][ ((component, self.bus_from_grid), "invest")]
                    ,solph.views.node(results, self.bus_from_grid)["scalars"].get(((component, self.bus_from_grid), "invest_status"), 0))
        else:
            return component.outputs[self.bus_from_grid].nominal_capacity, 0
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
    def get_flow_co2(self, flow_grid):
        return flow_grid.sum() * self.operation_grid.co2_per_flow
    def get_flow_from_grid_cost(self, flow_grid):
        return flow_grid.sum() * self.operation_grid.working_rate
    def get_flow_into_grid_revenue(self, flow_grid):
        return flow_grid.sum() * self.operation_grid.revenue
    def get_flow_from_grid(self,results,component):
        return results[component, self.bus_from_grid]["sequences"]["flow"]
    def get_flow_into_grid(self,results,component):
        return results[self.bus_into_grid, component]["sequences"]["flow"]

@dataclass
class GasGrid(Grid):
    name: str = "Gas"
    primary_energy_factor: float = 6.2
    operation_grid: GridComponents = field(default_factory=lambda: copy.deepcopy(gas_grid_config))

@dataclass
class ElectricityGrid(Grid):
    name: str = "Electricity"
    primary_energy_factor: float = 3.8
    operation_grid: GridComponents = field(default_factory=lambda: copy.deepcopy(electricity_grid_config))

@dataclass
class HeatGrid(Grid):
    name: str = "HeatGrid"
    max_supply_temperature: float = 135.0
    min_supply_temperature: float = 80.0
    primary_energy_factor: float = 6.1
    operation_grid: GridComponents = field(default_factory=lambda: copy.deepcopy(heat_grid_config))
    investment_component: InvestmentComponents = field(default_factory=lambda: copy.deepcopy(heat_grid_config_inv))