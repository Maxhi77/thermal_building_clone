from openpyxl.styles.builtins import output

from oemof.thermal_building_model.oemof_facades.base_component import BaseComponent, InvestmentComponents
from typing import Optional
from oemof import solph
from dataclasses import dataclass, field
from oemof.network import Bus
from oemof.solph import Flow
from oemof.thermal_building_model.input.economics.investment_components import battery_config,hot_water_tank_config
import copy
from oemof.solph.constraints import storage_level_constraint,equate_variables

@dataclass
class Storage(BaseComponent):
    input_bus: Optional[Bus] = None
    output_bus: Optional[Bus] = None
    nominal_capacity: Optional[float] = None
    maximum_capacity: Optional[float] = None
    charging_capacity_rate: Optional[float] = None
    discharging_capacity_rate: Optional[float] = None
    balanced : bool = True
    loss_rate: Optional[float] = None
    min_storage_level: Optional[float] = None
    initial_storage_level: Optional[float] = None
    charging_efficiency: Optional[float] = None
    discharging_efficiency: Optional[float] = None
    investment_component: Optional[InvestmentComponents] = None
    invest_relation_input_capacity: Optional[float] = 1
    invest_relation_output_capacity: Optional[float] = 1
    def create_storage(self):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        self.oemof_component_name = f"{self.name.lower()}"

        if self.investment:
            epc = self.investment_component.calculate_epc()  # Get EPC from economics model
            print(str(self.investment_component)+":"+ str(epc))
            return solph.components.GenericStorage(
                label=self.oemof_component_name,
                inputs=None if self.input_bus is None else {self.input_bus: solph.Flow()},
                outputs=None if self.output_bus is None else {self.output_bus: solph.Flow()},
                invest_relation_input_capacity=self.invest_relation_input_capacity,  # c-rate of 1/6
                invest_relation_output_capacity=self.invest_relation_output_capacity,
                nominal_storage_capacity=solph.Investment(ep_costs=epc,
                                                          nonconvex=True,
                                                          maximum=self.investment_component.maximum_capacity,
                                                          minimum=self.investment_component.minimum_capacity,
                                                          offset=self.investment_component.cost_offset,
                                                          lifetime=self.investment_component.lifetime,
                                                          custom_attributes={
                                                              "co2": {
                                                                "offset": self.investment_component.co2_offset if self.investment_component else 0.00,
                                                                   "cost": self.investment_component.co2_per_capacity if self.investment_component else 0.00
                                                              }
                                                          }
                                                  ),
                loss_rate=self.loss_rate,
                min_storage_level=self.min_storage_level,
                initial_storage_level=self.initial_storage_level,
                inflow_conversion_factor=self.charging_efficiency,
                outflow_conversion_factor=self.discharging_efficiency,
                balanced = self.balanced,
                lifetime_inflow=self.investment_component.lifetime,
                lifetime_outflow=self.investment_component.lifetime,
            )

        else:
            return solph.components.GenericStorage(
                label=self.oemof_component_name,
                inputs={
                    self.input_bus: solph.Flow(
                        nominal_value=self.nominal_capacity * self.charging_capacity_rate
                    )
                },
                outputs={
                    self.output_bus: solph.Flow(
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
    def create_stratified_storage(self, levels, carrier_buses):
        """Creates a solph source with working_rate as variable cost and demand_rate added."""
        share_sum=0
        storage_dict = {}
        for temperature, share in levels.items():

            share_sum=share_sum+share
            self.oemof_component_name = f"{self.name.lower()}_{str(temperature)}"
            if temperature <= min(carrier_buses):
                continue
            # Zielwert

            # Sortierte Liste der Keys
            sorted_keys = sorted(carrier_buses.keys())

            # Index vom Zielwert finden
            index = sorted_keys.index(temperature)

            # Nächstkleinerer Key (falls vorhanden)
            if index > 0:
                lower_key = sorted_keys[index - 1]
                result = carrier_buses[lower_key]

            input_bus =  {carrier_buses[temperature]:solph.Flow()}
            output_bus =  {result:solph.Flow()}
            if self.investment:
                storage_dict[temperature] =  solph.components.GenericStorage(
                    label=self.oemof_component_name,
                    inputs=input_bus,
                    outputs=output_bus,
                    nominal_storage_capacity=solph.Investment(lifetime=self.investment_component.lifetime,
                                                      ),
                    loss_rate=self.loss_rate * share_sum,
                    inflow_conversion_factor=self.charging_efficiency,
                    outflow_conversion_factor=self.discharging_efficiency,
                    balanced = self.balanced,
                    lifetime_inflow=self.investment_component.lifetime,
                    lifetime_outflow=self.investment_component.lifetime,
                )
        return storage_dict

        if False:
            ##### IM MOMENT NOCH NICHT FUNKTIONSTÜCHTIG
            return solph.components.GenericStorage(
                label=self.oemof_component_name,
                inputs={
                    self.input_bus: solph.Flow(
                        nominal_value=self.nominal_capacity * self.charging_capacity_rate
                    )
                },
                outputs={
                    self.output_bus: solph.Flow(
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
    def post_process(self, results, component):
        capacity, invest_status = self.get_capacity(results, component)
        investment_cost = self.get_investment_cost(capacity, invest_status)
        investment_co2 = self.get_investment_co2(capacity, invest_status)
        flow_into_storage = self.get_flow_into_storage(results, component)
        flow_out_storage =  self.get_flow_out_storage(results, component)
        if isinstance(self,HotWaterTank):
            capacity /= self. relative_storage_capacity_in_wh_per_volume(self.max_temperature)
        return {"capacity": capacity,
                "investment_cost": investment_cost,
                "investment_co2": investment_co2,
                "flow_into": flow_into_storage,
                "flow_co2": flow_out_storage}

    def get_capacity(self, results, component):
        if self.investment:
            if self.investment_component.multiperiod:
                return (results[component, self.output_bus]["period_scalars"]["invest"].sum(),1 if results[component, self.output_bus]["period_scalars"]["invest"].sum()>0 else 0)
            else:
                return (solph.views.node(results, self.output_bus)["scalars"][((component, self.output_bus), "invest")]
                        ,solph.views.node(results, self.output_bus)["scalars"].get(((component, self.output_bus), "invest_status"), 0))
        else:
            return component.nominal_storage_capacity, 0

    def get_investment_cost(self, capacity, invest_status):
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

    def get_flow_into_storage(self, results, component):
        return results[component, self.output_bus]["sequences"]["flow"]

    def get_flow_out_storage(self, results, component):
        return results[component, self.input_bus]["sequences"]["flow"]

@dataclass
class HotWaterTank(Storage):
    name: str = "LayeredWaterTank"
    temperature_buses: Optional[Bus] = None
    invest_relation_input_capacity: float = 0.3
    invest_relation_output_capacity: float = 0.3
    loss_rate: float = 0.0
    charging_efficiency: float = 0.98
    discharging_efficiency: float = 0.98
    charging_capacity_rate: float = 0.3
    discharging_capacity_rate: float = 0.3
    # ambient_temperature: [dict[str, float], None] = None
    u_value: Optional[float] = 1.2
    min_storage_level:float = 0
    max_temperature: Optional[float] = None
    min_temperature: Optional[float] = None
    diameter: float = 0.5
    volume_in_m3 : float  = 100
    investment_component: InvestmentComponents = field(default_factory=lambda: copy.deepcopy(hot_water_tank_config))  # Use deepcopy

    # capacity is m^3
    def __post_init__(self):
        self.storage_volumen_in_Wh_per_kg = 4.186 * 1000 / 3600 # [Wh/K kg]
        self.qubick_meter_water_in_kg = 992.2  # [kg/m^3]

        if not self.investment:
            if self.volume_in_m3:
                self.nominal_capacity = (self.storage_capacity_at_temperature_for_a_volume(volume = self.volume_in_m3,temperature_high=self.max_temperature,
                                                                                           temperature_low=self.min_temperature))
            else:
                self.nominal_capacity = None
        else:
            print("in storage"+str(self.investment_component))
            self.investment_component.maximum_capacity = self.storage_capacity_at_temperature_for_a_volume(volume =self.investment_component.maximum_capacity,
                                                                                                           temperature_high=self.max_temperature,
                                                                                                           temperature_low=self.min_temperature)
            self.investment_component.cost_per_unit /= self.relative_storage_capacity_in_wh_per_volume(temperature_high=self.max_temperature,
                                                                                           temperature_low=self.min_temperature)

            self.investment_component.co2_per_capacity /= self.relative_storage_capacity_in_wh_per_volume(
                temperature_high=self.max_temperature,
                temperature_low=self.min_temperature)

    def get_stratified_storage_temperature_levels(self):
        if len(self.temperature_buses)>1:
            storage_dict = {}
            temp_delta_storage = self.max_temperature - self.min_temperature
            min_temp_storage = self.min_temperature
            for temp, bus in self.temperature_buses.items():
                share_bus = (temp-min_temp_storage)/temp_delta_storage
                min_temp_storage = temp
                storage_dict[temp] = share_bus
        return storage_dict
    def create_stratisfied_storage_constraint(self,model,hot_water_tank, hot_water_tank_stratisfied, hot_water_tank_stratisfied_temp_levels):
        equate_variables(energysystem.groups['powerline_1_2'], )
        def equate_variables(m):
            return var1 * factor1 == var2

        setattr(model, name, po.Constraint(rule=equate_variables_rule))
        print(2)
        if False:
            storage_level_constraint(
                model=model,
                name=self.name,
                storage_component=storage,
                multiplexer_bus=self.multiplexer,
                input_levels={bus: self.get_relative_storage_level_at_temperature(temperature_low=temp,
                                                                                  temperature_high=self.max_temperature) for temp,bus in self.temperature_buses.items()},  # in_0 is always active
                output_levels={bus: self.get_relative_storage_level_at_temperature(temp) for temp,bus in self.temperature_buses.items()},
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
    def relative_storage_capacity_in_wh_per_volume(self,temperature_high:float,temperature_low:float):
        return self.qubick_meter_water_in_kg * self.storage_volumen_in_Wh_per_kg * (temperature_high - temperature_low)
    def storage_capacity_at_temperature_for_a_volume(self,volume : float, temperature_low:float,temperature_high:float):
        return self.relative_storage_capacity_in_wh_per_volume(temperature_low=temperature_low, temperature_high=temperature_high) * volume

    def get_relative_storage_level_at_temperature(self, temperature_high:float, temperature_low:float):
        return (self.relative_storage_capacity_in_wh_per_volume(temperature_low=temperature_low,
                                                               temperature_high=temperature_high)
                / self.relative_storage_capacity_in_wh_per_volume(temperature_low=temperature_low,
                                                               temperature_high=temperature_high))



@dataclass
class Battery(Storage):
    name: str = "Battery"
    loss_rate: float = 0.0
    nominal_capacity: float
    invest_relation_input_capacity: float = 0.5
    invest_relation_output_capacity: float = 0.5
    charging_capacity_rate: float= 1
    discharging_capacity_rate: float = 1
    charging_efficiency: float = 0.95
    discharging_efficiency: float = 0.95
    initial_soc: float = 0.5
    min_storage_level: float = 0
    investment_component: InvestmentComponents = field(default_factory=lambda: copy.deepcopy(battery_config))



