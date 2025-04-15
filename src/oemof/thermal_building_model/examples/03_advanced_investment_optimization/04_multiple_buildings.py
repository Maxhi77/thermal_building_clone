from oemof.solph.components import Converter
import copy
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, HeatGrid, GasGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier, \
    GasCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, WarmWater
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
from oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank
from oemof.thermal_building_model.oemof_facades.technologies.converter import AirHeatPump, GasHeater
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof.thermal_building_model.helpers.calculate_pv_electricity_yield import simulate_pv_yield
from oemof import solph
import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import os
import pickle
from oemof.thermal_building_model.helpers import calculate_gain_by_sun
from oemof.thermal_building_model.helpers.path_helper import get_project_root
from oemof.thermal_building_model.input.economics.investment_components import battery_config,hot_water_tank_config,air_heat_pump_config,gas_heater_config,pv_system_config

from oemof.thermal_building_model.tabula.tabula_reader import Building
import pprint as pp
import geopandas as gpd
import tsam.timeseriesaggregation as tsam

import pandas as pd
#  create solver
def run_model(co2_new,peak_new,refurbish,data,aggregation1,t1_agg,data_classes_comp,buildings_connected,combined_cluster):

    solver = "gurobi"
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

    if peak_new is None:
        electricity_grid_dataclass = ElectricityGrid()
    else:
        electricity_grid_dataclass = ElectricityGrid(max_peak_from_grid=peak_new)

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
    gas_grid_dataclass = GasGrid()
    gas_grid_bus_from_grid = gas_grid_dataclass.get_bus_from_grid()
    gas_grid_source = gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier()
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=gas_grid_bus_from_grid, target=gas_bus)


    gas = [gas_grid_bus_from_grid,gas_grid_source,gas_bus]
    es.add(*gas)
    component_per_building = {}

    dataclasses = {}
    components = {}
    for index, row in combined_cluster.iterrows():
        if index >=2:
            continue
        building_id =row['building_id']
        building_in_cluster =row['buildings_in_cluster']
        building_in_cluster=1
        dataclasses[building_id] = {}
        components[building_id] = {}
        electricity_carrier_dataclass_building = ElectricityCarrier(name="e_carrier_"+str(building_id))
        electricity_carrier_bus_building = electricity_carrier_dataclass_building.get_bus()
        if buildings_connected == "con":
            grid_into_converter_building = Converter(label="conv_e_into_grid_"+str(building_id),
                                                  inputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                                  outputs={electricity_carrier_bus: solph.flows.Flow()},
                                                  conversion_factors={electricity_carrier_bus_building: 1/building_in_cluster * 0.975})
            grid_from_converter_building = Converter(label="conv_e_from_grid_"+str(building_id),
                                                  inputs={electricity_carrier_bus: solph.flows.Flow()},
                                                  outputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                                  conversion_factors={electricity_carrier_bus_building: 1/ building_in_cluster * 0.975})
        elif buildings_connected =="uncon":
            grid_into_converter_building = Converter(label="conv_e_into_grid_" + str(building_id),
                                                     inputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                                     outputs={electricity_grid_bus_into_grid: solph.flows.Flow()},
                                                     conversion_factors={
                                                         electricity_carrier_bus_building: 1 / building_in_cluster })
            grid_from_converter_building = Converter(label="conv_e_from_grid_" + str(building_id),
                                                     inputs={electricity_grid_bus_from_grid: solph.flows.Flow()},
                                                     outputs={electricity_carrier_bus_building: solph.flows.Flow()},
                                                     conversion_factors={
                                                         electricity_carrier_bus_building: 1 / building_in_cluster })
        else:
            break

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

        max_required_heating = max(data["ww_demand_"+str(building_id)] + data["building_"+str(building_id)]) * 8


        heat_carrier_temperature_levels = [40]
        heat_carrier_dataclass = HeatCarrier(name="h_carrier_"+str(building_id),
            levels = heat_carrier_temperature_levels)
        heat_carrier_bus = heat_carrier_dataclass.get_bus([40])
        heat_demand_dataclass = data_classes_comp.loc["heat_demand", building_id]
        heat_demand_dataclass.value_list = data["ww_demand_"+str(building_id)]
        heat_demand_dataclass.level = 40
        heat_demand_dataclass.bus = heat_carrier_bus[40]

        heat_demand = heat_demand_dataclass.create_demand()

        dataclasses[building_id]["heat_carrier_dataclass"] = heat_carrier_dataclass
        dataclasses[building_id]["heat_demand_dataclass"] = heat_demand_dataclass

        components[building_id]["heat_demand"] = heat_demand
        components[building_id]["heat_carrier_bus"] = heat_carrier_bus


        print(building_id)
        hot_water_tank_config_building = copy.deepcopy(hot_water_tank_config)
        if data_classes_comp.loc["building", building_id] == "SFH":
            hot_water_tank_config_building.maximum_capacity = 20
        elif data_classes_comp.loc["building", building_id] == "MFH":
            hot_water_tank_config_building.maximum_capacity = 60

        hot_water_tank_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
        hot_water_tank_dataclass = HotWaterTank(
            name="heat_storage_"+str(building_id),
            investment=True,
            temperature_buses = heat_carrier_bus[40],
            max_temperature=70,
            min_temperature=40,
            input_bus=heat_carrier_bus[40],
            output_bus=heat_carrier_bus[40],
            investment_component=hot_water_tank_config_building
            )
        hot_water_tank = hot_water_tank_dataclass.create_storage()

        dataclasses[building_id]["hot_water_tank_dataclass"] = hot_water_tank_dataclass
        components[building_id]["hot_water_tank"] = hot_water_tank
        air_heat_pump_config_building =  copy.deepcopy(air_heat_pump_config)
        air_heat_pump_config_building.maximum_capacity = max_required_heating
        air_heat_pump_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
        air_heat_pump_dataclass = AirHeatPump(heat_carrier_bus= heat_carrier_dataclass.get_bus(),
                                              investment=True,
                                              name="hp_"+str(building_id),
                                              air_temperature=data["air_temperature"],
                                              investment_component=air_heat_pump_config_building)
        air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
        air_heat_pump= air_heat_pump_dataclass.create_source()
        air_heat_pump_converters= air_heat_pump_dataclass.create_converters(heat_pump_bus = air_heat_pump_bus,
                                                                         electricity_bus = electricity_carrier_bus_building,
                                                                         heat_carrier_bus=heat_carrier_dataclass.get_bus())

        dataclasses[building_id]["air_heat_pump_dataclass"] = air_heat_pump_dataclass
        components[building_id]["air_heat_pump_converters"] = air_heat_pump_converters
        components[building_id]["air_heat_pump"] = air_heat_pump
        components[building_id]["air_heat_pump_bus"] = air_heat_pump_bus

        gas_carrier_dataclass_building = GasCarrier(name="g_carrier_"+str(building_id))
        gas_carrier_bus_building = gas_carrier_dataclass_building.get_bus()
        grid_gas_into_converter_building = Converter(label="conv_g_into_grid_"+str(building_id),
                                              inputs={gas_carrier_bus_building: solph.flows.Flow()},
                                              outputs={gas_bus: solph.flows.Flow()},
                                              conversion_factors={gas_carrier_bus_building: 1/building_in_cluster})
        grid_gas_from_converter_building = Converter(label="conv_g_from_grid_"+str(building_id),
                                              inputs={gas_bus: solph.flows.Flow()},
                                              outputs={gas_carrier_bus_building: solph.flows.Flow()},
                                              conversion_factors={gas_carrier_bus_building: 1/building_in_cluster})

        gas_heater_config_building =  copy.deepcopy(gas_heater_config)
        gas_heater_config_building.maximum_capacity = max_required_heating
        gas_heater_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)

        gas_heater_dataclass = GasHeater(investment=True,
                                         name="gas_heater_"+str(building_id),
                                         investment_component=gas_heater_config_building)
        gas_heater_bus = gas_heater_dataclass.get_bus()
        gas_heater= gas_heater_dataclass.create_source()
        gas_heater_converters= gas_heater_dataclass.create_converters(gas_heater_bus = gas_heater_bus,
                                                                      gas_bus = gas_carrier_bus_building,
                                                                      heat_carrier_bus=heat_carrier_dataclass.get_bus())
        dataclasses[building_id]["gas_carrier_dataclass_building"] = gas_carrier_dataclass_building

        components[building_id]["gas_carrier_bus_building"] = gas_carrier_bus_building
        components[building_id]["grid_gas_into_converter_building"] = grid_gas_into_converter_building
        components[building_id]["grid_gas_from_converter_building"] = grid_gas_from_converter_building

        dataclasses[building_id]["gas_heater_dataclass"] = gas_heater_dataclass
        components[building_id]["gas_heater_converters"] = gas_heater_converters
        components[building_id]["gas_heater_bus"] = gas_heater_bus
        components[building_id]["gas_heater"] = gas_heater

        battery_config_building =  copy.deepcopy(battery_config)
        battery_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
        battery_dataclass = Battery(investment=True,
                                    name="battery_"+str(building_id)+str(building_id),
                                    input_bus = electricity_carrier_bus_building,
                                    output_bus = electricity_carrier_bus_building,
                                    investment_component=battery_config_building)
        battery = battery_dataclass.create_storage()

        dataclasses[building_id]["battery_dataclass"] = battery_dataclass
        components[building_id]["battery"] = battery




        building_dataclass = data_classes_comp.loc["building", building_id]
        building_dataclass.value_list = data["building_"+str(building_id)]
        building_dataclass.set_number_of_buildings_in_cluster(building_in_cluster)
        building_dataclass.bus=heat_carrier_dataclass.get_bus()

        building_component = building_dataclass.create_demand()

        dataclasses[building_id]["building_dataclass"] = building_dataclass
        components[building_id]["building_component"] = building_component
        pv_dataclass = data_classes_comp.loc["pv_system", building_id]
        pv_dataclass_config_building = copy.deepcopy(pv_system_config)
        pv_dataclass_config_building.set_reference_unit_quantity(reference_unit_quantity=building_in_cluster)
        pv_dataclass.investment_component=pv_dataclass_config_building

        pv_dataclass.value_list = data["pv_system_" + str(building_id)]

        pv_dataclass.update_maximum_investment_pv_capacity_based_on_area(area = building_dataclass.get_roof_area_for_pv())
        pv_system = pv_dataclass.create_source(output_bus = electricity_carrier_bus_building)

        dataclasses[building_id]["pv_dataclass"] = pv_dataclass
        components[building_id]["pv_system"] = pv_system

    for building_id, building_data in components.items():
        # Ensure we're processing the components for the current building
        for oemof_comp, comp_value in building_data.items():
            # Check if the component is a list (which it should not be, based on the structure)
            if isinstance(comp_value, list):
                for item in comp_value:
                    es.add(item)  # Process each component in the list
            # Check if the component is a dictionary, meaning it has nested components
            elif isinstance(comp_value, dict):
                # If it's a dictionary, iterate over its key-value pairs
                for key, value in comp_value.items():
                    es.add(value)
            else:
                # Otherwise, just add the component directly
                es.add(comp_value)

    model = solph.Model(es)

    if True:
        # Create the graph from the energy system (es)
        graph = create_nx_graph(es)
        # Draw the graph
        plt.figure(figsize=(18, 14))  # Set figure size
        nx.draw(graph, with_labels=True, font_size=6)
        plt.show()
    if co2_new is None:
        model = solph.constraints.additional_total_limit(model, "co2", limit=1500)
    else:
        model = solph.constraints.additional_total_limit(model, "co2", limit=co2_new)
    # Show the graph
    # Show the graph
        print("__________")
        print("start for:")
        print("boundary co2:"+str(co2_new))
        print("boundary peak:" + str(peak_new))
    try:


        model.solve(solver=solver, solve_kwargs={"tee": True},
                                              cmdline_options={"mipgap": 0.01}
        )
        meta_results = solph.processing.meta_results(model)
        results = solph.processing.results(model)
        final_results = {}
        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink
                                                )
        final_results[gas_grid_dataclass.name] = gas_grid_dataclass.post_process(results,gas_grid_source,None)

        if False:
            final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)

        for building_id, building_data in components.items():
            final_results[building_id] = {}
            final_results[building_id][dataclasses[building_id]["pv_dataclass"].name] = dataclasses[building_id]["pv_dataclass"].post_process(results,components[building_id]["pv_system"])

            final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass"].name] = dataclasses[building_id]["hot_water_tank_dataclass"].post_process(results,components[building_id]["hot_water_tank"])

            final_results[building_id][dataclasses[building_id]["battery_dataclass"].name] = dataclasses[building_id]["battery_dataclass"].post_process(results,components[building_id]["battery"])

            final_results[building_id][dataclasses[building_id]["gas_heater_dataclass"].name] = dataclasses[building_id]["gas_heater_dataclass"].post_process(results,
                                                                                                                                                              components[building_id]["gas_heater"],
                                                                                                                                                              components[building_id]["gas_heater_converters"],
                                                                                                                                                              components[building_id]["heat_carrier_bus"],
                                                                                                                                                              components[building_id]["gas_carrier_bus_building"])

            final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass"].name] = dataclasses[building_id]["air_heat_pump_dataclass"].post_process(results,
                                                                                                                                                                    components[building_id]["air_heat_pump"],
                                                                                                                                                                    components[building_id]["air_heat_pump_converters"],
                                                                                                                                                                    components[building_id]["heat_carrier_bus"],
                                                                                                                                                                    components[building_id]["electricity_carrier_bus_building"])

            final_results[building_id][dataclasses[building_id]["building_dataclass"].name] = dataclasses[building_id]["building_dataclass"].post_process(results,components[building_id]["building_component"])

            final_results[building_id][dataclasses[building_id]["electricity_demand_dataclass_building"].name] = dataclasses[building_id]["electricity_demand_dataclass_building"].post_process(results,components[building_id]["electricity_demand"])

            final_results[building_id][dataclasses[building_id]["heat_demand_dataclass"].name] = dataclasses[building_id]["heat_demand_dataclass"].post_process(results,components[building_id]["heat_demand"])

        co2_investment = 0
        for building_id in components:
            # For each component, sum up the CO2 contributions to the overall system
            co2_investment += final_results[building_id][dataclasses[building_id]["battery_dataclass"].name]["investment_co2"]
            co2_investment += final_results[building_id][dataclasses[building_id]["hot_water_tank_dataclass"].name]["investment_co2"]
            co2_investment += final_results[building_id][dataclasses[building_id]["gas_heater_dataclass"].name]["investment_co2"]
            co2_investment += final_results[building_id][dataclasses[building_id]["air_heat_pump_dataclass"].name]["investment_co2"]
            co2_investment += final_results[building_id][dataclasses[building_id]["pv_dataclass"].name]["investment_co2"]

            co2_investment += final_results[building_id][dataclasses[building_id]["building_dataclass"].name]["investment_co2"
                                ]
        co2_operation = final_results[electricity_grid_dataclass.name]["flow_from_grid_co2"
                                ]-final_results[electricity_grid_dataclass.name]["flow_into_grid_co2"
                                ]+final_results[gas_grid_dataclass.name]["flow_from_grid_co2"
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

        return final_results, co2_oemof_model
    except Exception as e:
        print(e)
        return None, None


def process_cluster(cluster_df, building_type, epw_path, directory_path, data, refurbish, number_of_time_steps,data_classes_comp,ev):
    for index, row in cluster_df.iterrows():
        if index >=2:
            continue
        building_id = row['building_id']
        tabula_year_class = row['tabula_year_class']
        building_floor_area = row['net_floor_area']
        number_of_occupants = row['number_of_residents']
        number_of_households = row['number_of_apartments']
        number_of_buildings_in_cluster = row['buildings_in_cluster']

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

        electricity_cols = [col for col in demand.columns if col.startswith("Electricity_")]
        demand_electricity = (demand[electricity_cols].sum(axis=1) * 1000).tolist()

        warm_water_cols = [col for col in demand.columns if col.startswith("Warm Water_")]
        demand_warm_water = demand[warm_water_cols].sum(axis=1)

        # Datenklassen
        electricity_demand = ElectricityDemand(name=f"e_demand_{building_id}", value_list=demand_electricity)
        heat_demand = WarmWater(name=f"ww_demand_{building_id}", value_list=demand_warm_water, level=40)

        building = ThermalBuilding(
            name=f"building_{building_id}",
            floor_area=building_floor_area,
            number_of_occupants=number_of_occupants,
            number_of_household=number_of_households,
            country="DE",
            construction_year=year_of_construction,
            class_building="average",
            building_type=building_type,
            refurbishment_status=refurbish,
            heat_level_calculation=True,
            number_of_time_steps=number_of_time_steps,
        )

        # PV-Ertrag pro Watt
        pv_yield_per_wp = simulate_pv_yield(
            pv_nominal_power_in_watt=1,
            tilt=row['avg_roof_pitch_angle'],
            epw_path=epw_path
        )

        pv = PVSystem(
            investment=True,
            name=f"pv_system_{building_id}",
            value_list=pv_yield_per_wp.tolist(),
        )
        pv.update_maximum_investment_pv_capacity_based_on_area(building.get_roof_area_for_pv())

        # Spalten hinzufügen
        data[electricity_demand.name] = electricity_demand.value_list
        data[heat_demand.name] = heat_demand.value_list
        data[building.name] = building.value_list
        data[pv.name] = pv.value_list
        data_classes_comp[building_id] = {"electricity_demand":electricity_demand,
                                          "pv_system":pv,
                                          "building":building,
                                          "heat_demand":heat_demand}
    return data, data_classes_comp



def run_main(refurbish):
    base_path = os.path.dirname(os.path.abspath(__file__))
    ueu = "processed_bds_in_DENI03403000SEC5658"
    directory_path =os.path.join(base_path, ueu)
    number_of_time_steps = 8760
    sfh_cluster_path = os.path.join(base_path, ueu, 'sfh_cluster.pkl')
    with open(sfh_cluster_path, 'rb') as f:
        sfh_cluster = pickle.load(f)
    if False:
        mfh_cluster_path = os.path.join(base_path, ueu, 'mfh_cluster.pkl')
        with open(mfh_cluster_path, 'rb') as f:
            mfh_cluster = pickle.load(f)
    combined_cluster = pd.concat([sfh_cluster])
    results_loop_to_save = {}
    ev = "EV"
    buildings_connected="con" #or uncon
    if True:
        print(refurbish)

        main_path = get_project_root()

        data = pd.DataFrame()
        data_classes_comp = pd.DataFrame()
        epw_path = os.path.join(
                main_path,
                "thermal_building_model",
                "input",
                "weather_files",
                "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
            )

        data,data_classes_comp = process_cluster(
            cluster_df=sfh_cluster,
            building_type="SFH",
            epw_path=epw_path,
            directory_path=directory_path,
            data=data,
            refurbish=refurbish,
            number_of_time_steps=number_of_time_steps,
            data_classes_comp = data_classes_comp,
            ev=ev
        )

        if False:
            data,data_classes_comp = process_cluster(
                cluster_df=mfh_cluster,
                building_type="MFH",
                epw_path=epw_path,
                directory_path=directory_path,
                data=data,
                refurbish=refurbish,
                number_of_time_steps=number_of_time_steps,
                data_classes_comp = data_classes_comp,
                ev =ev
            )
        main_path = get_project_root()
        location = calculate_gain_by_sun.Location(
            epwfile_path=os.path.join(
                main_path,
                "thermal_building_model",
                "input",
                "weather_files",
                "03_HH_Hamburg-Fuhlsbuttel_TRY2035.csv",
            ),
        )
        data["air_temperature"] = location.weather_data["drybulb_C"].to_list()
        date_time_index = solph.create_time_index(2025, number=number_of_time_steps - 1)
        data.index = date_time_index

        typical_periods = 25
        hours_per_period = 24

        aggregation1 = tsam.TimeSeriesAggregation(
            timeSeries=data.iloc[:8760],
            noTypicalPeriods=typical_periods,
            hoursPerPeriod=hours_per_period,
            clusterMethod="k_means",

        )
        aggregation1.createTypicalPeriods()
        data = aggregation1.typicalPeriods
        t1_agg = pd.date_range(
            "2025-01-01", periods=typical_periods * hours_per_period, freq="H"
        )


        final_results_ref, co2_ref = run_model(None, None,refurbish,data,aggregation1,t1_agg,data_classes_comp,buildings_connected,combined_cluster)
        co2_reduction_factor_ref = 1
        peak_reduction_factor_ref = 1
        results_loop_to_save[(co2_reduction_factor_ref, peak_reduction_factor_ref,refurbish)] = {
            "results": final_results_ref,
            "co2": co2_ref,
            "peak_reduction_factor" : peak_reduction_factor_ref,
            "refurbish": refurbish,
            "totex": final_results_ref["totex"],
            "peak": final_results_ref["Electricity"]["peak_from_grid"]

        }
        co2_reference = co2_ref
        peak_reference = final_results_ref["Electricity"]["peak_from_grid"]
        co2_reduction_factors = [0.9,0.8,0.7,0.6,0.5,0.4,0.3,0.2,0.1] # [0.95,0.9,0.85,0.8,0.75,0.7,0.65,0.6,0.5]
        peak_reduction_factors = [1,0.9,0.8,0.7,0.6,0.5,0.4]
        peak_calculation_worked = True
        co2_calculation_worked = True
        for co2_reduction_factor in co2_reduction_factors:
            if peak_calculation_worked == False and co2_calculation_worked == False:
                break
            if co2_reference > 0:
                co2_new = co2_reference * co2_reduction_factor
            else:
                co2_new = co2_reference * (1+1-co2_reduction_factor)
            for peak_reduction_factor in peak_reduction_factors:
                peak_calculation_worked=True
                print("refurbish:"+ str(refurbish))
                print("co2: "+str(co2_reduction_factor))
                print("peak: " + str(peak_reduction_factor))
                peak_new = peak_reference * peak_reduction_factor


                final_results, co2  = run_model(co2_new,peak_new,refurbish,data,aggregation1,t1_agg,data_classes_comp,buildings_connected,combined_cluster)
                if final_results is None:
                    results_loop_to_save[(co2_reduction_factor, peak_reduction_factor, refurbish)] = {
                        "results": None,
                        "co2": None,
                        "peak_reduction_factor": None,
                        "refurbish": None,
                        "totex": None,
                        "peak": None
                    }
                    if peak_calculation_worked:
                        peak_calculation_worked = False
                        break
                    else:
                        co2_calculation_worked = False
                        break
                else:
                    peak_calculation_worked = True
                    totex = final_results["totex"]
                    peak = final_results["Electricity"]["peak_from_grid"]


                    results_loop_to_save[(co2_reduction_factor, peak_reduction_factor,refurbish)] = {
                        "results": final_results,
                        "co2": co2,
                        "peak_reduction_factor": peak_reduction_factor,
                        "refurbish": refurbish,
                        "totex": totex,
                        "peak": peak
                    }

            file_path="results_"+str(ueu)+"_"+str(refurbish)+"_"+str(ev)+"_"+str(ev)+"_"+str(buildings_connected)+".pkl"
            if os.path.exists(file_path):
                # If the file exists, open it and load the data
                with open(file_path, "rb") as f:
                    existing_results = pickle.load(f)
                print(f"Loaded existing results for {file_path}")

                # Now you can add more data to existing_results
                existing_results.update(results_loop_to_save)  # Example of adding new data

            else:
                # If the file doesn't exist, create it and save the results
                existing_results = results_loop_to_save
                print(f"New results created for {file_path}")

            # Save the updated or new results back to the pickle file
            with open(file_path, "wb") as f:
                pickle.dump(existing_results, f)
    file_path = "results_" + str(ueu) + "_" + str(refurbish) + "_" + str(ev) + "_" + str(ev) + "_" + str(
        buildings_connected) + ".pkl"
    if os.path.exists(file_path):
        # If the file exists, open it and load the data
        with open(file_path, "rb") as f:
            existing_results = pickle.load(f)
        print(f"Loaded existing results for {file_path}")

        # Now you can add more data to existing_results
        existing_results.update(results_loop_to_save)  # Example of adding new data

    else:
        # If the file doesn't exist, create it and save the results
        existing_results = results_loop_to_save
        print(f"New results created for {file_path}")

    # Save the updated or new results back to the pickle file
    with open(file_path, "wb") as f:
        pickle.dump(existing_results, f)

if __name__ == "__main__":
    refurbish =["no_refurbishment","usual_refurbishment","advanced_refurbishment"]  # Beispiel #"GEG_standard"
    import multiprocessing
    import os
    # Multiprocessing-Pool erstellen
    run_main("no_refurbishment")
    if False:
        with multiprocessing.Pool(processes=multiprocessing.cpu_count()) as pool:
            pool.map(run_main, refurbish)