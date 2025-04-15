from oemof.thermal_building_model.oemof_facades.base_component import BaseComponent, InvestmentComponents
from typing import Optional, List
from oemof import solph
from oemof.network import Bus
from oemof.thermal_building_model.oemof_facades.helper_functions import calculate_cop, celsius_to_kelvin
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from dataclasses import dataclass, field
import copy
import os
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.input.economics.investment_components import air_heat_pump_config, gas_heater_config


@dataclass
class Converter(BaseComponent):
    nominal_power: Optional[float] = None
    input_bus: Optional[Bus] = None
    output_bus: Optional[Bus] = None
    conversion_factors: Optional[dict] = None
    investment_component: Optional[InvestmentComponents] = None
    def get_bus(self):
        self.bus = solph.buses.Bus(label=f"b_{self.name.lower()}")
        return self.bus
    def create_source(self):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        self.oemof_component_name = f"{self.name.lower()}_source"
        if self.investment:
            epc = self.investment_component.calculate_epc()  # Get EPC from economics model

            return solph.components.Source(
                label=self.oemof_component_name,
                outputs={self.bus: solph.Flow(
                    nominal_value= solph.Investment(ep_costs=epc,
                                                    maximum=self.investment_component.maximum_capacity,
                                                    minimum=self.investment_component.minimum_capacity,
                                                    offset=self.investment_component.cost_offset,
                                                    lifetime=self.investment_component.lifetime,
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
                label=self.oemof_component_name,
                outputs={
                    self.bus: solph.Flow(
                        nominal_value=self.nominal_power)
                }
            )
    def post_process(self,results,component,converter,heat_carrier,carrier_converted):
        capacity, invest_status = self.get_capacity(results,component)
        investment_cost = self.get_investment_cost(capacity,invest_status)
        investment_co2 = self.get_investment_co2(capacity,invest_status)
        into_converter = self.get_flow_into_converter(results,carrier_converted,converter)
        out_converter = self.get_flow_out_converter(results,component,converter,heat_carrier)
        sum_out_converter = [value.sum() for key, value in out_converter.items()]
        sum_into_converter =[value.sum() for key, value in into_converter.items()]

        total_efficiency = sum(sum_out_converter) /sum(sum_into_converter)

        return {"capacity":capacity,
                "investment_cost":investment_cost,
                "investment_co2":investment_co2,
                "flow_into_converter":into_converter,
                "flow_from_converter":out_converter,
                "total_efficiency":total_efficiency}
    def get_capacity(self,results,component):
        if self.investment:
            if self.investment_component.multiperiod:
                return (results[component, self.bus]["period_scalars"]["invest"].sum(),1 if results[component, self.bus]["period_scalars"]["invest"].sum()>0 else 0)
            else:
                return (solph.views.node(results, self.bus)[
                    "scalars"][ ((component, self.bus), "invest")]
                        ,solph.views.node(results, self.bus)["scalars"].get(((component, self.bus), "invest_status"), 0))
        else:
            return component.outputs[self.bus].nominal_capacity, 0
    def get_investment_cost(self,capacity,invest_status):
        if self.investment:
            return capacity * self.investment_component.cost_per_unit + self.investment_component.cost_offset * invest_status
        else:
            return 0
    def get_investment_co2(self, capacity, invest_status):
        if self.investment:
            if self.investment_component.co2_offset > 0 and invest_status == 0 and capacity > 0:
                raise ValueError(f"Error: 'invest_status' is None, so NonConvex=False, but co2_offset > 0 for component {self.name}")
            else:
                invest_status = 0
            return capacity * self.investment_component.co2_per_capacity + self.investment_component.co2_offset * invest_status
        else:
            return 0
    def get_flow_into_converter(self,results,carrier_converted,converter):
        return {conv.label: results[carrier_converted, conv]["sequences"]["flow"]
                 for conv in converter}

    def get_flow_out_converter(self,results,component,converter,heat_carrier):
        return {conv.label: results[conv, heat_carrier[hc]]["sequences"]["flow"]
                 for conv in converter for hc in heat_carrier
                 if (conv, heat_carrier[hc]) in results}

    def get_converted_carrier_flow_into_component(self,results,component,carrier_converted):
        carrier_converted


@dataclass
class GasHeater(Converter):
    name: str = "GasHeater"
    nominal_power: Optional[float] = 10000
    heat_carrier_bus: Optional[dict[Bus]] = None
    efficiency: Optional[float] = 0.95
    investment_component: InvestmentComponents = field(default_factory=lambda: copy.deepcopy(gas_heater_config))

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
                conversion_factors={bus:  self.efficiency},
            ))
        return converters

@dataclass
class CHP(Converter):
    name: str = "CHPElect"
    nominal_power: Optional[float] = 10000
    heat_carrier_bus: Optional[dict[Bus]] = None
    electrical_carrier_bus: Optional[dict[Bus]] = None
    thermal_efficiency: Optional[float] = 0.95
    electrical_efficiency: Optional[float] = 0.95
    investment_component: InvestmentComponents = field(default_factory=lambda: copy.deepcopy(gas_heater_config))

    def create_converters(self,
                          chp_bus: Bus,
                          gas_bus:Bus,
                          heat_carrier_bus: Optional[dict[Bus]]):
        converters = []
        for temperature, bus in heat_carrier_bus.items():
            converters.append(solph.components.Converter(
                label=f"{self.name.lower()}_converter_to_{temperature}",
                inputs={gas_bus: solph.Flow(),
                        chp_bus: solph.Flow()},
                outputs={
                    bus: solph.Flow(),
                    self.electrical_carrier_bus: solph.Flow(),
                },
                conversion_factors={bus: self.thermal_efficiency,
                                    self.electrical_carrier_bus: self.electrical_efficiency},
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
    investment_component: InvestmentComponents = field(default_factory=lambda: copy.deepcopy(air_heat_pump_config))
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

