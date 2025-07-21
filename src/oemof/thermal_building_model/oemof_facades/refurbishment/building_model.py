from dataclasses import dataclass, field
from oemof import solph
from typing import Optional, Union, List, Literal
from oemof.thermal_building_model.tabula.tabula_reader import Building
from oemof.thermal_building_model.helpers import calculate_gain_by_sun, path_helper
from oemof.thermal_building_model.helpers.building_heat_demand_simulation import HeatDemand_Simulation_5RC
from oemof.thermal_building_model.helpers.refurbishment_calculator import Floor,Roof,Wall
from oemof.thermal_building_model.input.refurbishment.refurbishment_data import wall_config, roof_config, floor_config, door_config, window_config
from oemof.thermal_building_model.oemof_facades.base_component import EconomicsInvestmentRefurbishment
from oemof.thermal_building_model.helpers.building_heat_demand_simulation import find_highest_peak, calculate_inlet_temp
import os
import warnings
import copy
@dataclass
class Demand:
    name: str
    level_heating_demand : Optional[float] = None
    heat_level_calculation: bool = None
    nominal_value = 1
    bus: Optional[Union[solph.buses.Bus]] = None
    value_list: List = None
    level: int = None
    capex_annuity: Optional[float] = None
    co2_cost: Optional[float] = None
    def create_demand(self) -> solph.components.Sink:
        """Creates a solph sink with revenue as variable cost."""
        if self.heat_level_calculation:
            # Ensure `self.bus` is a dictionary
            if isinstance(self.bus, dict):
                for key,values in self.bus.items():
                    if key == self.level_heating_demand:
                        bus = values
                        self.heat_temp_bus = bus
                assert bus is not None, "No matching temp for heat demand building with carrier."

            elif isinstance(self.bus, solph.buses.Bus):
                # If `self.bus` is a single Bus instance, skip the dictionary check
                self.heat_temp_bus = self.bus
                warnings.warn(
                    "Warning: The building demand heating temperature might differ from the one supplied by the bus.",
                    stacklevel=2)


            else:
                raise TypeError("self.bus must be either a dictionary or a single Bus object.")
            self.oemof_component_name = f"{self.name.lower()}_lvl{self.heat_level_calculation}_demand"
            return solph.components.Sink(
                label=self.oemof_component_name,
                inputs={self.heat_temp_bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value,
                    variable_costs=self.capex_annuity / sum(self.value_list),
                    custom_attributes={"co2": self.co2_cost/ sum(self.value_list)}
                )
                }
            )
        else:
            self.oemof_component_name = f"{self.name.lower()}_demand"
            self.heat_temp_bus = self.bus
            return solph.components.Sink(
                label=self.oemof_component_name,
                inputs={self.heat_temp_bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value,
                    variable_costs=self.capex_annuity/ sum(self.value_list),
                    custom_attributes={"co2": self.co2_cost/ sum(self.value_list)}
                )
                }
            )
    def get_heat_bus_of_demand_temp_level(self):
        return self.heat_temp_bus

    def post_process(self, results, component):
        investment_cost = self.capex_annuity
        investment_co2 = self.co2_cost
        flow_into = self.get_flow_into_building(results, component)
        return {"investment_cost": investment_cost,
                "investment_co2": investment_co2,
                "flow_into": flow_into,
                "sum":flow_into.sum()}

    def get_flow_into_building(self, results, component):
        return results[ self.heat_temp_bus, component]["sequences"]["flow"]

