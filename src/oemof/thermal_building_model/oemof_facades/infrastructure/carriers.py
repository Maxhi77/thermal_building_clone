from dataclasses import dataclass
from oemof import solph

from oemof.tools import economics
from typing import Optional, Union, List
from thermal_building_model.oemof_facades.base_component import CO2Components, EconomicsInvestmentComponents
from dataclasses import dataclass, field

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
class Carrier:
    name: str
    levels: List = None

    def __post_init__(self):
        """Initialize the grid and create the bus only once."""
        if self.levels is not None:
            self.bus = {level: solph.buses.Bus(label=f"b_{self.name.lower()}_{level}") for level in sorted(self.levels)}
        else:
            self.bus = solph.buses.Bus(label=f"b_{self.name.lower()}")
    def connect_buses_decreasing_levels(self):
        for lower, higher in zip(sorted(self.bus.keys())[:-1], sorted(self.bus.keys())[1:]):
            # Set the flow from the higher to the lower bus
            self.bus[lower].inputs[self.bus[higher]] = solph.Flow()
    def get_bus(self, level_list:  [Union[List[int]]] = None):
        """
        - If level_list is given, return a dictionary of buses that match the given levels.
        - If no level_list is given, return the entire bus dictionary or a single bus.
        """
        if isinstance(self.bus, dict):
            if level_list is not None:
                if isinstance(level_list, list):
                    return {level: self.bus[level] for level in level_list if level in self.bus}
                assert print("level_list has to be a list")
            return self.bus  #

        return self.bus  #


@dataclass
class GasCarrier(Carrier):
    name: str = "Gas"

@dataclass
class ElectricityCarrier(Carrier):
    name: str = "Electricity"

@dataclass
class HeatCarrier(Carrier):
    name: str = "Heat"
    levels = [10,30,50]
