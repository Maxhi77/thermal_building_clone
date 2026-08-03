from oemof.thermal_building_model.oemof_facades.base_component import  PhysicalBaseUnit
from oemof.solph.components import Converter
import copy
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, GasGrid, HydrogenGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier, \
    GasCarrier, HydrogenCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, WarmWater
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
from oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank, SeasonalWaterTank
from oemof.thermal_building_model.oemof_facades.technologies.converter import AirHeatPump, GasHeater, CHP
from oemof.thermal_building_model.oemof_facades.technologies.heat_grid import HeatGridInvestment
from oemof.thermal_building_model.input.economics.operation_grid_economics import (
    natural_gas_grid_config,
    bio_gas_grid_config,
    electricity_grid_config,
    hydrogen_grid_config,
)
from oemof.thermal_building_model.helpers.price_scenarios import (
    DEFAULT_PRICE_SCENARIOS,
    normalize_price_scenario_name as _normalize_price_scenario_name,
    parse_price_scenarios as _parse_price_scenarios,
    resolve_price_scenario_config as _resolve_price_scenario_config,
    scenario_output_cluster_name as _scenario_output_cluster_name,
)
import numpy as np
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
from oemof import solph
from oemof.solph.constraints import storage_level_constraint,equate_variables
from pyomo import environ as po
from oemof.thermal_building_model.helpers.define_building_combinations_for_cen_optimization import (
    build_scenarios,
    remove_duplicate_scenarios,
)
import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import os
import glob
import pickle
import argparse
from urllib.parse import urlparse
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from oemof.thermal_building_model.input.economics.investment_components_heat_grid import battery_config,hot_water_tank_config,air_heat_pump_config,gas_heater_config,pv_system_config,chp_config, seasonal_hot_water_tank_config

from oemof.thermal_building_model.tabula.tabula_reader import Building
import pprint as pp
import geopandas as gpd
import tsam.timeseriesaggregation as tsam

