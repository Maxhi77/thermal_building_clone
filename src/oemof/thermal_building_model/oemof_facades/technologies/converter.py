from oemof.thermal_building_model.oemof_facades.base_component import BaseComponent, EconomicsInvestmentComponents, CO2Components
from typing import Optional, List
from oemof import solph
from oemof.network import Bus
from oemof.thermal_building_model.oemof_facades.helper_functions import calculate_cop, celsius_to_kelvin
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from dataclasses import dataclass, field

import os
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.input.economics.investment_components import air_heat_pump_config, gas_heater_config
from oemof.thermal_building_model.input.emissions.co2_components import air_heat_pump_co2, gas_heater_co2


@dataclass
class Converter(BaseComponent):
    nominal_power: Optional[float] = None
    input_bus: Optional[Bus] = None
    output_bus: Optional[Bus] = None
    conversion_factors: Optional[dict] = None
    economics_model: Optional[EconomicsInvestmentComponents] = None
    co2_model: Optional[CO2Components] = None

    def create_source(self,
                      heat_pump_bus: Bus):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        if self.investment:
            epc = self.economics_model.calculate_epc()  # Get EPC from economics model

            return solph.components.Source(
                label=f"{self.name.lower()}_source",
                outputs={heat_pump_bus: solph.Flow(
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
                    heat_pump_bus: solph.Flow(
                        nominal_value=self.nominal_power)
                }
            )
@dataclass
class GasHeater(Converter):
    name: str = "GasHeater"
    nominal_power: Optional[float] = 10000
    heat_carrier_bus: Optional[dict[Bus]] = None
    efficiency: Optional[float] = 0.99
    co2_model: CO2Components = field(default_factory=lambda: gas_heater_co2)
    economics_model: EconomicsInvestmentComponents = field(default_factory=lambda: gas_heater_config)

    def get_bus(self):
        self.bus = solph.buses.Bus(label=f"b_{self.name.lower()}")
        return self.bus
    def create_converters(self,
                          gas_heater_bus: Bus,
                          gas_bus:Bus,
                          heat_carrier_bus: Optional[dict[Bus]]):
        converters = []
        for temperature, bus in heat_carrier_bus.items():
            converters.append(solph.components.Converter(
                label=f"{self.name.lower()}_converter_to_{temperature}",
                inputs={gas_bus: solph.Flow(),
                        gas_heater_bus: solph.Flow()},
                outputs={
                    bus: solph.Flow(),
                },
                conversion_factors={gas_bus:  self.efficiency},
            ))
        return converters
@dataclass
class AirHeatPump(Converter):
    name: str = "AirHeatPump"
    nominal_power: Optional[float] = 100
    air_temperature: Optional[List] = None
    heat_carrier_bus: Optional[dict[Bus]] = None
    lorenz_cop_temp_in_heating: float = 10
    lorenz_cop_temp_out_heating: float = 45
    lorenz_cop_temp_in_cooling: float = 30
    lorenz_cop_temp_out_cooling: float = 10
    cop_for_setted_temp_interval: float = 4
    eer_for_setted_temp_interval: float = 4.8
    co2_model: CO2Components = field(default_factory=lambda: air_heat_pump_co2)
    economics_model: EconomicsInvestmentComponents = field(default_factory=lambda: air_heat_pump_config)
    def __post_init__(self):
        if self.air_temperature is None:
            main_path = get_project_root()
            location = calculate_gain_by_sun.Location(
                epwfile_path=os.path.join(
                    main_path,
                    "thermal_building_model",
                    "input",
                    "weather_files",
                    "12_BW_Mannheim_TRY2035.csv",
                ),
            )
            self.air_temperature = location.weather_data["drybulb_C"].to_list()
    def get_bus(self):
        self.bus = solph.buses.Bus(label=f"b_{self.name.lower()}")
        return self.bus
    def create_converters(self,
                          heat_pump_bus: Bus,
                          electricity_bus:Bus,
                          heat_carrier_bus: Optional[dict[Bus]]):
        converters = []
        cop = []
        for temperature, bus in heat_carrier_bus.items():
            for air_temp in self.air_temperature:
                cop.append(calculate_cop(
                    temp_input=celsius_to_kelvin(air_temp),
                    temp_output=celsius_to_kelvin(temperature),
                    lorenz_cop_temp_in=self.lorenz_cop_temp_in_heating,
                    lorenz_cop_temp_out=self.lorenz_cop_temp_out_heating,
                    cop_for_setted_temp_interval=self.cop_for_setted_temp_interval,
                ))
            converters.append(solph.components.Converter(
                label=f"{self.name.lower()}_converter_to_{temperature}",
                inputs={electricity_bus: solph.Flow(),
                        heat_pump_bus: solph.Flow()},
                outputs={
                    bus: solph.Flow(),
                },
                conversion_factors={electricity_bus:  [1 / x for x in cop]},
            ))
        return converters

