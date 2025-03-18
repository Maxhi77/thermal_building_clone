from oemof import solph
from typing import Optional, Union, List
from oemof.thermal_building_model.oemof_facades.base_component import  EconomicsInvestmentComponents, CO2Components
from dataclasses import dataclass, field
from oemof.thermal_building_model.oemof_facades.base_component import EconomicsGrid
from oemof.thermal_building_model.input.economics.operation_grid_economics import gas_grid_config,electricity_grid_config,heat_grid_config
from oemof.thermal_building_model.input.emissions.co2_components import gas_co2, electricity_co2, heat_grid_co2
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
    analysis_period: Optional[int] = None  # Number of years for price adjustment
    bus_from_grid: Optional[Union[solph.buses.Bus, List[solph.buses.Bus]]] = None
    bus_into_grid: Optional[Union[solph.buses.Bus, List[solph.buses.Bus]]] = None
    investment_economics: Optional[EconomicsInvestmentComponents] = None
    operation_economics: Optional[EconomicsGrid] = None
    co2_model: Optional[CO2Components] = None

    def __post_init__(self):
        self.bus_from_grid = solph.buses.Bus(label=f"b_{self.name.lower()}_from_grid")
        self.bus_into_grid = solph.buses.Bus(label=f"b_{self.name.lower()}_into_grid")
    def get_bus_from_grid(self):
        return self.bus_from_grid
    def get_bus_into_grid(self):
        return self.bus_into_grid
    def calculate_average_price(self, base_price: float) -> float:
        """Calculates the average price over the analysis period using exponential growth."""
        if self.analysis_period is None or self.operation_economics.price_change_factor == 0:
            return base_price  # No adjustment needed

        n = self.analysis_period
        growth_rate = self.operation_economics.price_change_factor

        # Exponential increase formula: P_t = P_0 * (1 + g)^t
        total_price = sum(base_price * (1 + growth_rate) ** t for t in range(n))
        return total_price / n  # Average price over period

    def create_source(self) -> solph.components.Source:
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        price = self.calculate_average_price(self.operation_economics.working_rate)

        if self.investment:
            epc = self.investment_economics.calculate_epc()  # Get EPC from economics model

            return solph.components.Source(
                label=f"{self.name.lower()}_from_grid",
                outputs={self.bus_from_grid: solph.Flow(
                    variable_costs=price,
                    custom_attributes={"co2": self.co2_model.per_flow if self.co2_model else 0.00},
                    nominal_value=solph.Investment(
                        maximum=self.investment_economics.maximum_capacity,
                        minimum=self.investment_economics.maximum_capacity,
                        ep_costs=epc,
                        nonconvex=True,
                        custom_attributes= {"co2":{"offset": self.co2_model.offset_capacity if self.co2_model else 0.00},
                                                    "cost":  self.co2_model.per_capacity if self.co2_model else 0.00}
                    )
                )}
            )
        else:
            return solph.components.Source(
                label=f"{self.name.lower()}_from_grid",
                outputs={self.bus_from_grid: solph.Flow(variable_costs=price,
                                              custom_attributes={"co2": self.co2_model.per_flow if self.co2_model else 0.00})},
            )

    def create_sink(self) -> solph.components.Sink:
        """Creates a solph sink with revenue as variable cost."""
        price = self.calculate_average_price(self.operation_economics.revenue)

        return solph.components.Sink(
            label=f"{self.name.lower()}_into_grid",
            inputs={self.bus_into_grid: solph.Flow(variable_costs=price,
                                         custom_attributes={"co2": - self.co2_model.per_flow if self.co2_model else 0.00})},
        )
@dataclass
class GasGrid(Grid):
    name: str = "Gas"
    primary_energy_factor: float = 6.2
    co2_model: CO2Components = field(default_factory=lambda: gas_co2)
    operation_economics: EconomicsGrid = field(default_factory=lambda: gas_grid_config)

@dataclass
class ElectricityGrid(Grid):
    name: str = "Electricity"
    primary_energy_factor: float = 3.8
    co2_model: CO2Components = field(default_factory=lambda: electricity_co2)
    operation_economics: EconomicsGrid = field(default_factory=lambda: electricity_grid_config)

@dataclass
class HeatGrid(Grid):
    name: str = "HeatGrid"
    max_supply_temperature: float = 135.0
    min_supply_temperature: float = 80.0
    primary_energy_factor: float = 6.1
    co2_model: CO2Components = field(default_factory=lambda: heat_grid_co2)
    operation_economics: EconomicsGrid = field(default_factory=lambda: heat_grid_config)
    investment_economics: EconomicsInvestmentComponents = field(default_factory=lambda: heat_grid_config_inv)