import pandas as pd
#  create solver
def run_model(
    co2_new,
    peak_new,
    data,
    aggregation1,
    t1_agg,
    data_classes_comp,
    combined_cluster,
    heat_grid_temperature,
    cluster_occurence,
    heat_demand_worst_case,
    heat_grid_length,
    price_scenario=None,
):
    es = solph.EnergySystem(
        timeindex=t1_agg,
        timeincrement=[1] * len(t1_agg),
        periods=[t1_agg],
        tsa_parameters=[
            {
                "timesteps_per_period": aggregation1.hoursPerPeriod,
                "order": aggregation1.clusterOrder,
                "timeindex": aggregation1.timeIndex,
            },
        ],
        infer_last_interval=False,
    )
    dataclasses = {}
    components = {}
    heat_grid_id="heat_grid"

    dataclasses[heat_grid_id]={}
    components[heat_grid_id]={}
    price_scenario_config = _resolve_price_scenario_config(price_scenario)

    total_heat_demand_year=None
    heat_transfer_station_max_kW = []
    number_of_buildings = 0
    for index, row in combined_cluster.iterrows():
        building_id = row['building_id']
        buildings_in_cluster = row['buildings_in_cluster']
        number_of_buildings = number_of_buildings + buildings_in_cluster
        total_heat_demand_year_per_building = (data["ww_demand_" + str(building_id)]+ data["building_" + str(building_id)])
        heat_transfer_station_max_kW.append((max(total_heat_demand_year_per_building),buildings_in_cluster))
        total_heat_demand_year_per_building_cluster = total_heat_demand_year_per_building * buildings_in_cluster
        print("building id:"+str(building_id))
        print((max(total_heat_demand_year_per_building_cluster),buildings_in_cluster))

        if total_heat_demand_year is None:
            total_heat_demand_year =  total_heat_demand_year_per_building_cluster
        else:
            total_heat_demand_year = total_heat_demand_year + total_heat_demand_year_per_building_cluster
    print("total_heat_demand_year_per_building_cluster :" +str(total_heat_demand_year_per_building_cluster))
    print("total_heat_demand_year :" +str(total_heat_demand_year))

    max_required_heating=float(max(total_heat_demand_year)) * 3
    heat_demand_annual = float(total_heat_demand_year.sum())
    demand = 0
    print("max_required_heating :" +str(max_required_heating))
    print("heat_demand_annual :" +str(heat_demand_annual))
    fictional_heat_grid_demand= data["ww_demand_" + str(building_id)]
    fictional_heat_grid_demand[:]= 1
    total_heat_demand_year_sum=0
    annual_heat_demand_peak = max(total_heat_demand_year)
    for cluster, count in cluster_occurence.items():
        # Hole den entsprechenden WW-Demand aus 'data' für das Cluster (erste Zahl in cluster_order entspricht dem Cluster)
        demand = demand + fictional_heat_grid_demand[cluster].sum() * count
        total_heat_demand_year_sum  += total_heat_demand_year[cluster].sum() * count

    if peak_new is False or peak_new is None:
        electricity_grid_config_grid = copy.deepcopy(electricity_grid_config)
        electricity_grid_config_grid.working_rate *= float(price_scenario_config["electricity_factor"])
        electricity_grid_config_grid.revenue *= float(price_scenario_config["electricity_feed_in_factor"])
        electricity_grid_dataclass = ElectricityGrid(operation_grid=electricity_grid_config_grid)
    else:
        electricity_grid_config_grid = copy.deepcopy(electricity_grid_config)
        electricity_grid_config_grid.working_rate *= float(price_scenario_config["electricity_factor"])
        electricity_grid_config_grid.revenue *= float(price_scenario_config["electricity_feed_in_factor"])
        electricity_grid_dataclass = ElectricityGrid(max_peak_from_grid=peak_new,
                                                     max_peak_into_grid=peak_new,
                                                     operation_grid=electricity_grid_config_grid)

    electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
    electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()
    electricity_grid_sink = electricity_grid_dataclass.create_sink()
    electricity_grid_source = electricity_grid_dataclass.create_source()
    electricity_carrier_dataclass = ElectricityCarrier()
    electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
    connect_buses(input=electricity_grid_bus_from_grid, target=electricity_carrier_bus, output=electricity_grid_bus_into_grid)

    electricity  = [electricity_grid_bus_from_grid,
                    electricity_grid_bus_into_grid,
                    electricity_grid_sink,
                    electricity_grid_source,
                    electricity_carrier_bus]
    es.add(*electricity)
    natural_gas_grid_config_grid = copy.deepcopy(natural_gas_grid_config)
    natural_gas_grid_config_grid.working_rate *= float(price_scenario_config["natural_gas_factor"])
    natural_gas_grid_dataclass = GasGrid(operation_grid=natural_gas_grid_config_grid,
                                 name="NaturalGas")
    natural_gas_grid_bus_from_grid = natural_gas_grid_dataclass.get_bus_from_grid()
    natural_gas_grid_source = natural_gas_grid_dataclass.create_source()

    bio_gas_grid_config_grid = copy.deepcopy(bio_gas_grid_config)
    bio_gas_grid_config_grid.working_rate *= float(price_scenario_config["bio_gas_factor"])
    bio_gas_grid_dataclass = GasGrid(operation_grid=bio_gas_grid_config_grid,
                                 name="BioGas")
    bio_gas_grid_bus_from_grid = bio_gas_grid_dataclass.get_bus_from_grid()
    bio_gas_grid_source = bio_gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier()
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=natural_gas_grid_bus_from_grid, target=gas_bus)
    connect_buses(input=bio_gas_grid_bus_from_grid, target=gas_bus)

    gas = [natural_gas_grid_bus_from_grid,bio_gas_grid_bus_from_grid,bio_gas_grid_source,natural_gas_grid_source,gas_bus]
    es.add(*gas)

    hydrogen_grid_config_grid = copy.deepcopy(hydrogen_grid_config)
    hydrogen_grid_config_grid.working_rate *= float(price_scenario_config["hydrogen_factor"])
    hydrogen_grid_dataclass = HydrogenGrid(operation_grid=hydrogen_grid_config_grid)
    hydrogen_grid_bus_from_grid = hydrogen_grid_dataclass.get_bus_from_grid()
    hydrogen_grid_source = hydrogen_grid_dataclass.create_source()

    hydrogen_carrier_dataclass = HydrogenCarrier()
    hydrogen_bus = hydrogen_carrier_dataclass.get_bus()
    connect_buses(input=hydrogen_grid_bus_from_grid, target=hydrogen_bus)


    hydrogen = [hydrogen_grid_bus_from_grid,hydrogen_grid_source,hydrogen_bus]
    es.add(*hydrogen)
    component_per_building = {}

    if True:
        heat_carrier_temperature_levels = [40,50]
        if heat_grid_temperature == 60:
            heat_carrier_temperature_levels.extend([heat_grid_temperature, 80])
        elif heat_grid_temperature == 50:
            heat_carrier_temperature_levels.extend([80])
        else:
            heat_carrier_temperature_levels.extend([heat_grid_temperature, 80])
    heat_carrier_dataclass = HeatCarrier(name="h_carrier_" + str(heat_grid_id),
                                         levels=heat_carrier_temperature_levels)
    heat_carrier_dataclass.connect_buses_decreasing_levels()
    heat_carrier_bus = heat_carrier_dataclass.get_bus()

    dataclasses[heat_grid_id]["heat_carrier_dataclass"] = heat_carrier_dataclass

    components[heat_grid_id]["heat_carrier_bus"] = heat_carrier_bus

    for key, config in hot_water_tank_config.items():
        hot_water_tank_config_building = copy.deepcopy(config)
        hot_water_tank_config_building.maximum_capacity =min(0.3 * heat_demand_worst_case,hot_water_tank_config_building.maximum_capacity)
        hot_water_tank_input_bus = solph.buses.Bus(label=f"tank_input_bus_{heat_grid_id}_{key}")
        hot_water_tank_output_bus = solph.buses.Bus(label=f"tank_output_bus_{heat_grid_id}_{key}")
        if False:
            hot_water_tank_dataclass = HotWaterTank(
                name=f"heat_storage_{heat_grid_id}_{key}",
                investment=True,
                temperature_buses=heat_carrier_dataclass.get_bus(),
                max_temperature=80,
                min_temperature=(40 + heat_grid_temperature) / 2,
                investment_component=hot_water_tank_config_building,
                input_bus=heat_carrier_dataclass.get_bus()[80],
                output_bus=heat_carrier_bus[80],
            )
        else:
            hot_water_tank_dataclass = HotWaterTank(
                name=f"heat_storage_{heat_grid_id}_{key}",
                investment=True,
                temperature_buses=heat_carrier_dataclass.get_bus(),
                max_temperature=80,
                min_temperature=40,
                investment_component=hot_water_tank_config_building,
                input_bus=hot_water_tank_input_bus,
                output_bus=hot_water_tank_output_bus,
                invest_relation_input_capacity=0.2,
                invest_relation_output_capacity = 0.2,
            )
        hot_water_tank = hot_water_tank_dataclass.create_storage()

        dataclasses[heat_grid_id]["hot_water_tank_dataclass_" + str(key)] = hot_water_tank_dataclass
        components[heat_grid_id]["hot_water_tank_" + str(key)] = hot_water_tank

    hot_water_tank_stratisfied_temp_levels_dict = hot_water_tank_dataclass.get_stratified_storage_temperature_levels()
    hot_water_tank_stratisfied = hot_water_tank_dataclass.create_stratified_storage(
        hot_water_tank_stratisfied_temp_levels_dict, heat_carrier_bus)

    dataclasses[heat_grid_id][
        "hot_water_tank_stratisfied_temp_levels_" + str(key)] = hot_water_tank_stratisfied_temp_levels_dict
    components[heat_grid_id]["hot_water_tank_stratisfied_" + str(key)] = hot_water_tank_stratisfied
    components[heat_grid_id]["hot_water_tank_input_bus_" + str(key)] = hot_water_tank_input_bus
    components[heat_grid_id]["hot_water_tank_output_bus_" + str(key)] = hot_water_tank_output_bus

    tank_helper = SeasonalWaterTank(
        name="tmp_seasonal",
        investment=False,  # wichtig: keine Config-Mutation
        max_temperature=90,
        min_temperature=40,
    )

    kwh_per_m3 = tank_helper.relative_storage_capacity_in_wh_per_volume(
        temperature_high=tank_helper.max_temperature,
        temperature_low=tank_helper.min_temperature,
    ) / 1000.0
    seasonal_share = 0.3
    seasonal_volume_m3_estimate = (heat_demand_annual * seasonal_share) / kwh_per_m3
    for key, config in seasonal_hot_water_tank_config.items():
        seasonal_water_tank_config_building = copy.deepcopy(config)

        seasonal_simplified_maximum_in_m3 = min(
            seasonal_volume_m3_estimate,
            seasonal_water_tank_config_building.maximum_capacity,
        )
        seasonal_water_tank_config_building.maximum_capacity = seasonal_simplified_maximum_in_m3
        print("seasonal_max_in_m3: "+str(seasonal_simplified_maximum_in_m3))
        print("seasonal_min:"+str(seasonal_water_tank_config_building.minimum_capacity) )
        seasonal_water_tank_input_bus = solph.buses.Bus(label=f"seasonal_water_tank_input_bus_{heat_grid_id}_{key}")
        seasonal_water_tank_output_bus = solph.buses.Bus(label=f"seasonal_water_tank_output_bus_{heat_grid_id}_{key}")
        seasonal_water_tank_dataclass = SeasonalWaterTank(
            name=f"seasonal_water_tank_{heat_grid_id}_{key}",
            investment=True,
            temperature_buses=heat_carrier_dataclass.get_bus(),
            max_temperature=90,
            min_temperature=40,
            investment_component=seasonal_water_tank_config_building,
            input_bus=seasonal_water_tank_input_bus,
            output_bus=seasonal_water_tank_output_bus,

        )
        seasonal_water_tank = seasonal_water_tank_dataclass.create_storage()

        dataclasses[heat_grid_id]["seasonal_water_tank_dataclass_" + str(key)] = seasonal_water_tank_dataclass
        components[heat_grid_id]["seasonal_water_tank_" + str(key)] = seasonal_water_tank


    seasonal_water_tank_stratisfied_temp_levels_dict = seasonal_water_tank_dataclass.get_stratified_storage_temperature_levels()
    seasonal_water_tank_stratisfied = seasonal_water_tank_dataclass.create_stratified_storage(
        seasonal_water_tank_stratisfied_temp_levels_dict, heat_carrier_bus)

    dataclasses[heat_grid_id][
        "seasonal_water_tank_stratisfied_temp_levels_" + str(key)] = seasonal_water_tank_stratisfied_temp_levels_dict
    components[heat_grid_id]["seasonal_water_tank_stratisfied_" + str(key)] = seasonal_water_tank_stratisfied
    components[heat_grid_id]["seasonal_water_tank_input_bus_" + str(key)] = seasonal_water_tank_input_bus
    components[heat_grid_id]["seasonal_water_tank_output_bus_" + str(key)] = seasonal_water_tank_output_bus

    for key, config in air_heat_pump_config.items():
        air_heat_pump_config_building =  copy.deepcopy(config)
        if air_heat_pump_config_building.maximum_capacity > max_required_heating:
            air_heat_pump_config_building.maximum_capacity = max_required_heating
        air_heat_pump_dataclass = AirHeatPump(heat_carrier_bus= heat_carrier_dataclass.get_bus(),
                                              investment=True,
                                              name="hp_"+str(heat_grid_id)+"_"+str(key),
                                              air_temperature=data["air_temperature"],
                                              investment_component=air_heat_pump_config_building)


        air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
        air_heat_pump= air_heat_pump_dataclass.create_source()
        air_heat_pump_converters= air_heat_pump_dataclass.create_converters(heat_pump_bus = air_heat_pump_bus,
                                                                         electricity_bus = electricity_carrier_bus,
                                                                         heat_carrier_bus= heat_carrier_bus)



        dataclasses[heat_grid_id]["air_heat_pump_dataclass_"+str(key)] = air_heat_pump_dataclass
        components[heat_grid_id]["air_heat_pump_converters_"+str(key)] = air_heat_pump_converters
        components[heat_grid_id]["air_heat_pump_"+str(key)] = air_heat_pump
        components[heat_grid_id]["air_heat_pump_bus_"+str(key)] = air_heat_pump_bus

    if True:
        for key, config in gas_heater_config.items():
            gas_heater_config_building = copy.deepcopy(config)
            if gas_heater_config_building.maximum_capacity > max_required_heating:
                gas_heater_config_building.maximum_capacity = max_required_heating

            gas_heater_dataclass = GasHeater(investment=True,
                                             name="gas_heater_"+str(heat_grid_id)+"_"+str(key),
                                             investment_component=gas_heater_config_building)
            gas_heater_bus = gas_heater_dataclass.get_bus()
            gas_heater= gas_heater_dataclass.create_source()
            gas_heater_converters= gas_heater_dataclass.create_converters(gas_heater_bus = gas_heater_bus,
                                                                          gas_bus = gas_bus,
                                                                          heat_carrier_bus=heat_carrier_bus)

            dataclasses[heat_grid_id]["gas_heater_dataclass_"+str(key)] = gas_heater_dataclass
            components[heat_grid_id]["gas_heater_converters_"+str(key)] = gas_heater_converters
            components[heat_grid_id]["gas_heater_bus_"+str(key)] = gas_heater_bus
            components[heat_grid_id]["gas_heater_"+str(key)] = gas_heater
    if True:
        for key, config in chp_config.items():
            chp_config_building = copy.deepcopy(config)

            if chp_config_building.maximum_capacity > max_required_heating:
                chp_config_building.maximum_capacity = max_required_heating
            chp_dataclass = CHP(investment=True,
                                name="chp_"+str(heat_grid_id)+"_"+str(key),
                                investment_component=chp_config_building,
                                )
            chp_bus = chp_dataclass.get_bus()
            chp= chp_dataclass.create_source()
            chp_converters= chp_dataclass.create_converters(chp_bus = chp_bus,
                                                            gas_bus = hydrogen_bus,
                                                            heat_carrier_bus=heat_carrier_bus
                                                            ,
                                                            electricity_bus = electricity_carrier_bus
                                                            )

            dataclasses[heat_grid_id]["chp_dataclass_"+str(key)] = chp_dataclass
            components[heat_grid_id]["chp_converters_"+str(key)] = chp_converters
            components[heat_grid_id]["chp_bus_"+str(key)] = chp_bus
            components[heat_grid_id]["chp_"+str(key)] = chp

    for key, config in battery_config.items():
        battery_config_building =  copy.deepcopy(config)

        battery_config_building.maximum_capacity = min(number_of_buildings * 60, battery_config_building.maximum_capacity)
        battery_dataclass = Battery(investment=True,
                                    name="battery_"+str(heat_grid_id)+"_"+str(key),
                                    input_bus = electricity_carrier_bus,
                                    output_bus = electricity_carrier_bus,
                                    investment_component=battery_config_building)

        battery = battery_dataclass.create_storage()

        dataclasses[heat_grid_id]["battery_dataclass_"+str(key)] = battery_dataclass
        components[heat_grid_id]["battery_"+str(key)] = battery

    print(heat_transfer_station_max_kW)
    print(max(total_heat_demand_year))
    print(total_heat_demand_year_sum)
    print(demand)
    heat_grid_investment = HeatGridInvestment(name="heat_grid_investment",
                                    heat_transfer_station_max_kW =heat_transfer_station_max_kW,
                                    pipe_length_in_meter = heat_grid_length,
                                    peak_load_in_kw = max(total_heat_demand_year),
                                    flow_temperature = heat_grid_temperature,
                                    total_heat_demand = total_heat_demand_year_sum,
                                    fictional_demand = demand)
    heat_grid_investment.tsam_total_amount = demand
    heat_grid_investment.value_list = fictional_heat_grid_demand
    heat_grid_investment_bus = heat_grid_investment.get_bus()
    heat_grid_investment_sink=  heat_grid_investment.create_sink(heat_grid_investment_bus)
    heat_grid_investment_source = heat_grid_investment.create_source(heat_grid_investment_bus)

    heat_grid_loss=heat_grid_investment.calculate_heat_grid_loss_for_flow_temperature(heat_grid_temperature)
    dataclasses["heat_grid"]["heat_grid_investment"] =heat_grid_investment

    components["heat_grid"]["heat_grid_investment_bus"] = heat_grid_investment_bus
    components["heat_grid"]["heat_grid_investment_sink"] = heat_grid_investment_sink
    components["heat_grid"]["heat_grid_investment_source"] = heat_grid_investment_source
    if False:
        list_heat_demand_building = None
        list_heat_demand_ww = None
        list_electricity_demand_building = None
        for index, row in combined_cluster.iterrows():
            building_id = row['building_id']
            buildings_in_cluster = row['buildings_in_cluster']

            ww_values = np.asarray(data["ww_demand_" + str(building_id)], dtype=float) * buildings_in_cluster
            heat_values = np.asarray(data["building_" + str(building_id)], dtype=float) * buildings_in_cluster
            elec_values = np.asarray(data["e_demand_" + str(building_id)], dtype=float) * buildings_in_cluster

            if list_heat_demand_building is None:
                list_heat_demand_ww = ww_values
                list_heat_demand_building = heat_values
                list_electricity_demand_building = elec_values
            else:
                list_heat_demand_ww = list_heat_demand_ww + ww_values
                list_heat_demand_building = list_heat_demand_building + heat_values
                list_electricity_demand_building = list_electricity_demand_building + elec_values

            print(building_id)
            dataclasses[building_id]={}
            components[building_id]={}
            buildings_in_cluster =row['buildings_in_cluster']

            heat_demand_dataclass.value_list = data["ww_demand_"+str(building_id)]
            heat_demand_dataclass.level = heat_demand_dataclass.demand_temperature

            demand = 0
            for cluster, count in cluster_occurence.items():
                # Hole den entsprechenden WW-Demand aus 'data' für das Cluster (erste Zahl in cluster_order entspricht dem Cluster)
                demand = demand + data["building_" + str(building_id)][cluster].sum() * count

            max(data["ww_demand_" + str(building_id)] + data["building_" + str(building_id)])





    for index, row in combined_cluster.iterrows():


        building_id = row['building_id']
        print(building_id)
        dataclasses[building_id]={}
        components[building_id]={}
        buildings_in_cluster =row['buildings_in_cluster']
        building_dataclass = copy.deepcopy(data_classes_comp.loc["building", building_id])
        building_dataclass.level_heating_demand = heat_grid_temperature
        heat_carrier_temperature_levels_building = [50, heat_grid_temperature]
        heat_carrier_dataclass_building = HeatCarrier(name="h_carrier_" + str(building_id),
                                             levels=heat_carrier_temperature_levels_building)
        heat_carrier_bus_building = heat_carrier_dataclass_building.get_bus()
        heat_50_from_converter_building = Converter(label="conv_h_from_grid_50_"+str(building_id),
                                              inputs={heat_carrier_bus[50]: solph.flows.Flow()},
                                              outputs={heat_carrier_bus_building[50]: solph.flows.Flow()},
                                              conversion_factors={heat_carrier_bus_building[50]: 1/(buildings_in_cluster)*heat_grid_loss})
        heat_heating_demand_from_converter_building = Converter(label="conv_h_from_grid_heatdemand_"+str(building_id),
                                              inputs={heat_carrier_bus[heat_grid_temperature]: solph.flows.Flow()},
                                              outputs={heat_carrier_bus_building[heat_grid_temperature]: solph.flows.Flow()},
                                              conversion_factors={heat_carrier_bus_building[heat_grid_temperature]: 1/(buildings_in_cluster)*heat_grid_loss})

        heat_demand_dataclass = data_classes_comp.loc["heat_demand", building_id]
        heat_demand_dataclass.value_list = data["ww_demand_"+str(building_id)]
        heat_demand_dataclass.level = heat_demand_dataclass.demand_temperature
        heat_demand_dataclass.bus = heat_carrier_bus_building[heat_demand_dataclass.demand_temperature]

        heat_demand = heat_demand_dataclass.create_demand()

        dataclasses[building_id]["heat_carrier_dataclass"] = heat_carrier_dataclass_building
        dataclasses[building_id]["heat_demand_dataclass"] = heat_demand_dataclass

        components[building_id]["heat_demand"] = heat_demand
        components[building_id]["heat_carrier_bus"] = heat_carrier_bus_building
        components[building_id]["heat_50_from_converter_building"] = heat_50_from_converter_building
        components[building_id]["heat_heating_demand_from_converter_building"] = heat_heating_demand_from_converter_building

        building_dataclass.value_list = data["building_"+str(building_id)]
        demand = 0
        for cluster, count in cluster_occurence.items():
            # Hole den entsprechenden WW-Demand aus 'data' für das Cluster (erste Zahl in cluster_order entspricht dem Cluster)
            demand = demand + data["building_" + str(building_id)][cluster].sum() * count

        building_dataclass.tsam_total_amount = demand
        building_dataclass.set_number_of_buildings_in_cluster(buildings_in_cluster)
        building_dataclass.bus=heat_carrier_bus_building[building_dataclass.level_heating_demand]

        building_component = building_dataclass.create_demand()

        dataclasses[building_id]["building_dataclass"] = building_dataclass
        components[building_id]["building_component"] = building_component
        max(data["ww_demand_" + str(building_id)] + data["building_" + str(building_id)])

        electricity_carrier_dataclass_building = ElectricityCarrier(name="e_carrier_"+str(building_id))
        electricity_carrier_bus_building = electricity_carrier_dataclass_building.get_bus()
        grid_into_converter_building = Converter(label="conv_e_into_grid_"+str(building_id),
                                              inputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                              outputs={electricity_carrier_bus: solph.flows.Flow()},
                                              conversion_factors={electricity_carrier_bus_building: 1/buildings_in_cluster })
        grid_from_converter_building = Converter(label="conv_e_from_grid_"+str(building_id),
                                              inputs={electricity_carrier_bus: solph.flows.Flow()},
                                              outputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                              conversion_factors={electricity_carrier_bus_building: 1/ buildings_in_cluster})

        electricity_demand_dataclass_building = data_classes_comp.loc["electricity_demand", building_id]
        electricity_demand_dataclass_building.value_list = data["e_demand_"+str(building_id)]
        electricity_demand_dataclass_building.bus=electricity_carrier_bus_building
        electricity_demand = electricity_demand_dataclass_building.create_demand()

        dataclasses[building_id]["electricity_carrier_dataclass_building"] = electricity_carrier_dataclass_building
        dataclasses[building_id]["electricity_demand_dataclass_building"] = electricity_demand_dataclass_building

        components[building_id]["electricity_carrier_bus_building"] = electricity_carrier_bus_building
        components[building_id]["grid_into_converter_building"] = grid_into_converter_building
        components[building_id]["grid_from_converter_building"] = grid_from_converter_building
        components[building_id]["electricity_demand"] = electricity_demand

        for key, config in pv_system_config.items():
            pv_dataclass = copy.deepcopy(data_classes_comp[building_id]["pv_system"][key])
            pv_dataclass_config_building = copy.deepcopy(config)
            pv_dataclass_config_building.set_reference_unit_quantity(reference_unit_quantity=buildings_in_cluster)

            pv_dataclass.investment_component=pv_dataclass_config_building

            pv_dataclass.value_list = data["pv_system_" + str(building_id)+"_"+str(key)]

            pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(area = building_dataclass.get_roof_area_for_pv())
            pv_bus = pv_dataclass.get_bus()
            pv_system = pv_dataclass.create_source()
            pv_system_curtailment_capable = pv_dataclass.create_sink()
            connect_buses(input=pv_bus, target=electricity_carrier_bus_building)

            dataclasses[building_id]["pv_dataclass_" + str(key)] = pv_dataclass
            components[building_id]["pv_system_" + str(key)] = pv_system
            components[building_id]["pv_system_curtailment_capable_" + str(key)] = pv_system_curtailment_capable
            components[building_id]["pv_bus_" + str(key)] = pv_bus

    for building_id, building_data in components.items():
        # Ensure we're processing the components for the current building
        for oemof_comp, comp_value in building_data.items():
            # Check if the component is a list (which it should not be, based on the structure)
            if isinstance(comp_value, list):
                for item in comp_value:
                    es.add(item)
                    print(item)
                    # Process each component in the list
            # Check if the component is a dictionary, meaning it has nested components
            elif isinstance(comp_value, dict):
                # If it's a dictionary, iterate over its key-value pairs
                for key, value in comp_value.items():
                    print(value)
                    es.add(value)
            else:
                # Otherwise, just add the component directly
                es.add(comp_value)
                print(comp_value)
    model = solph.Model(es)

    if True:
        for building_id, building_data in dataclasses.items():
            if building_id=="heat_grid":
                for key, config in hot_water_tank_config.items():
                    for temperature, stratisfied_storage in components[building_id]["hot_water_tank_stratisfied_"+str(key)].items():
                        storage_father = es.groups[components[building_id]["hot_water_tank_"+str(key)].label]
                        storage_child = stratisfied_storage
                        share_stratisfied = dataclasses[building_id]["hot_water_tank_stratisfied_temp_levels_"+str(key)][temperature]

                        def equate_variables_rule(share_stratisfied):
                            return model.GenericInvestmentStorageBlock.invest[storage_child, 0]  <= model.GenericInvestmentStorageBlock.invest[storage_father, 0]* share_stratisfied

                        setattr(model, "eq"+components[building_id]["hot_water_tank_stratisfied_"+str(key)][temperature].label, po.Constraint(rule=equate_variables_rule(share_stratisfied)))
            if building_id == "heat_grid":
                for key, config in seasonal_hot_water_tank_config.items():
                    for temperature, stratisfied_storage in components[building_id][
                        "seasonal_water_tank_stratisfied_" + str(key)].items():
                        storage_father = es.groups[components[building_id]["seasonal_water_tank_" + str(key)].label]
                        storage_child = stratisfied_storage
                        share_stratisfied = \
                        dataclasses[building_id]["seasonal_water_tank_stratisfied_temp_levels_" + str(key)][temperature]

                        def equate_variables_rule(share_stratisfied):
                            return model.GenericInvestmentStorageBlock.invest[storage_child, 0] <= \
                                model.GenericInvestmentStorageBlock.invest[storage_father, 0] * share_stratisfied

                        setattr(model, "eq" + components[building_id]["seasonal_water_tank_stratisfied_" + str(key)][
                            temperature].label, po.Constraint(rule=equate_variables_rule(share_stratisfied)))
    if len(pv_system_config) > 1:
        print("PV SYSTEM ÜBERARTBEITEN SODASS DER CONSTRAINT FÜR JEDES GEBÄUDE GEMACHT WIRD IN BUILDING ID")
        for key, config in pv_system_config.items():
            maximum_pv_capacity = dataclasses[building_id]["pv_dataclass_" + str(key)].investment_component.maximum_capacity
            maximum_key = max(pv_system_config)
            def equate_variables_rule(maximum_pv_capacity, maximum_key):
                for ke in range(maximum_key):
                    key = int(ke +1)
                    return model.InvestmentFlowBlock.invest[es.groups[components[building_id]["pv_system_"+str(key)].label],
                    components[building_id]["electricity_carrier_bus_building"],
                    0] + \
                    model.InvestmentFlowBlock.invest[es.groups[components[building_id]["pv_system_"+str(key)].label],
                    components[building_id]["electricity_carrier_bus_building"],
                    0] <= maximum_pv_capacity

            setattr(model, "eq"+components[building_id]["pv_system_"+str(key)].label, po.Constraint(rule=equate_variables_rule(int(maximum_pv_capacity),int(maximum_key))))

    if False:
        # Create the graph from the energy system (es)
        graph = create_nx_graph(es)
        # Draw the graph
        plt.figure(figsize=(18, 14))  # Set figure size
        nx.draw(graph, with_labels=True, font_size=6)
        plt.show()
    if co2_new is None:
        model = solph.constraints.additional_total_limit(model, "co2", limit=144000000)
    else:
        print("new co2 VALUE:"+str(co2_new))
        model = solph.constraints.additional_total_limit(model, "co2", limit=co2_new)
    # Show the graph
    # Show the graph
        print("__________")
        print("start for:")
        print("boundary co2:"+str(co2_new))
        print("boundary peak:" + str(peak_new))
    try:

        if True:
            solve_result=model.solve(solver=SOLVER, solve_kwargs={"tee": True},
                                                  cmdline_options={"threads":SOLVER_THREADS}
            )
        else:
            solve_result=model.solve(solver=SOLVER, solve_kwargs={"tee": True},
                                                  cmdline_options={"mipgap": 0.005}
            )
        meta_results = solph.processing.meta_results(model)
        results = solph.processing.results(model)
        final_results = {}
        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink
                                                )
        final_results[natural_gas_grid_dataclass.name] = natural_gas_grid_dataclass.post_process(results,natural_gas_grid_source,None)
        final_results[bio_gas_grid_dataclass.name] = bio_gas_grid_dataclass.post_process(results, bio_gas_grid_source, None)
        final_results[hydrogen_grid_dataclass.name] = hydrogen_grid_dataclass.post_process(results, hydrogen_grid_source, None)
        if False:
            final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)

        for building_id, building_data in components.items():
            final_results[building_id] = {}
            if building_id=="heat_grid":
                final_results["heat_grid"]["heat_grid_investment"]=dataclasses["heat_grid"]["heat_grid_investment"].post_process()
                final_results["heat_grid"]["heat_grid_investment"]["max_required_demand"]=dataclasses["heat_grid"]["heat_grid_investment"].peak_load_in_kw
                for key,_ in hot_water_tank_config.items():

                    final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name] = dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].post_process(results,components[building_id]["hot_water_tank_"+str(key)])

                for key,_ in seasonal_hot_water_tank_config.items():

                    final_results[building_id][dataclasses[building_id]["seasonal_water_tank_dataclass_"+str(key)].name] = dataclasses[building_id]["seasonal_water_tank_dataclass_"+str(key)].post_process(results,components[building_id]["seasonal_water_tank_"+str(key)])

                for key,_ in battery_config.items():
                    final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name] = dataclasses[building_id]["battery_dataclass_"+str(key)].post_process(results,components[building_id]["battery_"+str(key)])
                for key,_ in gas_heater_config.items():
                    final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name] = dataclasses[building_id]["gas_heater_dataclass_"+str(key)].post_process(results,
                                                                                                                                                                      components[building_id]["gas_heater_"+str(key)],
                                                                                                                                                                      components[building_id]["gas_heater_converters_"+str(key)],
                                                                                                                                                                      components[building_id]["heat_carrier_bus"],
                                                                                                                                                                      gas_bus)
                for key, _ in chp_config.items():
                    final_results[building_id][dataclasses[building_id]["chp_dataclass_" + str(key)].name] = \
                    dataclasses[building_id]["chp_dataclass_" + str(key)].post_process(results,
                                                                                              components[building_id][
                                                                                                  "chp_" + str(key)],
                                                                                              components[building_id][
                                                                                                  "chp_converters_" + str(
                                                                                                      key)],
                                                                                              components[building_id][
                                                                                                  "heat_carrier_bus"],
                                                                                              hydrogen_bus)
                for key,_ in air_heat_pump_config.items():
                    final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].name] = dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].post_process(results,
                                                                                                                                                                            components[building_id]["air_heat_pump_"+str(key)],
                                                                                                                                                                            components[building_id]["air_heat_pump_converters_"+str(key)],
                                                                                                                                                                            components[building_id]["heat_carrier_bus"],
                                                                                                                                                                            electricity_carrier_bus)
            else:
                final_results[building_id][dataclasses[building_id]["building_dataclass"].name] = dataclasses[building_id]["building_dataclass"].post_process(results,components[building_id]["building_component"])
                final_results[building_id]["refurbishment_status"] = dataclasses[building_id]["building_dataclass"].refurbishment_status

                final_results[building_id][dataclasses[building_id]["electricity_demand_dataclass_building"].name] = dataclasses[building_id]["electricity_demand_dataclass_building"].post_process(results,components[building_id]["electricity_demand"])

                final_results[building_id][dataclasses[building_id]["heat_demand_dataclass"].name] = dataclasses[building_id]["heat_demand_dataclass"].post_process(results,components[building_id]["heat_demand"])
                final_results[building_id]["buildings_in_cluster"] = dataclasses[building_id]["building_dataclass"].buildings_in_cluster
                for key,_ in pv_system_config.items():
                    final_results[building_id][dataclasses[building_id]["pv_dataclass_"+str(key)].name] = dataclasses[building_id]["pv_dataclass_"+str(key)].post_process(results,components[building_id]["pv_system_"+str(key)],components[building_id]["pv_system_curtailment_capable_"+str(key)])

        co2_investment = 0
        for building_id in components:
            if building_id == "heat_grid":
                # For each component, sum up the CO2 contributions to the overall system
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["battery_dataclass_"+str(key)].name]["investment_co2"] for key,_ in battery_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass_"+str(key)].name]["investment_co2"] for key,_ in hot_water_tank_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["gas_heater_dataclass_"+str(key)].name]["investment_co2"] for key,_ in gas_heater_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["chp_dataclass_"+str(key)].name]["investment_co2"] for key,_ in chp_config.items())
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass_"+str(key)].name]["investment_co2"] for key,_ in air_heat_pump_config.items())
                co2_investment += final_results["heat_grid"]["heat_grid_investment"]["investment_co2"]

            else:
                co2_investment += sum(final_results[building_id][dataclasses[building_id]["pv_dataclass_"+str(key)].name]["investment_co2"] for key,_ in pv_system_config.items())

                co2_investment += final_results[building_id][dataclasses[building_id]["building_dataclass"].name]["investment_co2"
                                    ]
        co2_operation = final_results[electricity_grid_dataclass.name]["flow_from_grid_co2"
                                ]-final_results[electricity_grid_dataclass.name]["flow_into_grid_co2"
                                ]+final_results[natural_gas_grid_dataclass.name]["flow_from_grid_co2"
                                ]+final_results[bio_gas_grid_dataclass.name]["flow_from_grid_co2"
                                ]+final_results[hydrogen_grid_dataclass.name]["flow_from_grid_co2"
                                ]

        co2_oemof_model = model.total_limit_co2()

        print("co2_constraint: ", co2_oemof_model)
        print("co2_post_process_inv: ", co2_investment)
        print("co2_post_process_oper: ", co2_operation)
        print("objective",str(meta_results["objective"]))
        print("elect_from_grid: "+str(sum(final_results[electricity_grid_dataclass.name]["flow_from_grid"])/1000))
        print("elect_into_grid: "+str(sum(final_results[electricity_grid_dataclass.name]["flow_into_grid"])/1000))
        print("elect_from_grid: "+str((final_results[electricity_grid_dataclass.name]["flow_from_grid"].sum())/1000))
        print("elect_into_grid: "+str((final_results[electricity_grid_dataclass.name]["flow_into_grid"].sum())/1000))
        final_results["co2_oemof_model"] = co2_oemof_model
        final_results["co2_operation"] = co2_operation
        final_results["co2_investment"] = co2_investment
        final_results["totex"] = meta_results["objective"]
        final_results["totex_oemof_model"] = meta_results["objective"]
        final_results["price_scenario_name"] = _normalize_price_scenario_name(price_scenario)
        final_results["price_scenario"] = price_scenario_config
        if SOLVER == "gurobi":
            return final_results, co2_oemof_model, meta_results["solver"]["Wall time"]
        else:
            solver_time_s = float(solve_result.solver.time)
            print("solve_time: "+str(solver_time_s))
            return final_results, co2_oemof_model, solver_time_s
    except Exception as e:
        print(e)
        return None, None, None


