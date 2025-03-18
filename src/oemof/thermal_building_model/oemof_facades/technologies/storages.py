from oemof.thermal_building_model.oemof_facades.base_component import BaseComponent, EconomicsInvestmentComponents, CO2Components
from typing import Optional
from oemof import solph
from dataclasses import dataclass, field
from oemof.network import Bus
from oemof.thermal_building_model.input.emissions.co2_components import battery_co2,hot_water_tank_co2
from oemof.thermal_building_model.input.economics.investment_components import battery_config,hot_water_tank_config

@dataclass
class Storage(BaseComponent):
    nominal_capacity: Optional[float] = None
    charging_capacity_rate: Optional[float] = None
    discharging_capacity_rate: Optional[float] = None
    balanced : bool = True
    loss_rate: Optional[float] = None
    min_storage_level: Optional[float] = None
    initial_storage_level: Optional[float] = 0
    charging_efficiency: Optional[float] = None
    discharging_efficiency: Optional[float] = None
    economics_model: Optional[EconomicsInvestmentComponents] = None
    co2_model: Optional[CO2Components] = None
    invest_relation_input_capacity: Optional[float] = None
    invest_relation_output_capacity: Optional[float] = None
    def create_storage(self, input_bus: Optional[Bus] = None, output_bus: Optional[Bus] = None):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        if self.investment:
            epc = self.economics_model.calculate_epc()  # Get EPC from economics model

            return solph.components.GenericStorage(
                label=f"{self.name.lower()}",
                inputs={input_bus: solph.Flow()},
                outputs={output_bus: solph.Flow()},
                invest_relation_input_capacity=self.invest_relation_input_capacity,  # c-rate of 1/6
                invest_relation_output_capacity=self.invest_relation_output_capacity,
                nominal_storage_capacity=solph.Investment(ep_costs=epc,
                                                  custom_attributes={
                                                      "co2": {
                                                          "offset": self.co2_model.offset_capacity if self.co2_model else 0.00,
                                                           "cost": self.co2_model.per_capacity if self.co2_model else 0.00
                                                      }
                                                  }
                                                  ),
                loss_rate=self.loss_rate,
                min_storage_level=self.min_storage_level,
                initial_storage_level=self.initial_storage_level,
                inflow_conversion_factor=self.charging_efficiency,
                outflow_conversion_factor=self.discharging_efficiency,
                balanced = self.balanced
            )

        else:
            return solph.components.GenericStorage(
                label=f"{self.name.lower()}",
                inputs={
                    input_bus: solph.Flow(
                        nominal_value=self.nominal_capacity * self.charging_capacity_rate
                    )
                },
                outputs={
                    output_bus: solph.Flow(
                        nominal_value=self.nominal_capacity * self.discharging_capacity_rate
                    )},
                    nominal_storage_capacity = self.nominal_capacity,
                    loss_rate = self.loss_rate,
                    min_storage_level = self.min_storage_level,
                    initial_storage_level = self.initial_storage_level,
                    inflow_conversion_factor = self.charging_efficiency,
                    outflow_conversion_factor = self.discharging_efficiency,
                    balanced=self.balanced
            )

@dataclass
class HotWaterTank(Storage):
    name: str = "LayeredWaterTank"
    temperature_buses: Optional[Bus] = None
    invest_relation_input_capacity: float = 0.2
    invest_relation_output_capacity: float = 0.2
    loss_rate: float = 0.01
    charging_efficiency: float = 0.99
    discharging_efficiency: float = 0.99
    charging_capacity_rate: float = 0.2
    discharging_capacity_rate: float = 0.2
    # ambient_temperature: [dict[str, float], None] = None
    u_value: Optional[float] = 1.2
    min_storage_level:float = 0
    max_temperature: Optional[float] = None
    min_temperature: Optional[float] = None
    diameter: float = 0.5
    volume_in_m3 : float  = 100
    economics_model: EconomicsInvestmentComponents = field(default_factory=lambda:hot_water_tank_config)
    co2_model: CO2Components = field(default_factory=lambda:hot_water_tank_co2)
    # capacity is m^3
    def __post_init__(self):
        self.storage_volumen_in_Wh_per_kg = 4.186 * 1000 / 3600 # [Wh/K kg]
        self.qubick_meter_water_in_kg = 992.2  # [kg/m^3]

        if self.volume_in_m3:
            self.nominal_capacity = (self.storage_capacity_at_temperature_per_volume(temperature=self.max_temperature)) * self.volume_in_m3
        else:
            self.nominal_capacity = None
        if self.investment:
            self.economics_model.maximum_capacity *= (
                self.storage_capacity_at_temperature_per_volume(temperature=self.max_temperature)
                * self.storage_volumen_in_Wh_per_kg
                * self.qubick_meter_water_in_kg
            )
            self.economics_model.cost_per_unit /= (
                self.qubick_meter_water_in_kg / self.storage_volumen_in_Wh_per_kg
            )
    def generate_bus_from_storage(self):
        self.bus_from_storage = solph.buses.Bus(label=f"b_{self.name.lower()}_from_storage")
        return self.get_bus_from_storage()
    def generate_storage_into_bus(self):
        self.bus_into_storage = solph.buses.Bus(label=f"b_{self.name.lower()}_into_storage")
        return self.get_bus_into_storage()
    def get_bus_from_storage(self):
        return self.bus_from_storage
    def get_bus_into_storage(self):
        return self.bus_into_storage
    def get_temperature_buses(self):
        return self.temperature_buses
    def storage_capacity_at_temperature_per_volume(self,temperature:float):
        return self.volume_in_m3 * self.qubick_meter_water_in_kg * self.storage_volumen_in_Wh_per_kg * (temperature -  self.min_temperature)

    def get_relative_storage_level_at_temperature(self, temperature:float):
        return self.storage_capacity_at_temperature_per_volume(temperature) / self.storage_capacity_at_temperature_per_volume(self.max_temperature)

@dataclass
class Battery(Storage):
    name: str = "Battery"
    loss_rate: float = 0
    nominal_capacity: float = 1000
    charging_capacity_rate: float= 1
    discharging_capacity_rate: float = 1
    charging_efficiency: float = 0.98
    discharging_efficiency: float = 0.95
    initial_storage_level: float = 0.0
    initial_soc: float = 0.5
    min_storage_level: float = 0
    economics_model: EconomicsInvestmentComponents = field(default_factory=lambda:battery_config)
    co2_model: CO2Components = field(default_factory=lambda:battery_co2)



