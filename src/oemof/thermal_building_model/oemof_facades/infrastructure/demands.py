from dataclasses import dataclass
from oemof import solph
from typing import Optional, Union, List

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
            assert (isinstance(self.bus, dict) or
                    len(self.bus) == 1), ("Expected self.bus to be a dictionary with one entry, "
                                                "when self.levle is defined.")
            # Extract the single key-value pair
            bus_level, bus = next(iter(self.bus.items()))
            # Ensure `self.level` matches the key of the bus dictionary
            assert self.level == bus_level, (f"Expected self.level ({self.level}) to match "
                                             f"the bus key ({bus_level}).")

            return solph.components.Sink(
                label=f"{self.name.lower()}_lvl{self.level}_demand",
                inputs={bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value
                )}
            )
        else:
            return solph.components.Sink(
                label=f"{self.name.lower()}_demand",
                inputs={self.bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value
                )
                }
            )

@dataclass
class ElectricityDemand(Demand):
    name: str = "Electricity"

@dataclass
class HeatDemand(Demand):
    name: str = "Heat"
    level:float = 30