def check_possible_buildings_for_heat_grid_temp(building_row, building_type, epw_path, directory_path, data, number_of_time_steps,data_classes_comp,ev,time_index,heat_grid_temperature):
        building_id = building_row['building_id']
        tabula_year_class = building_row['tabula_year_class']
        building_floor_area = building_row['net_floor_area']
        number_of_occupants = building_row['number_of_residents']
        number_of_households = building_row['number_of_apartments']
        number_of_buildings_in_cluster = building_row['buildings_in_cluster']

        # Zuordnung Baujahr
        year_map = {
            1: 1850, 2: 1910, 3: 1930, 4: 1950,
            5: 1960, 6: 1970, 7: 1980, 8: 1990,
            9: 2000, 10: 2005, 11: 2010, 12: 2020
        }
        year_of_construction = year_map.get(tabula_year_class, 2000)  # fallback

        buildung_dict={}
        flow_temperature_arriving_at_building = heat_grid_temperature - 10
        for refurbishment in ["no_refurbishment","usual_refurbishment","advanced_refurbishment","GEG_standard"]:
            building_in_loop = ThermalBuilding(
                name=f"building_{building_id}",
                floor_area=building_floor_area,
                number_of_occupants=number_of_occupants,
                number_of_household=number_of_households,
                country="DE",
                construction_year=year_of_construction,
                class_building="average",
                building_type=building_type,
                refurbishment_status=refurbishment,
                heat_level_calculation=True,
                time_index=time_index,
            )
            if building_in_loop.level_heating_demand < flow_temperature_arriving_at_building:
                building_in_loop.level_heating_demand = flow_temperature_arriving_at_building
            buildung_dict[refurbishment] = building_in_loop
        matching_buildings = {key: value for key, value in buildung_dict.items() if
                              value.level_heating_demand <= flow_temperature_arriving_at_building}

        if len(matching_buildings) == 0 and flow_temperature_arriving_at_building ==40:
            buildung_dict = {}
            building = ThermalBuilding(
                    name=f"building_{building_id}",
                    floor_area=building_floor_area,
                    number_of_occupants=number_of_occupants,
                    number_of_household=number_of_households,
                    country="DE",
                    construction_year=year_of_construction,
                    class_building="average",
                    building_type=building_type,
                    refurbishment_status="advanced_refurbishment",
                    heat_level_calculation=True,
                    time_index=time_index,
                )
            if building.level_heating_demand ==50:
                building.capex_annuity = building.capex_annuity * 1.25
                building.co2_cost = building.co2_cost * 1.25
                building.level_heating_demand = 40
                buildung_dict["advanced_refurbishment"] = building
                matching_buildings = buildung_dict
            elif building.level_heating_demand ==60:
                building.capex_annuity = building.capex_annuity * 1.5
                building.co2_cost = building.co2_cost * 1.5
                building.level_heating_demand = 40
                buildung_dict["advanced_refurbishment"] = building
                matching_buildings = buildung_dict
            elif building.level_heating_demand ==70:
                building.capex_annuity = building.capex_annuity * 1.75
                building.co2_cost = building.co2_cost * 1.75
                building.level_heating_demand = 40
                buildung_dict["advanced_refurbishment"] = building
                matching_buildings = buildung_dict
        print(building_id)
        print(heat_grid_temperature)

        #assert matching_buildings, "Fehler: Es wurden keine Gebäudej gefunden, die den gewünschten Heizbedarf entsprechen."

        min_capex_building = min(matching_buildings, key=lambda x: matching_buildings[x].capex_annuity)


        return matching_buildings