'''
I think I want to add as well nur Dämmung des Daches als Variante
'''
@dataclass
class ThermalBuilding(Demand):
    name: Optional[str] = None
    number_of_occupants:float = 0
    number_of_household:float = 1
    number_of_time_steps: Optional[float] = None
    tabula_building_code: Optional[str] = None
    country: Optional[str] = None
    class_building: str = "heavy"
    building_type: Optional[str] = "SFH"
    refurbishment_status: str = "no_refurbishment"
    construction_year: Optional[int] = None
    floor_area: Optional[float] = None
    building_parameters: Optional["BuildingParameters"] = None
    wall_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:copy.deepcopy(wall_config))
    roof_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:copy.deepcopy(roof_config))
    floor_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:copy.deepcopy(floor_config))
    door_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:copy.deepcopy(door_config))
    window_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:copy.deepcopy(window_config))


    def __post_init__(self):

        self.building_object = Building(
            number_of_time_steps=self.number_of_time_steps,
            tabula_building_code=self.tabula_building_code,
            country=self.country,
            class_building=self.class_building,
            building_type=self.building_type,
            refurbishment_status=self.refurbishment_status,
            construction_year=self.construction_year,
            floor_area=self.floor_area,
        )
        self.building_object.calculate_all_parameters()
        main_path = path_helper.get_project_root()
        self.location = calculate_gain_by_sun.Location(
            epwfile_path=os.path.join(
                main_path,
                "thermal_building_model",
                "input",
                "weather_files",
                "03_HH_Hamburg-Fuhlsbuttel_TRY2035.epw",
            ),
        )
        self.t_outside = self.location.weather_data["drybulb_C"].to_list()
        self.solar_gains = self.building_object.calc_solar_gaings_through_windows(
            object_location_of_building=self.location,
            t_outside=self.t_outside
        )
        self.building_object.calc_solar_gaings_through_windows(
            object_location_of_building=self.location,
            t_outside=self.t_outside
        )
        if "MFH" in self.building_type :
            gain_technology_per_hour_in_watt = 200 * self.number_of_household
        elif "SFH" in self.building_type :
            gain_technology_per_hour_in_watt = 250
        else:
            gain_technology_per_hour_in_watt = 200
        # Internal gains of residents, machines (f.e. fridge, computer,...) and lights have to be added manually
        self.internal_gains = []
        self.t_set_heating = []
        self.t_set_cooling = []
        for _ in range(self.number_of_time_steps + 1):
            self.internal_gains.append(self.number_of_occupants*50+ gain_technology_per_hour_in_watt)
            self.t_set_heating.append(20)
            self.t_set_cooling.append(40)
        self.max_power_heating = 30000
        self.max_power_cooling = 30000
        self.t_set_heating_max = 24
        self.t_inital=20
        heating_demand, _, _ = HeatDemand_Simulation_5RC(
            label=str(self.name),
            solar_gains=self.solar_gains,
            t_outside=self.t_outside,
            internal_gains=self.internal_gains,
            t_set_heating=self.t_set_heating,
            t_set_cooling=self.t_set_cooling,
            t_set_heating_max=self.t_set_heating_max,
            building_config=self.building_object.building_config,
            t_inital=self.t_inital,
            max_power_heating=self.max_power_heating,
            max_power_cooling=self.max_power_cooling,
            timesteps= self.number_of_time_steps).solve()
        self.value_list = heating_demand
        if self.refurbishment_status is not "no_refurbishment":
            self.peak_index, _ = find_highest_peak(self.value_list)
            self.reference_building = Building(
                number_of_time_steps=self.peak_index,
                tabula_building_code=self.tabula_building_code,
                country=self.country,
                class_building=self.class_building,
                building_type=self.building_type,
                refurbishment_status="no_refurbishment",
                construction_year=self.construction_year,
                floor_area=self.floor_area,
            )
            self.reference_building.calculate_all_parameters()

        else:
            self.reference_building = self.building_object
        self.investment_cost_per_measure, self.capex_annuity_per_measure, self.co2_cost_per_measure = self.get_refurbishment_cost ()

        self.level_heating_demand = self.calculate_heat_distribution_temperature()

        self.capex_annuity = sum(self.capex_annuity_per_measure.values())
        self.co2_cost = sum(self.co2_cost_per_measure.values())

    def set_number_of_buildings_in_cluster(self,buildings_in_cluster):
        self.capex_annuity = self.capex_annuity * buildings_in_cluster
        self.co2_cost = self.co2_cost * buildings_in_cluster
    def get_roof_area_for_pv(self):
        total_a_floor = sum(self.building_object.a_floor.values())
        # https://www.agora-energiewende.de/fileadmin/Projekte/2023/2023-16_DE_Dach-PV-Potenzial/2023-16_DE_Dach-PV-Potenzial_Dokumentation.pdf?utm_source=chatgpt.com
        reduction_factor_for_pitched_roofs = 0.6  * 0.65
        return total_a_floor * reduction_factor_for_pitched_roofs

    def calculate_heat_distribution_temperature(self) -> float:
        tabula_building_code = self.building_object.tabula_building_code.array[0]
        index = tabula_building_code.find("Gen.") - 2
        tabula_gen = int(tabula_building_code[index:index + 1])
        #era_related_heat_distribution_temp_levels = [(1980, 70), (2000, 60), (2010, 50), (3000, 40)]
        if tabula_building_code.endswith(".001"):
            era_related_heat_distribution_temp_levels = [(5, 70), (9, 60), (10, 50), (11, 40)]  # (XY.Gen,T_inlet)
            T_old = 70
            for index in range(0, len(era_related_heat_distribution_temp_levels)):
                if tabula_gen >= era_related_heat_distribution_temp_levels[index][0]:
                    T_old = era_related_heat_distribution_temp_levels[index][1]
            return T_old
        else:
            era_related_heat_distribution_temp_levels = [(5, 70), (9, 60), (10, 50), (11, 40)]  # (XY.Gen,T_inlet)
            T_old = 70
            for index in range(0, len(era_related_heat_distribution_temp_levels)):
                if tabula_gen >= era_related_heat_distribution_temp_levels[index][0]:
                    T_old = era_related_heat_distribution_temp_levels[index][1]

            solar_gains_reference = self.reference_building.calc_solar_gaings_through_windows(
                object_location_of_building=self.location,
                t_outside=self.t_outside[:self.peak_index]
            )
            heating_demand_reference, _, _ = HeatDemand_Simulation_5RC(
                label=str(self.name)+"_reference",
                solar_gains=solar_gains_reference,
                t_outside=self.t_outside[:self.peak_index],
                internal_gains=self.internal_gains[:self.peak_index],
                t_set_heating=self.t_set_heating,
                t_set_cooling=self.t_set_cooling,
                t_set_heating_max=self.t_set_heating_max,
                building_config=self.reference_building.building_config,
                t_inital=self.t_inital,
                max_power_heating=self.max_power_heating,
                max_power_cooling=self.max_power_cooling,
                timesteps=self.peak_index).solve()

            nominal_outside_temperature_for_heating_systems = -14
            t_outside_coldest = self.t_outside[:self.peak_index]
            t_outside_coldest[-8:] = [nominal_outside_temperature_for_heating_systems] * 8
            heating_demand_with_refurbishment_peak, _, _ = HeatDemand_Simulation_5RC(
                building_config=self.building_object.building_config,
                label="coldest_peak",
                t_outside=t_outside_coldest,
                solar_gains=self.solar_gains[0:self.peak_index],  #: List, List,
                internal_gains=self.internal_gains[0:self.peak_index],  # [0], # ecos.household_internal_heat_gains,
                t_set_heating=self.t_set_heating,  # t_set_heating,
                t_set_cooling=self.t_set_cooling,  # t_set_cooling,
                t_set_heating_max=self.t_set_heating_max,
                t_inital=self.t_inital,
                max_power_heating=self.max_power_heating,
                max_power_cooling=self.max_power_cooling,
                timesteps=self.peak_index,
            ).solve()
            T_new = calculate_inlet_temp(
                space_heating_load_old=max(heating_demand_reference),
                space_heating_load_new=max(heating_demand_with_refurbishment_peak),
                T_inlet_old=T_old
            )
            assert T_old > T_new
            # Suche die nächstgrößere Zahl
            next_temp = None
            for _, temp in era_related_heat_distribution_temp_levels:
                if temp >= T_new:
                    if next_temp is None or temp < next_temp:
                        next_temp = temp

            return next_temp
    def get_refurbishment_cost(self) -> float:
        if self.refurbishment_status == "no_refurbishment":
            investment_cost = {"key":0}
            co2_cost = {"key":0}
            capex_annuity = {"key":0}
            return investment_cost, capex_annuity, co2_cost
        else:
            insulation_thickness = {}
            insulation_replacement = {}
            for key, new_u_value in self.building_object.u_floor.items():
                insulation_thickness[key.replace('u_', '')] = Floor(old_u_value=self.reference_building.u_floor[key],
                      new_u_value=new_u_value,  # Assuming `value` is the target U-value
                      thermal_conductivity=floor_config.thermal_conductivity).calculate_insulation_thickness()
            for key, new_u_value in self.building_object.u_roof.items():
                insulation_thickness[key.replace('u_', '')] = Roof(old_u_value=self.reference_building.u_roof[key],
                      new_u_value=new_u_value,  # Assuming `value` is the target U-value
                      thermal_conductivity=roof_config.thermal_conductivity).calculate_insulation_thickness()
            for key, new_u_value in self.building_object.u_wall.items():
                insulation_thickness[key.replace('u_', '')] = Wall(old_u_value=self.reference_building.u_wall[key],
                      new_u_value=new_u_value,  # Assuming `value` is the target U-value
                      thermal_conductivity=wall_config.thermal_conductivity).calculate_insulation_thickness()
            for key, new_u_value in self.building_object.u_door.items():
                if new_u_value == self.reference_building.u_door[key]:
                    insulation_replacement[key.replace('u_', '')] = False
                else:
                    insulation_replacement[key.replace('u_', '')] = False
                    for key_config, config in sorted(door_config.items(),  key=lambda x: (x[1].thermal_conductivity)):
                        insulation_replacement[key.replace('u_', '')] = key_config
                        if 1 / config.thermal_conductivity < new_u_value:
                            break
            for key, new_u_value in self.building_object.u_window.items():
                if new_u_value == self.reference_building.u_window[key]:
                    insulation_replacement[key.replace('u_', '')] = False
                else:
                    insulation_replacement[key.replace('u_', '')] = False
                    for key_config, config in sorted(window_config.items(),  key=lambda x: ( x[1].thermal_conductivity)):
                        insulation_replacement[key.replace('u_', '')] = key_config
                        if 1 / config.thermal_conductivity < new_u_value:
                            break

            investment_cost = {}
            capex_annuity = {}
            co2_cost = {}
            for key, area in self.building_object.a_floor.items():
                investment_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.floor_config.cost_per_unit +
                                        self.floor_config.cost_offset) * area
                capex_annuity[key.replace('a_', '')] = self.floor_config.calculate_epc(investment_cost[key.replace('a_', '')])
                co2_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.floor_config.co2_per_unit * area) *self.floor_config.get_depreciation_period() /self.floor_config.lifetime
            for key, area in self.building_object.a_wall.items():
                investment_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.wall_config.cost_per_unit +
                                        self.wall_config.cost_offset) * area
                capex_annuity[key.replace('a_', '')] = self.wall_config.calculate_epc(investment_cost[key.replace('a_', '')])

                co2_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.wall_config.co2_per_unit * area) *self.wall_config.get_depreciation_period()/self.wall_config.lifetime
            for key, area in self.building_object.a_roof.items():
                investment_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.roof_config.cost_per_unit +
                                        self.roof_config.cost_offset) * area
                capex_annuity[key.replace('a_', '')] = self.roof_config.calculate_epc(investment_cost[key.replace('a_', '')])

                co2_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.roof_config.co2_per_unit * area) *self.roof_config.get_depreciation_period()/self.roof_config.lifetime

            for key, area in self.building_object.a_window.items():
                if area==0:
                    investment_cost[key.replace('a_', '')] = 0
                    co2_cost[key.replace('a_', '')] = 0
                    capex_annuity[key.replace('a_', '')] = 0
                else:
                    investment_cost[key.replace('a_', '')] = (self.window_config[insulation_replacement[key.replace('a_', '')]].cost_per_unit *
                                                              (area ** self.window_config[insulation_replacement[key.replace('a_', '')]].cost_per_unit_exponent)
                                                              * area)
                    capex_annuity[key.replace('a_', '')] = self.window_config[insulation_replacement[key.replace('a_', '')]].calculate_epc(
                        investment_cost[key.replace('a_', '')])

                    co2_cost[key.replace('a_', '')] = (self.window_config[insulation_replacement[key.replace('a_', '')]].co2_per_unit * area) *self.window_config[insulation_replacement[key.replace('a_', '')]].get_depreciation_period()
            for key, area in self.building_object.a_door.items():
                square_meter_average_door = 2
                investment_cost[key.replace('a_', '')] = (self.door_config[insulation_replacement[key.replace('a_', '')]].cost_per_unit *
                                                          area / square_meter_average_door)
                capex_annuity[key.replace('a_', '')] = self.door_config[
                    insulation_replacement[key.replace('a_', '')]].calculate_epc(
                    investment_cost[key.replace('a_', '')])
                co2_cost[key.replace('a_', '')] = (
                            self.door_config[insulation_replacement[key.replace('a_', '')]].co2_per_unit * area / square_meter_average_door) *self.door_config[insulation_replacement[key.replace('a_', '')]].get_depreciation_period()

            return investment_cost, capex_annuity, co2_cost