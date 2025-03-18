from dataclasses import dataclass, field
from oemof import solph
from typing import Optional, Union, List, Literal
from oemof.thermal_building_model.tabula.tabula_reader import Building
from oemof.thermal_building_model.helpers import calculate_gain_by_sun, path_helper
from oemof.thermal_building_model.helpers.building_heat_demand_simulation import HeatDemand_Simulation_5RC
from oemof.thermal_building_model.helpers.refurbishment_calculator import Floor,Roof,Wall
from oemof.thermal_building_model.input.refurbishment.refurbishment_data import wall_config, roof_config, floor_config, door_config, window_config
from oemof.thermal_building_model.oemof_facades.base_component import EconomicsInvestmentRefurbishment
import os
@dataclass
class Demand:
    name: str
    nominal_value = 1
    bus: Optional[Union[solph.buses.Bus]] = None
    value_list: List = None
    level: int = None
    total_capex_annuity: Optional[float] = None
    total_co2_cost: Optional[float] = None
    def create_demand(self) -> solph.components.Sink:
        """Creates a solph sink with revenue as variable cost."""
        if self.level:
            # Ensure `self.bus` is a dictionary
            if isinstance(self.bus, dict):
                assert (isinstance(self.bus, dict) or
                        len(self.bus) == 1), ("Expected self.bus to be a dictionary with one entry, "
                                                    "when self.levle is defined.")
                # Extract the single key-value pair
                bus_level, bus = next(iter(self.bus.items()))
                # Ensure `self.level` matches the key of the bus dictionary
                assert self.level == bus_level, (f"Expected self.level ({self.level}) to match "
                                                 f"the bus key ({bus_level}).")
            elif isinstance(self.bus, solph.buses.Bus):
                # If `self.bus` is a single Bus instance, skip the dictionary check
                bus = self.bus
            else:
                raise TypeError("self.bus must be either a dictionary or a single Bus object.")
            return solph.components.Sink(
                label=f"{self.name.lower()}_lvl{self.level}_demand",
                inputs={bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value,
                    variable_costs=self.total_capex_annuity / sum(self.value_list),
                    custom_attributes={"co2": {"offset": self.total_co2_cost}}
                )
                }
            )
        else:
            return solph.components.Sink(
                label=f"{self.name.lower()}_demand",
                inputs={self.bus: solph.Flow(
                    fix=self.value_list,
                    nominal_value=self.nominal_value,
                    variable_costs=self.total_capex_annuity / sum(self.value_list),
                    custom_attributes={"co2":{"offset" : self.total_co2_cost}}
                )
                }
            )

'''
I think I want to add as well nur Dämmung des Daches als Variante
'''
@dataclass
class ThermalBuilding(Demand):
    name: Optional[str] = None
    number_of_time_steps: Optional[float] = None
    tabula_building_code: Optional[str] = None
    country: Optional[str] = None
    class_building: str = "heavy"
    building_type: Optional[str] = None
    refurbishment_status: str = "no_refurbishment"
    construction_year: Optional[int] = None
    floor_area: Optional[float] = None
    observation_period: float = 20
    building_parameters: Optional["BuildingParameters"] = None
    wall_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:wall_config)
    roof_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:roof_config)
    floor_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:floor_config)
    door_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:door_config)
    window_config: EconomicsInvestmentRefurbishment = field(default_factory=lambda:window_config)


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
        if self.refurbishment_status is not "no_refurbishment":
            self.reference_building = Building(
                number_of_time_steps=self.number_of_time_steps,
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
        main_path = path_helper.get_project_root()
        location = calculate_gain_by_sun.Location(
            epwfile_path=os.path.join(
                main_path,
                "thermal_building_model",
                "input",
                "weather_files",
                "12_BW_Mannheim_TRY2035.csv",
            ),
        )
        t_outside = location.weather_data["drybulb_C"].to_list()
        solar_gains = self.building_object.calc_solar_gaings_through_windows(
            object_location_of_building=location,
            t_outside=t_outside
        )
        self.building_object.calc_solar_gaings_through_windows(
            object_location_of_building=location,
            t_outside=t_outside
        )

        # Internal gains of residents, machines (f.e. fridge, computer,...) and lights have to be added manually
        internal_gains = []
        t_set_heating = []
        t_set_cooling = []
        for _ in range(self.number_of_time_steps + 1):
            internal_gains.append(3446 * 1000 / 8760)
            t_set_heating.append(20)
            t_set_cooling.append(40)

        heating_demand, cooling_demand, t_air = HeatDemand_Simulation_5RC(
            label=str(self.name),
            solar_gains=solar_gains,
            t_outside=t_outside,
            internal_gains=internal_gains,
            t_set_heating=t_set_heating,
            t_set_cooling=t_set_cooling,
            t_set_heating_max=24,
            building_config=self.building_object.building_config,
            t_inital=20,
            max_power_heating=20000,
            max_power_cooling=20000,
            timesteps=8760).solve()
        self.value_list = heating_demand
        self.investment_cost, self.capex_annuity, self.co2_cost = self.get_refurbishment_cost ()
        self.total_capex_annuity = sum(self.capex_annuity.values())
        self.total_co2_cost = sum(self.co2_cost.values())
    def get_insulation_thickness(self):
        print(2)
    def get_refurbishment_cost(self) -> float:
        if self.refurbishment_status == "no_refurbishment":
            investment_cost = {"key":0}
            co2_cost = {"key":0}
            return investment_cost, co2_cost
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
                                        self.floor_config.co2_per_unit * area) *self.floor_config.get_depreciation_period()
            for key, area in self.building_object.a_wall.items():
                investment_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.wall_config.cost_per_unit +
                                        self.wall_config.cost_offset) * area
                capex_annuity[key.replace('a_', '')] = self.wall_config.calculate_epc(investment_cost[key.replace('a_', '')])

                co2_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.wall_config.co2_per_unit * area) *self.wall_config.get_depreciation_period()
            for key, area in self.building_object.a_roof.items():
                investment_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.roof_config.cost_per_unit +
                                        self.roof_config.cost_offset) * area
                capex_annuity[key.replace('a_', '')] = self.roof_config.calculate_epc(investment_cost[key.replace('a_', '')])

                co2_cost[key.replace('a_', '')] = (insulation_thickness[key.replace('a_', '')] *
                                        self.roof_config.co2_per_unit * area) *self.roof_config.get_depreciation_period()

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