def process_cluster(building,building_id,building_row, epw_path,building_type, directory_path, data, number_of_time_steps,
                    data_classes_comp, ev, time_index):

    # Zuordnung Baujahr
    year_map = {
        1: 1850, 2: 1910, 3: 1930, 4: 1950,
        5: 1960, 6: 1970, 7: 1980, 8: 1990,
        9: 2000, 10: 2005, 11: 2010, 12: 2020
    }
    building_id = building_row['building_id']
    tabula_year_class = building_row['tabula_year_class']
    building_floor_area = building_row['net_floor_area']
    building_roof_area = building_row['roof_surface_area']
    azimuth = building_row['azimuth']
    tilt = building_row['tilt']
    number_of_occupants = building_row['number_of_residents']
    number_of_households = building_row['number_of_apartments']
    number_of_buildings_in_cluster = building_row['buildings_in_cluster']

    # Zuordnung Baujahr
    year_map = {
        1: 1850, 2: 1910, 3: 1930, 4: 1950,
        5: 1960, 6: 1970, 7: 1980, 8: 1990,
        9: 2000, 10: 2005, 11: 2010, 12: 2020
    }
    year_of_construction = year_map.get(tabula_year_class, 2000)  # fallback

    # Demands laden
    with open(os.path.join(directory_path, f"{building_id}_demand_{ev}.pkl"), "rb") as f:
        demand = pickle.load(f)

    electricity_cols = [col for col in demand.columns if col.startswith("Electricity")]
    demand_electricity = (demand[electricity_cols].sum(axis=1) * 1000).tolist()
    warm_water_cols = [col for col in demand.columns if col.startswith("Warm Water_")]
    demand_warm_water = demand[warm_water_cols].sum(axis=1).tolist()

    # Datenklassen
    electricity_demand = ElectricityDemand(name=f"e_demand_{building_id}", value_list=demand_electricity)
    heat_demand = WarmWater(name=f"ww_demand_{building_id}", value_list=demand_warm_water, level=40)

    heat_demand_worst_case_building = ThermalBuilding(
        name=f"building_{building_id}",
        floor_area=building_floor_area,
        number_of_occupants=number_of_occupants,
        number_of_household=number_of_households,
        country="DE",
        construction_year=year_of_construction,
        class_building="average",
        building_type=building_type,
        refurbishment_status="no_refurbishment",
        heat_level_calculation=True,
        time_index=time_index,
    )
    heat_demand_worst_case = (max(heat_demand_worst_case_building.value_list) + max(heat_demand.value_list) ) * number_of_buildings_in_cluster

    # PV-Ertrag pro Watt
    pv_yield_per_wp = simulate_pv_yield(
        pv_nominal_power_in_watt=1,
        tilt=tilt,
        azimuth=azimuth,
        epw_path=epw_path
    )
    dict_pv_systems = {}
    for key, config in pv_system_config.items():
        pv_system_config_building = copy.deepcopy(config)
        pv = PVSystem(
            investment=True,
            name=f"pv_system_{building_id}_{key}",
            value_list=pv_yield_per_wp.tolist(),
            investment_component=pv_system_config_building
        )
        pv.update_maximum_investment_pv_capacity_based_on_area(building.get_roof_area_for_pv(building_roof_area))
        data[pv.name] = pv.value_list
        dict_pv_systems[key] = pv

    # Spalten hinzufügen
    data[electricity_demand.name] = electricity_demand.value_list
    data[heat_demand.name] = heat_demand.value_list
    data[building.name] = building.value_list

    data_classes_comp[building_id] = {"electricity_demand": electricity_demand,
                                      "pv_system": dict_pv_systems,
                                      "building": building,
                                      "heat_demand": heat_demand,
                                      "building_type": building_type}
    return data, data_classes_comp ,heat_demand_worst_case


def _safe_load_cluster_pickle(path):
    if not os.path.exists(path):
        return pd.DataFrame()
    with open(path, "rb") as f:
        data = pickle.load(f)
    if isinstance(data, pd.DataFrame):
        return data
    return pd.DataFrame(data)


def _is_reference_k(k_value):
    return isinstance(k_value, str) and k_value.lower() == "reference"


def _format_k_for_folder(k_value):
    if _is_reference_k(k_value):
        return "reference"
    return f"k{int(k_value):02d}"


def _discover_available_k_values(base_path, cluster_name, building_type):
    cluster_root = os.path.join(base_path, cluster_name)
    if not os.path.isdir(cluster_root):
        return []

    if building_type == "SFH":
        prefix = "sfh_cluster_k"
    elif building_type == "MFH":
        prefix = "mfh_cluster_k"
    else:
        raise ValueError(f"Unknown building type: {building_type}")

    values = set()
    for folder_name in os.listdir(cluster_root):
        folder_path = os.path.join(cluster_root, folder_name)
        if not os.path.isdir(folder_path):
            continue
        if folder_name.startswith(prefix):
            suffix = folder_name[len(prefix):]
            if suffix.isdigit():
                values.add(int(suffix))
    return sorted(values)


def _load_cluster_for_type(base_path, cluster_name, building_type, k_value):
    cluster_root = os.path.join(base_path, cluster_name)
    if _is_reference_k(k_value):
        gpkg_ueu = os.path.join(cluster_root, f"{cluster_name}.gpkg")
        if not os.path.exists(gpkg_ueu):
            raise FileNotFoundError(f"Reference gpkg not found: {gpkg_ueu}")
        gdf_ueu = gpd.read_file(gpkg_ueu)
        reference_cluster = gdf_ueu.loc[gdf_ueu["tabula_building_type"] == building_type].copy()
        # For reference runs each row represents one explicit building.
        reference_cluster["buildings_in_cluster"] = 1
        return reference_cluster

    k_token = f"k{int(k_value):02d}"
    prefix = "sfh" if building_type == "SFH" else "mfh"
    cluster_dir = os.path.join(cluster_root, f"{prefix}_cluster_{k_token}")
    return _safe_load_cluster_pickle(os.path.join(cluster_dir, f"{prefix}_cluster.pkl"))


def _centralized_output_dir_path(base_path, cluster_name, sfh_k_value, mfh_k_value):
    cluster_root = os.path.join(base_path, cluster_name)
    sfh_token = _format_k_for_folder(sfh_k_value)
    mfh_token = _format_k_for_folder(mfh_k_value)
    return os.path.join(cluster_root, f"combined_cluster_sfh_{sfh_token}_mfh_{mfh_token}", "centralized")


def _build_centralized_output_dir(base_path, cluster_name, sfh_k_value, mfh_k_value):
    output_dir = _centralized_output_dir_path(base_path, cluster_name, sfh_k_value, mfh_k_value)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _expected_scenario_tokens_for_mode(scenario_mode):
    if scenario_mode == "capex_min_only":
        return ["cmin"]
    if scenario_mode == "capex_max_only":
        return ["cmax"]
    if scenario_mode in {"capex_min_max_only", "cmin_cmax_only"}:
        return ["cmin", "cmax"]
    return None


def _missing_simple_co2_factors(
    base_path,
    cluster_name,
    sfh_k_value,
    mfh_k_value,
    heat_grid_temperature,
    scenario_mode,
    co2_reduction_factors,
):
    output_dir = _centralized_output_dir_path(base_path, cluster_name, sfh_k_value, mfh_k_value)
    scenario_tokens = _expected_scenario_tokens_for_mode(scenario_mode)
    if scenario_tokens is None:
        # For "all" mode the generated scenario names are only known after preprocessing,
        # so do not skip jobs based on an incomplete filesystem heuristic.
        return list(co2_reduction_factors)

    missing = []
    for co2_reduction_factor in co2_reduction_factors:
        co2_suffix = _co2_factor_to_suffix(co2_reduction_factor)
        all_expected_files_exist = True
        for scenario_token in scenario_tokens:
            simple_file_path = os.path.join(
                output_dir,
                f"res_cen_t{int(heat_grid_temperature)}_{scenario_token}_simple_co2_{co2_suffix}.pkl",
            )
            if not os.path.exists(simple_file_path):
                all_expected_files_exist = False
                break
        if not all_expected_files_exist:
            missing.append(co2_reduction_factor)
    return missing


def _script_base_path():
    return os.path.dirname(os.path.abspath(__file__))


def _normalize_result_root(raw_value, base_path):
    if raw_value is None:
        return None

    value = str(raw_value).strip()
    if not value or value.lower() in {"none", "default"}:
        return None

    if len(value) >= 2 and value[1] == ":":
        normalized = value
    else:
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme != "file":
            if not parsed.path:
                raise ValueError(f"Invalid storage URL without path: {value}")
            normalized = parsed.path
        elif parsed.scheme == "file":
            normalized = parsed.path
        else:
            normalized = value

    if not os.path.isabs(normalized):
        normalized = os.path.abspath(os.path.join(base_path, normalized))

    return os.path.normpath(normalized)


def _normalize_input_root(raw_value, base_path):
    return _normalize_result_root(raw_value, base_path)


def _get_input_root():
    return INPUT_ROOT if INPUT_ROOT else _script_base_path()


def _get_result_storage_root():
    return RESULT_STORAGE_ROOT if RESULT_STORAGE_ROOT else _script_base_path()


def _co2_factor_to_suffix(factor):
    value = float(factor)
    if value.is_integer():
        return str(int(value))
    s = f"{value:.6f}".rstrip("0").rstrip(".")
    if s.startswith("-0."):
        return "m0" + s[3:]
    if s.startswith("0."):
        return "0" + s[2:]
    return s.replace(".", "")


def _scenario_name_to_token(name):
    mapping = {
        "capex_min_per_building": "cmin",
        "capex_max_per_building": "cmax",
    }
    if name in mapping:
        return mapping[name]
    cleaned = "".join(ch for ch in str(name).lower() if ch.isalnum() or ch == "_")
    return cleaned[:20] if cleaned else "scenario"


def _atomic_pickle_dump(path, payload):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(payload, fh)


def _build_result_entries(
    final_results,
    co2,
    peak_reduction_factor,
    refurbish,
    time,
    price_scenario_name="ref",
    price_scenario=None,
):
    price_scenario_name = _normalize_price_scenario_name(price_scenario_name)
    if final_results is None:
        full_entry = {
            "results": None,
            "co2": None,
            "peak_reduction_factor": None,
            "refurbish": None,
            "price_scenario_name": price_scenario_name,
            "price_scenario": price_scenario,
            "totex": None,
            "peak": None,
            "electricity_grid": None,
            "peak_from_grid": None,
            "peak_into_grid": None,
            "time": None,
        }
        simple_entry = {
            "co2": None,
            "peak_reduction_factor": None,
            "refurbish": None,
            "price_scenario_name": price_scenario_name,
            "price_scenario": price_scenario,
            "totex": None,
            "peak": None,
            "electricity_grid": None,
            "peak_from_grid": None,
            "peak_into_grid": None,
            "time": None,
        }
        return full_entry, simple_entry

    peak_from_grid = final_results["Electricity"]["peak_from_grid"]
    peak_into_grid = final_results["Electricity"]["peak_into_grid"]
    peak = max(peak_from_grid, peak_into_grid)
    totex = final_results["totex"]
    full_entry = {
        "results": final_results,
        "co2": co2,
        "peak_reduction_factor": peak_reduction_factor,
        "refurbish": refurbish,
        "price_scenario_name": price_scenario_name,
        "price_scenario": price_scenario,
        "totex": totex,
        "peak": peak,
        "electricity_grid": final_results["Electricity"],
        "peak_from_grid": peak_from_grid,
        "peak_into_grid": peak_into_grid,
        "time": time,
    }
    simple_entry = {
        "co2": co2,
        "peak_reduction_factor": peak_reduction_factor,
        "refurbish": refurbish,
        "price_scenario_name": price_scenario_name,
        "price_scenario": price_scenario,
        "totex": totex,
        "peak": peak,
        "electricity_grid": final_results["Electricity"],
        "peak_from_grid": peak_from_grid,
        "peak_into_grid": peak_into_grid,
        "time": time,
    }
    return full_entry, simple_entry


def _resolve_requested_k_values(base_path, cluster_name, requested_k_values, building_type):
    available_values = _discover_available_k_values(base_path, cluster_name, building_type)
    reference_available = os.path.exists(os.path.join(base_path, cluster_name, f"{cluster_name}.gpkg"))

    if requested_k_values is None:
        resolved = list(available_values)
        if reference_available:
            resolved.insert(0, "reference")
        return resolved

    resolved = []
    for raw_value in requested_k_values:
        if _is_reference_k(raw_value):
            if reference_available:
                resolved.append("reference")
            else:
                print(f"Skipped reference for {cluster_name}: {cluster_name}.gpkg not found")
            continue
        try:
            k_value = int(raw_value)
        except Exception:
            print(f"Skipped invalid {building_type} k value for {cluster_name}: {raw_value}")
            continue
        if k_value in available_values:
            resolved.append(k_value)
        else:
            print(f"Skipped missing {building_type} k value for {cluster_name}: {k_value}")

    unique = []
    seen = set()
    for value in resolved:
        marker = value if isinstance(value, str) else int(value)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(value)
    return unique


def _select_scenarios_for_mode(scenarios, scenario_mode):
    if scenario_mode in (None, "all"):
        return scenarios
    if scenario_mode == "capex_min_only":
        selected = [scenario for scenario in scenarios if scenario.get("name") == "capex_min_per_building"]
        if selected:
            return selected[:1]
        raise ValueError("Scenario mode 'capex_min_only' requested, but 'capex_min_per_building' was not found.")
    if scenario_mode == "capex_max_only":
        selected = [scenario for scenario in scenarios if scenario.get("name") == "capex_max_per_building"]
        if selected:
            return selected[:1]
        print(
            "skip scenario_mode=capex_max_only: "
            "'capex_max_per_building' was not found after duplicate removal. "
            "This usually means cmax is identical to another scenario for this cluster/temperature/k combination."
        )
        return []
    if scenario_mode in {"capex_min_max_only", "cmin_cmax_only"}:
        selected = [
            scenario
            for scenario in scenarios
            if scenario.get("name") in {"capex_min_per_building", "capex_max_per_building"}
        ]
        found_names = {scenario.get("name") for scenario in selected}
        missing_names = {"capex_min_per_building", "capex_max_per_building"} - found_names
        if missing_names:
            raise ValueError(
                "Scenario mode 'capex_min_max_only' requested, but the following "
                f"scenario(s) were not found: {', '.join(sorted(missing_names))}."
            )
        return selected
    raise ValueError(f"Unknown scenario_mode: {scenario_mode}")


def run_main(
        heat_grid_temperature,
        ueu,
        heat_grid_length,
        sfh_k_value,
        mfh_k_value,
        scenario_mode="all",
        co2_reduction_factors_to_run=None,
        price_scenario_name="ref",
):
    base_path = _get_input_root()
    result_storage_root = _get_result_storage_root()
    price_scenario_name = _normalize_price_scenario_name(price_scenario_name)
    price_scenario_config = _resolve_price_scenario_config(price_scenario_name)
    output_cluster_name = _scenario_output_cluster_name(ueu, price_scenario_name)
    directory_path =os.path.join(base_path, ueu)
    number_of_time_steps = 8760
    sfh_cluster = _load_cluster_for_type(base_path, ueu, "SFH", sfh_k_value)
    mfh_cluster = _load_cluster_for_type(base_path, ueu, "MFH", mfh_k_value)
    combined_frames = [df for df in (sfh_cluster, mfh_cluster) if not df.empty]
    if not combined_frames:
        raise ValueError(
            f"No buildings found for cluster='{ueu}' with sfh={sfh_k_value}, mfh={mfh_k_value}"
        )
    print("BUILDING CLUSTER:")
    print(combined_frames)
    combined_cluster = pd.concat(combined_frames, ignore_index=True)
    output_dir = _build_centralized_output_dir(result_storage_root, output_cluster_name, sfh_k_value, mfh_k_value)
    ev = "no_EV"
    if True:

        main_path = get_project_root()
        data_classes_comp = pd.DataFrame()
        epw_path = os.path.join(
                main_path,
                "thermal_building_model",
                "input",
                "weather_files",
                "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
            )
        location = calculate_gain_by_sun.Location(
            epwfile_path=os.path.join(
                main_path,
                "thermal_building_model",
                "input",
                "weather_files",
                "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
            ),
        )
        data = pd.DataFrame()
        data["air_temperature"] = location.weather_data["drybulb_C"].to_list()
        date_time_index = solph.create_time_index(2025, number=number_of_time_steps - 1)
        data.index = date_time_index
        matching_buildings_sfh = {}
        for index, building_row in sfh_cluster.iterrows():
            matching_buildings_sfh[building_row.building_id] = check_possible_buildings_for_heat_grid_temp(
                building_row=building_row,
                building_type="SFH",
                epw_path=epw_path,
                directory_path=directory_path,
                data=data,
                number_of_time_steps=number_of_time_steps,
                data_classes_comp = data_classes_comp,
                ev=ev,
                time_index=date_time_index,
                heat_grid_temperature=heat_grid_temperature
            )
        matching_buildings_mfh = {}
        for index, building_row in mfh_cluster.iterrows():
            matching_buildings_mfh[building_row.building_id] = check_possible_buildings_for_heat_grid_temp(
                building_row=building_row,
                building_type="MFH",
                epw_path=epw_path,
                directory_path=directory_path,
                data=data,
                number_of_time_steps=number_of_time_steps,
                data_classes_comp = data_classes_comp,
                ev =ev,
                time_index=date_time_index,
                heat_grid_temperature=heat_grid_temperature
            )
        scenarios, buildings_all, available_by_building = build_scenarios(
            matching_buildings_sfh=matching_buildings_sfh,
            matching_buildings_mfh=matching_buildings_mfh,
            n_random=4,
            seed=1,
        )
        if scenario_mode in (None, "all"):
            seen = set()
            unique_scenarios = []
            for scenario in scenarios:
                # Convert choice dict to a hashable, order-independent representation
                choice_signature = frozenset(scenario["choice"].items())
                if choice_signature not in seen:
                    seen.add(choice_signature)
                    unique_scenarios.append(scenario)
            scenarios = unique_scenarios
        print(len(scenarios), scenarios[0]["name"], list(scenarios[0]["choice"].items())[:3])

        print(f"Szenarien vor Dedup: {len(scenarios)}")

        scenarios = _select_scenarios_for_mode(scenarios, scenario_mode)
        if scenario_mode in (None, "all"):
            scenarios = remove_duplicate_scenarios(scenarios)
        if not scenarios:
            print(
                "No scenarios selected after scenario-mode filtering. "
                f"Skipping optimization for T={heat_grid_temperature}, cluster={ueu}, "
                f"sfh={_format_k_for_folder(sfh_k_value)}, mfh={_format_k_for_folder(mfh_k_value)}, "
                f"scenario_mode={scenario_mode}."
            )
            return

        path = os.path.join(output_dir, "cen_optimizations_scenarios_"+str(heat_grid_temperature)+".pkl")

        with open(path, "wb") as f:
            pickle.dump(scenarios, f)

        print("Gespeichert:", path)
        print(f"Szenarien aktiv ({scenario_mode}): {len(scenarios)}")
        for scenario in scenarios:
            location = calculate_gain_by_sun.Location(
                epwfile_path=os.path.join(
                    main_path,
                    "thermal_building_model",
                    "input",
                    "weather_files",
                    "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
                ),
            )
            data = pd.DataFrame()
            data["air_temperature"] = location.weather_data["drybulb_C"].to_list()
            date_time_index = solph.create_time_index(2025, number=number_of_time_steps - 1)
            data.index = date_time_index
            name_of_scenario = scenario["name"]
            heat_demand_worst_case = 0
            for index, building_row in sfh_cluster.iterrows():
                refurbish = scenario["choice"][building_row["building_id"]]
                building = buildings_all[building_row["building_id"]][refurbish]
                data,data_classes_comp,heat_demand_worst_case_var = process_cluster(
                    building = building,
                    building_id = building_row["building_id"],
                    building_row = building_row,
                    building_type = "SFH",
                    epw_path=epw_path,
                    directory_path=directory_path,
                    data=data,
                    number_of_time_steps=number_of_time_steps,
                    data_classes_comp = data_classes_comp,
                    ev=ev,
                    time_index=date_time_index
                )
                heat_demand_worst_case = heat_demand_worst_case+heat_demand_worst_case_var
            for index, building_row in mfh_cluster.iterrows():
                refurbish = scenario["choice"][building_row["building_id"]]
                building = buildings_all[building_row["building_id"]][refurbish]
                data,data_classes_comp,heat_demand_worst_case_var = process_cluster(
                    building=building,
                    building_id=building_row["building_id"],
                    building_row=building_row,
                    building_type="MFH",
                    epw_path=epw_path,
                    directory_path=directory_path,
                    data=data,
                    number_of_time_steps=number_of_time_steps,
                    data_classes_comp = data_classes_comp,
                    ev =ev,
                    time_index=date_time_index
                )
                heat_demand_worst_case = heat_demand_worst_case + heat_demand_worst_case_var
            typical_periods = 30
            hours_per_period = 24

            aggregation1 = tsam.TimeSeriesAggregation(
                timeSeries=data.iloc[:8760],
                noTypicalPeriods=typical_periods,
                hoursPerPeriod=hours_per_period,
                clusterMethod="k_means",

            )
            aggregation1.createTypicalPeriods()
            cluster_occurence=aggregation1.clusterPeriodNoOccur
            data = aggregation1.typicalPeriods
            t1_agg = pd.date_range(
                "2025-01-01", periods=typical_periods * hours_per_period, freq="h"
            )
            if False:
                for index, row in combined_cluster.iterrows():
                    try:
                        building_id = row['building_id']
                        buildings_in_cluster = row['buildings_in_cluster']

                        # Identify the corresponding 'ww_demand' column for each building_id
                        ww_demand_column = f"ww_demand_{building_id}"
                        e_demand_column = f"e_demand_{building_id}"
                        building_demand_column = f"building_{building_id}"
                        # Multiply the ww_demand column by the number of buildings in the cluster
                        data[ww_demand_column] = data[ww_demand_column] * buildings_in_cluster
                        data[e_demand_column] = data[e_demand_column] * buildings_in_cluster
                        data[building_demand_column] = data[building_demand_column] * buildings_in_cluster
                    except:
                        print(index)
                all_ww_demand_columns = [col for col in data.columns if 'ww_demand' in col]
                all_e_demand_columns = [col for col in data.columns if 'e_demand' in col]
                all_building_demand_columns = [col for col in data.columns if 'building' in col]

                data['ww_demand_total'] = data[all_ww_demand_columns].sum(axis=1)
                data['e_demand_total'] = data[all_e_demand_columns].sum(axis=1)
                data['building_total'] = data[all_building_demand_columns].sum(axis=1)

            final_results_ref, co2_ref, time = run_model(
                None,
                None,
                data,
                aggregation1,
                t1_agg,
                data_classes_comp,
                combined_cluster,
                heat_grid_temperature,
                cluster_occurence,
                heat_demand_worst_case,
                heat_grid_length,
                price_scenario=price_scenario_name,
            )
            co2_reduction_factor_ref = 1
            peak_reduction_factor_ref = 1
            results_loop_to_save = {}

            results_loop_to_save[(co2_reduction_factor_ref, peak_reduction_factor_ref)] = {
                "results": final_results_ref,
                "co2": co2_ref,
                "peak_reduction_factor" : peak_reduction_factor_ref,
                "price_scenario_name": price_scenario_name,
                "price_scenario": price_scenario_config,
                "totex": final_results_ref["totex"],
                "peak": max(final_results_ref["Electricity"]["peak_from_grid"],
                                      final_results_ref["Electricity"]["peak_into_grid"]),
                "time":time

            }
            co2_reference_save = co2_ref
            peak_reference_save = max(final_results_ref["Electricity"]["peak_from_grid"],
                                      final_results_ref["Electricity"]["peak_into_grid"])
            hp_power = 0
            gas_heater_power = 0
            if True:
                building_id_in_cluster = "heat_grid"
                for i in range(1, 2):
                    hp_power += \
                    final_results_ref[building_id_in_cluster]["hp_" + building_id_in_cluster + "_" + str(i)][
                        "capacity"]
                    gas_heater_power += \
                        final_results_ref[building_id_in_cluster][
                            "gas_heater_" + building_id_in_cluster + "_" + str(i)]["capacity"]
                if hp_power >= gas_heater_power:
                    step = 0.05
                    co2_reduction_factors = [round(x, 3) for x in
                                             [1 - i * step for i in range(int((1.0 - (-0.1)) / step) + 1)]]

            co2_reduction_factors = list(DEFAULT_CO2_REDUCTION_FACTORS)
            if co2_reduction_factors_to_run is not None:
                requested_co2_factors = {
                    round(float(co2_reduction_factor), 6)
                    for co2_reduction_factor in co2_reduction_factors_to_run
                }
                co2_reduction_factors = [
                    co2_reduction_factor
                    for co2_reduction_factor in co2_reduction_factors
                    if round(float(co2_reduction_factor), 6) in requested_co2_factors
                ]
                print(f"CO2 factors selected for this job: {co2_reduction_factors}")
            if not co2_reduction_factors:
                print("No CO2 factors selected for this job.")
                continue
            references = ["co2"]#["co2","peak"]
            for ref in references:
                if ref=="co2":
                    peak_reference = peak_reference_save
                    co2_reference = co2_reference_save
                    scenario_token = _scenario_name_to_token(name_of_scenario)
                    result_prefix = os.path.join(
                        output_dir,
                        f"res_cen_t{int(heat_grid_temperature)}_{scenario_token}",
                    )
                    for co2_reduction_factor in co2_reduction_factors:
                        first_co2_run_in_peak_loop = True
                        peak_reduction_factors = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.01]
                        results_for_co2_step_full = {}
                        results_for_co2_step_simple = {}

                        if co2_reference > 0:
                            co2_new = co2_reference * co2_reduction_factor
                        else:
                            co2_new = co2_reference * (1+1-co2_reduction_factor)
                        print("START PEAK LOOP")
                        for peak_reduction_factor in peak_reduction_factors:
                            print("co2_reduction_factor: "+str(co2_reduction_factor))
                            print("peak_reduction_factor: " + str(peak_reduction_factor))
                            if first_co2_run_in_peak_loop:
                                peak_new =False
                            else:

                                peak_new = peak_reference * peak_reduction_factor

                            final_results, co2,time  = run_model(
                                co2_new,
                                peak_new,
                                data,
                                aggregation1,
                                t1_agg,
                                data_classes_comp,
                                combined_cluster,
                                heat_grid_temperature,
                                cluster_occurence,
                                heat_demand_worst_case,
                                heat_grid_length,
                                price_scenario=price_scenario_name,
                            )
                            key = (co2_reduction_factor, peak_reduction_factor, ref)
                            full_entry, simple_entry = _build_result_entries(
                                final_results=final_results,
                                co2=co2,
                                peak_reduction_factor=peak_reduction_factor,
                                refurbish=name_of_scenario,
                                time=time,
                                price_scenario_name=price_scenario_name,
                                price_scenario=price_scenario_config,
                            )
                            results_for_co2_step_full[key] = full_entry
                            results_for_co2_step_simple[key] = simple_entry

                            if final_results is None:
                                if first_co2_run_in_peak_loop:
                                    first_co2_run_in_peak_loop = False
                                    peak =False
                                    peak_reference = peak
                                break
                            else:
                                peak = full_entry["peak"]
                                if first_co2_run_in_peak_loop:
                                    first_co2_run_in_peak_loop = False
                                    peak_reference = peak
                        co2_suffix = _co2_factor_to_suffix(co2_reduction_factor)
                        full_file_path = result_prefix + "_co2_" + co2_suffix + ".pkl"
                        simple_file_path = result_prefix + "_simple_co2_" + co2_suffix + ".pkl"
                        _atomic_pickle_dump(full_file_path, results_for_co2_step_full)
                        _atomic_pickle_dump(simple_file_path, results_for_co2_step_simple)
                        print(f"saved co2 step {co2_reduction_factor} -> {full_file_path}")
                elif ref=="peak":
                    peak_reference = peak_reference_save
                    co2_reference = co2_reference_save
                    co2_reduction_factors_saver=co2_reduction_factors
                    peak_reduction_factors = [1, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1,0.01]
                    for peak_reduction_factor in peak_reduction_factors:
                        first_peak_run_in_co2_loop = True
                        co2_reduction_factors = co2_reduction_factors_saver

                        peak_new = peak_reference * peak_reduction_factor

                        print("START PEAK LOOP")
                        for co2_reduction_factor in co2_reduction_factors:
                            print("co2_reduction_factor: "+str(co2_reduction_factor))
                            print("peak_reduction_factor: " + str(peak_reduction_factor))
                            if first_peak_run_in_co2_loop:
                                co2_new =None
                            else:
                                if co2_reference > 0:
                                    co2_new = co2_reference * co2_reduction_factor
                                else:
                                    co2_new = co2_reference * (1 + 1 - co2_reduction_factor)
                            final_results, co2,time  = run_model(
                                co2_new,
                                peak_new,
                                data,
                                aggregation1,
                                t1_agg,
                                data_classes_comp,
                                combined_cluster,
                                heat_grid_temperature,
                                cluster_occurence,
                                heat_demand_worst_case,
                                heat_grid_length,
                                price_scenario=price_scenario_name,
                            )
                            if final_results is None:
                                results_loop_to_save[(co2_reduction_factor, peak_reduction_factor,ref)] = {
                                    "results": None,
                                    "co2": None,
                                    "peak_reduction_factor": None,
                                    "refurbish": None,
                                    "price_scenario_name": price_scenario_name,
                                    "price_scenario": price_scenario_config,
                                    "totex": None,
                                    "peak": None,
                                    "time":None
                                }
                                if first_peak_run_in_co2_loop:
                                    first_peak_run_in_co2_loop = False
                                    co2_new =False
                                    co2_reference = co2_new
                                break
                            else:
                                totex = final_results["totex"]
                                peak = max(final_results["Electricity"]["peak_from_grid"],
                                      final_results["Electricity"]["peak_into_grid"])
                                if first_peak_run_in_co2_loop:
                                    first_peak_run_in_co2_loop = False
                                    peak_reference = peak

                                results_loop_to_save[(co2_reduction_factor, peak_reduction_factor,ref)] = {
                                    "results": final_results,
                                    "co2": co2,
                                    "peak_reduction_factor": peak_reduction_factor,
                                    "price_scenario_name": price_scenario_name,
                                    "price_scenario": price_scenario_config,
                                    "totex": totex,
                                    "peak": peak,
                                    "time": time
                                }
                        print("FINISHED PEAK LOOP START SAVING")
                        scenario_token = _scenario_name_to_token(name_of_scenario)
                        peak_suffix = _co2_factor_to_suffix(peak_reduction_factor)
                        file_path = os.path.join(
                            output_dir,
                            f"res_cen_t{int(heat_grid_temperature)}_{scenario_token}_peak_{peak_suffix}.pkl",
                        )
                        _atomic_pickle_dump(file_path, results_loop_to_save)
                        print(f"saved peak step {peak_reduction_factor} -> {file_path}")
            # Results are written per co2 step (17_dec-style) inside the co2 loop.

import multiprocessing as mp
import traceback
from datetime import datetime

DEFAULT_HEAT_GRID_SUPPLY_TEMPERATURES = [50, 80]
DEFAULT_SOLVER = "gurobi"
DEFAULT_SOLVER_THREADS = "auto"
DEFAULT_UEU_CASES = [
    ("processed_bds_in_DENI03403000SEC5658", 1146.15),
]
DEFAULT_K_VALUES_TO_OPTIMIZE_SFH = [1]
DEFAULT_K_VALUES_TO_OPTIMIZE_MFH = [1]
DEFAULT_SCENARIO_MODE = "capex_min_max_only"  # all | capex_min_only | capex_max_only | capex_min_max_only
DEFAULT_CO2_REDUCTION_FACTORS = [
    1,
    0.95,
    0.9,
    0.85,
    0.8,
    0.75,
    0.7,
    0.65,
    0.6,
    0.55,
    0.5,
    0.45,
    0.4,
    0.35,
    0.3,
    0.25,
    0.2,
    0.15,
    0.1,
    0.05,
    0.01,
    -0.01,
    -0.05,
    -0.1,
    -0.2,
]
RESULT_STORAGE_ROOT = None
INPUT_ROOT = None

ERROR_DIR = "error_logs"
os.makedirs(ERROR_DIR, exist_ok=True)
SOLVER = DEFAULT_SOLVER
SOLVER_THREADS = DEFAULT_SOLVER_THREADS


def _parse_csv_tokens(raw):
    if raw is None:
        return []
    return [token.strip() for token in str(raw).split(",") if token.strip()]


def _parse_k_values(raw):
    values = []
    for token in _parse_csv_tokens(raw):
        if token.lower() == "reference":
            values.append("reference")
        else:
            values.append(int(token))
    return values


def _parse_int_values(raw, label):
    values = []
    for token in _parse_csv_tokens(raw):
        try:
            values.append(int(token))
        except Exception as exc:
            raise ValueError(f"Invalid {label} value '{token}'") from exc
    return values


def _parse_float_values(raw, label):
    values = []
    for token in _parse_csv_tokens(raw):
        try:
            values.append(float(token))
        except Exception as exc:
            raise ValueError(f"Invalid {label} value '{token}'") from exc
    return values


def _resolve_solver_threads(raw_value, n_cores, requested_workers):
    value = str(raw_value).strip().lower()
    if not value or value == "auto":
        if requested_workers is None:
            return 1
        return max(1, n_cores // max(1, int(requested_workers)))
    try:
        threads = int(value)
    except Exception as exc:
        raise ValueError("--solver-threads must be a positive integer or 'auto'") from exc
    if threads <= 0:
        raise ValueError("--solver-threads must be > 0")
    return threads


def _parse_ueu_cases(raw):
    if not raw:
        return list(DEFAULT_UEU_CASES)
    out = []
    for token in _parse_csv_tokens(raw):
        parts = token.split(":")
        if len(parts) != 2:
            raise ValueError(f"Invalid ueu case '{token}'. Expected format: <ueu>:<length>")
        out.append((parts[0].strip(), float(parts[1])))
    return out


def _build_all_jobs(
    base_path,
    result_storage_root,
    ueu_cases,
    heat_grid_supply_temperatures,
    sfh_requested,
    mfh_requested,
    scenario_mode,
    co2_reduction_factors,
    price_scenarios,
):
    jobs = []
    for heat_grid_temperature in heat_grid_supply_temperatures:
        for (ueu, heat_grid_length) in ueu_cases:
            sfh_k_values = _resolve_requested_k_values(
                base_path=base_path,
                cluster_name=ueu,
                requested_k_values=sfh_requested,
                building_type="SFH",
            )
            mfh_k_values = _resolve_requested_k_values(
                base_path=base_path,
                cluster_name=ueu,
                requested_k_values=mfh_requested,
                building_type="MFH",
            )

            if not sfh_k_values:
                print(f"No runnable SFH k-values for cluster {ueu}")
                continue
            if not mfh_k_values:
                print(f"No runnable MFH k-values for cluster {ueu}")
                continue

            for sfh_k_value in sfh_k_values:
                for mfh_k_value in mfh_k_values:
                    for price_scenario_name in price_scenarios:
                        price_scenario_name = _normalize_price_scenario_name(price_scenario_name)
                        output_cluster_name = _scenario_output_cluster_name(ueu, price_scenario_name)
                        missing_co2_factors = _missing_simple_co2_factors(
                            base_path=result_storage_root,
                            cluster_name=output_cluster_name,
                            sfh_k_value=sfh_k_value,
                            mfh_k_value=mfh_k_value,
                            heat_grid_temperature=heat_grid_temperature,
                            scenario_mode=scenario_mode,
                            co2_reduction_factors=co2_reduction_factors,
                        )
                        if not missing_co2_factors:
                            print(
                                "skip complete simple: "
                                f"{output_cluster_name} | T={heat_grid_temperature} | "
                                f"sfh={_format_k_for_folder(sfh_k_value)} | "
                                f"mfh={_format_k_for_folder(mfh_k_value)} | "
                                f"price_scenario={price_scenario_name}"
                            )
                            continue
                        print(
                            "missing simple co2 factors: "
                            f"{output_cluster_name} | T={heat_grid_temperature} | "
                            f"sfh={_format_k_for_folder(sfh_k_value)} | "
                            f"mfh={_format_k_for_folder(mfh_k_value)} | "
                            f"price_scenario={price_scenario_name} | "
                            f"co2={','.join(str(x) for x in missing_co2_factors)}"
                        )
                        jobs.append(
                            (
                                heat_grid_temperature,
                                ueu,
                                heat_grid_length,
                                sfh_k_value,
                                mfh_k_value,
                                scenario_mode,
                                missing_co2_factors,
                                price_scenario_name,
                            )
                        )
    return jobs


def wrapper(args):
    global SOLVER, SOLVER_THREADS
    (
        job_idx,
        host_name,
        solver,
        solver_threads,
        heat_grid_temperature,
        ueu,
        heat_grid_length,
        sfh_k_value,
        mfh_k_value,
        scenario_mode,
        missing_co2_factors,
        price_scenario_name,
    ) = args
    SOLVER = solver
    SOLVER_THREADS = solver_threads
    try:
        print(
            f"host={host_name} job={job_idx} start: temp={heat_grid_temperature} | ueu={ueu} | length={heat_grid_length} "
            f"| sfh={_format_k_for_folder(sfh_k_value)} | mfh={_format_k_for_folder(mfh_k_value)} "
            f"| scenario_mode={scenario_mode} | solver={SOLVER} | solver_threads={SOLVER_THREADS} "
            f"| price_scenario={price_scenario_name} "
            f"| co2={','.join(str(x) for x in missing_co2_factors)}"
        )
        run_main(
            heat_grid_temperature,
            ueu,
            heat_grid_length,
            sfh_k_value,
            mfh_k_value,
            scenario_mode=scenario_mode,
            co2_reduction_factors_to_run=missing_co2_factors,
            price_scenario_name=price_scenario_name,
        )
    except Exception as e:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_ueu = ueu.replace(os.sep, "_")
        safe_host = str(host_name).replace(os.sep, "_")
        safe_price = str(price_scenario_name).replace(os.sep, "_")
        filename = (
            f"error_{safe_host}_{safe_ueu}_job{job_idx}_T{heat_grid_temperature}"
            f"_sfh_{_format_k_for_folder(sfh_k_value)}"
            f"_mfh_{_format_k_for_folder(mfh_k_value)}"
            f"_price_{safe_price}_{timestamp}.txt"
        )
        path = os.path.join(ERROR_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"host_name: {host_name}\n")
            f.write(f"job_idx: {job_idx}\n")
            f.write(f"heat_grid_temperature: {heat_grid_temperature}\n")
            f.write(f"ueu: {ueu}\n")
            f.write(f"heat_grid_length: {heat_grid_length}\n")
            f.write(f"sfh_k_value: {sfh_k_value}\n")
            f.write(f"mfh_k_value: {mfh_k_value}\n")
            f.write(f"scenario_mode: {scenario_mode}\n")
            f.write(f"price_scenario_name: {price_scenario_name}\n")
            f.write(f"solver: {SOLVER}\n")
            f.write(f"solver_threads: {SOLVER_THREADS}\n")
            f.write(f"missing_co2_factors: {missing_co2_factors}\n")
            f.write(f"exception: {repr(e)}\n\n")
            f.write("traceback:\n")
            f.write(traceback.format_exc())
        print(f"[ERROR] Logged to {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run centralized optimization with optional host job slicing.")
    parser.add_argument("--host-name", type=str, default="unknown")
    parser.add_argument("--job-start", type=int, default=0, help="Start index in global job list for this host.")
    parser.add_argument("--max-jobs", type=int, default=None, help="Maximum number of jobs this host should run.")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel worker processes on this host.")
    parser.add_argument("--serial", action="store_true", help="Run selected jobs sequentially.")
    parser.add_argument("--solver", type=str, default=DEFAULT_SOLVER, help="MILP solver backend, e.g. gurobi or scip.")
    parser.add_argument(
        "--solver-threads",
        type=str,
        default=DEFAULT_SOLVER_THREADS,
        help="Solver threads per job, or 'auto' to divide CPU cores by --workers.",
    )
    parser.add_argument(
        "--scenario-mode",
        type=str,
        default=DEFAULT_SCENARIO_MODE,
        choices=["all", "capex_min_only", "capex_max_only", "capex_min_max_only", "cmin_cmax_only"],
    )
    parser.add_argument(
        "--temps",
        type=str,
        default=",".join(str(x) for x in DEFAULT_HEAT_GRID_SUPPLY_TEMPERATURES),
        help="Comma-separated heat grid temperatures, e.g. 50,60,80",
    )
    parser.add_argument(
        "--sfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_SFH),
        help="Comma-separated SFH k values, e.g. reference,1,2,4",
    )
    parser.add_argument(
        "--mfh-k",
        type=str,
        default=",".join(str(x) for x in DEFAULT_K_VALUES_TO_OPTIMIZE_MFH),
        help="Comma-separated MFH k values, e.g. reference,1,2,3",
    )
    parser.add_argument(
        "--ueu-cases",
        type=str,
        default=",".join(f"{name}:{length}" for name, length in DEFAULT_UEU_CASES),
        help="Comma-separated UEU cases as <ueu>:<heat_grid_length>.",
    )
    parser.add_argument(
        "--co2-factors",
        type=str,
        default=",".join(str(x) for x in DEFAULT_CO2_REDUCTION_FACTORS),
        help="Comma-separated CO2 reduction factors expected as simple result files.",
    )
    parser.add_argument(
        "--price-scenarios",
        type=str,
        default=",".join(DEFAULT_PRICE_SCENARIOS),
        help="Comma-separated price scenarios, or 'all'. Uses helpers.price_scenarios.",
    )
    parser.add_argument(
        "--input-root",
        type=str,
        default="default",
        help=(
            "Base directory containing processed_bds input folders. "
            "Use 'default' to read near this script."
        ),
    )
    parser.add_argument(
        "--result-storage-root",
        type=str,
        default="default",
        help=(
            "Base directory for centralized results. "
            "Use 'default' to store near this script."
        ),
    )
    args = parser.parse_args()

    if args.job_start < 0:
        raise ValueError("--job-start must be >= 0")
    if args.max_jobs is not None and args.max_jobs <= 0:
        raise ValueError("--max-jobs must be > 0 when provided")
    if args.workers is not None and args.workers <= 0:
        raise ValueError("--workers must be > 0 when provided")
    if not str(args.solver).strip():
        raise ValueError("--solver must not be empty")

    heat_grid_supply_temperatures = _parse_int_values(args.temps, "temperature")
    sfh_requested = _parse_k_values(args.sfh_k)
    mfh_requested = _parse_k_values(args.mfh_k)
    ueu_cases = _parse_ueu_cases(args.ueu_cases)
    co2_reduction_factors = _parse_float_values(args.co2_factors, "CO2 reduction factor")
    price_scenarios = _parse_price_scenarios(args.price_scenarios)
    if not heat_grid_supply_temperatures:
        raise ValueError("No temperatures provided.")
    if not sfh_requested and not mfh_requested:
        raise ValueError("Both --sfh-k and --mfh-k are empty.")
    if not co2_reduction_factors:
        raise ValueError("No CO2 reduction factors provided.")
    if not price_scenarios:
        raise ValueError("No price scenarios provided.")

    script_base = _script_base_path()
    INPUT_ROOT = _normalize_input_root(args.input_root, script_base)
    RESULT_STORAGE_ROOT = _normalize_result_root(args.result_storage_root, script_base)
    if RESULT_STORAGE_ROOT:
        os.makedirs(RESULT_STORAGE_ROOT, exist_ok=True)

    SOLVER = str(args.solver).strip()
    base_path = INPUT_ROOT if INPUT_ROOT else script_base
    all_jobs_raw = _build_all_jobs(
        base_path=base_path,
        result_storage_root=RESULT_STORAGE_ROOT if RESULT_STORAGE_ROOT else base_path,
        ueu_cases=ueu_cases,
        heat_grid_supply_temperatures=heat_grid_supply_temperatures,
        sfh_requested=sfh_requested,
        mfh_requested=mfh_requested,
        scenario_mode=args.scenario_mode,
        co2_reduction_factors=co2_reduction_factors,
        price_scenarios=price_scenarios,
    )
    if not all_jobs_raw:
        print("No jobs to run.")
        raise SystemExit(0)

    total_jobs = len(all_jobs_raw)
    if args.job_start >= total_jobs:
        print(f"No jobs for host {args.host_name}: job_start={args.job_start} >= total_jobs={total_jobs}")
        raise SystemExit(0)

    end_idx = total_jobs if args.max_jobs is None else min(total_jobs, args.job_start + args.max_jobs)
    selected_jobs_raw = all_jobs_raw[args.job_start:end_idx]
    if not selected_jobs_raw:
        print("No selected jobs after slicing.")
        raise SystemExit(0)

    n_cores = os.cpu_count() or 1
    SOLVER_THREADS = _resolve_solver_threads(args.solver_threads, n_cores, args.workers)
    default_workers = max(1, n_cores // SOLVER_THREADS)
    workers = args.workers if args.workers is not None else default_workers
    workers = max(1, min(workers, len(selected_jobs_raw)))

    selected_jobs = [
        (args.job_start + idx, args.host_name, SOLVER, SOLVER_THREADS, *job)
        for idx, job in enumerate(selected_jobs_raw)
    ]

    print(
        f"host={args.host_name} total_jobs={total_jobs} "
        f"selected_range=[{args.job_start},{end_idx}) selected_jobs={len(selected_jobs)} "
        f"workers={workers} solver={SOLVER} solver_threads={SOLVER_THREADS} "
        f"price_scenarios={','.join(price_scenarios)} "
        f"input_root={base_path} result_storage_root={RESULT_STORAGE_ROOT if RESULT_STORAGE_ROOT else base_path}"
    )

    if args.serial or workers == 1:
        for job in selected_jobs:
            wrapper(job)
    else:
        with mp.Pool(processes=workers) as pool:
            pool.map(wrapper, selected_jobs)
