
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, HeatGrid, GasGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier, \
    GasCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, WarmWater
from oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
from oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank
from oemof.thermal_building_model.oemof_facades.technologies.converter import AirHeatPump, GasHeater
from oemof.thermal_building_model.oemof_facades.refurbishment.building_model import ThermalBuilding
from oemof import solph
import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
import os
import pickle
from oemof.thermal_building_model.tabula.tabula_reader import Building
import pprint as pp
#  create solver
def main(co2_new,peak_new,refurbish,building_id, floor_area):
    solver = "gurobi"  # 'glpk', 'gurobi',....
    number_of_time_steps = 8760


    date_time_index = solph.create_time_index(
        2012, number=number_of_time_steps)
    es = solph.EnergySystem(timeindex=date_time_index,
                            infer_last_interval=False)

    if peak_new is None:
        electricity_grid_dataclass = ElectricityGrid()
    else:
        electricity_grid_dataclass = ElectricityGrid(max_peak_into_grid=peak_new,
                                                     max_peak_from_grid=peak_new)


    electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
    electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()
    electricity_grid_sink = electricity_grid_dataclass.create_sink()
    electricity_grid_source = electricity_grid_dataclass.create_source()
    electricity_carrier_dataclass = ElectricityCarrier()
    electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
    connect_buses(input=electricity_grid_bus_from_grid, target=electricity_carrier_bus, output=electricity_grid_bus_into_grid)
    electricity_demand_dataclass = ElectricityDemand(building_id = building_id,
                                                    bus=electricity_carrier_bus)
    electricity_demand = electricity_demand_dataclass.create_demand()

    electricity  = [electricity_grid_bus_from_grid,
                    electricity_grid_bus_into_grid,
                    electricity_grid_sink,
                    electricity_grid_source,
                    electricity_carrier_bus,
                    electricity_demand]


    heat_grid_temperature_levels = [40]
    heat_grid_dataclass = HeatGrid(investment=True)

    heat_grid_source = heat_grid_dataclass.create_source()
    heat_grid_bus_from_grid = heat_grid_dataclass.get_bus_from_grid()

    heat_carrier_temperature_levels = [40]
    heat_carrier_dataclass = HeatCarrier(levels = heat_carrier_temperature_levels)

    heat_carrier_bus = heat_carrier_dataclass.get_bus([40])
    connect_buses(
        input=heat_grid_bus_from_grid,
        target=heat_carrier_bus)

    heat_demand_dataclass = WarmWater(name="WarmWater",
                                       level = 40,
                                       bus=heat_carrier_bus[40],
                                        building_id=building_id)
    heat_demand = heat_demand_dataclass.create_demand()

    hot_water_tank_dataclass = HotWaterTank(
        investment=True,
        temperature_buses = heat_carrier_bus[40],
        max_temperature=70,
        min_temperature=40,
        input_bus=heat_carrier_bus[40],
        output_bus=heat_carrier_bus[40]
        )


    hot_water_tank = hot_water_tank_dataclass.create_storage()
    es.add(hot_water_tank)

    air_heat_pump_dataclass = AirHeatPump(heat_carrier_bus= heat_carrier_dataclass.get_bus(),
                                          investment=True)
    air_heat_pump_bus = air_heat_pump_dataclass.get_bus()
    air_heat_pump= air_heat_pump_dataclass.create_source()
    air_heat_pump_converters= air_heat_pump_dataclass.create_converters(heat_pump_bus = air_heat_pump_bus,
                                                                     electricity_bus = electricity_carrier_bus,
                                                                     heat_carrier_bus=heat_carrier_dataclass.get_bus())
    es.add(air_heat_pump_bus,air_heat_pump,*air_heat_pump_converters)

    gas_grid_dataclass = GasGrid()
    gas_grid_bus_from_grid = gas_grid_dataclass.get_bus_from_grid()
    gas_grid_source = gas_grid_dataclass.create_source()

    gas_carrier_dataclass = GasCarrier()
    gas_bus = gas_carrier_dataclass.get_bus()
    connect_buses(input=gas_grid_bus_from_grid, target=gas_bus)

    gas_heater_dataclass = GasHeater(investment=True)
    gas_heater_bus = gas_heater_dataclass.get_bus()
    gas_heater= gas_heater_dataclass.create_source()
    gas_heater_converters= gas_heater_dataclass.create_converters(gas_heater_bus = gas_heater_bus,
                                                                  gas_bus = gas_bus,
                                                                  heat_carrier_bus=heat_carrier_dataclass.get_bus())


    es.add(gas_grid_bus_from_grid,
            gas_bus,
           gas_grid_source,
            gas_heater_bus,
            gas_heater,
            *gas_heater_converters)

    battery_dataclass = Battery(investment=True,
                                input_bus = electricity_carrier_bus,
                                output_bus = electricity_carrier_bus,
                                maximum_capacity = 15000)
    battery = battery_dataclass.create_storage()
    es.add(battery)
    pv_dataclass = PVSystem(investment=True)
    pv_system = pv_dataclass.create_source(output_bus = electricity_carrier_bus,

                             )
    es.add(pv_system)



    building_dataclass = ThermalBuilding(name=building_id,
                                         floor_area = floor_area,
                                          country="DE",
                                          construction_year=1980,
                                          class_building="average",
                                          building_type="SFH",
                                          refurbishment_status=refurbish,
                                          heat_level_calculation = True,
                                          number_of_time_steps=number_of_time_steps,
                                          bus=heat_carrier_dataclass.get_bus()
                                          )
    building_component = building_dataclass.create_demand()
    es.add(building_component)
    heat = []
    heat = [
        #heat_grid_sink,
            heat_grid_source,
            heat_grid_bus_from_grid,
           # heat_grid_bus_into_grid,
            heat_carrier_bus,
            heat_demand]


    electricity_components = flatten_components_list(electricity)
    heat_components = flatten_components_list(heat)
    # Add all components to the energy system in one go
    # Add all components to the energy system in one go
    es.add(*(heat_components))
    es.add(*(electricity_components))
    model = solph.Model(es)

    if False:
        # Create the graph from the energy system (es)
        graph = create_nx_graph(es)
        # Draw the graph
        plt.figure(figsize=(10, 6))  # Set figure size
        nx.draw(graph, with_labels=True, font_size=8)
        plt.show()
    if co2_new is None:
        model = solph.constraints.additional_total_limit(model, "co2", limit=10000000)
    else:
        model = solph.constraints.additional_total_limit(model, "co2", limit=co2_new)
    # Show the graph
    # Show the graph

    try:
        print("__________")
        print("start for:")
        print("boundary co2:"+str(co2_new))
        print("boundary peak:" + str(peak_new))

        model.solve(solver=solver, solve_kwargs={"tee": True})
        meta_results = solph.processing.meta_results(model)
        results = solph.processing.results(model)
        final_results = {}
        final_results[hot_water_tank_dataclass.name] = hot_water_tank_dataclass.post_process(results,hot_water_tank)

        final_results[battery_dataclass.name] = battery_dataclass.post_process(results,battery)

        final_results[electricity_grid_dataclass.name] = electricity_grid_dataclass.post_process(results,electricity_grid_source,electricity_grid_sink
                                                )
        final_results[gas_grid_dataclass.name] = gas_grid_dataclass.post_process(results,gas_grid_source,None
                                                )
        final_results[heat_grid_dataclass.name] = heat_grid_dataclass.post_process(results,heat_grid_source,None)

        final_results[gas_heater_dataclass.name] = gas_heater_dataclass.post_process(results,gas_heater,gas_heater_converters)

        final_results[air_heat_pump_dataclass.name] = air_heat_pump_dataclass.post_process(results,air_heat_pump,air_heat_pump_converters)

        final_results[pv_dataclass.name] = pv_dataclass.post_process(results,pv_system)

        final_results[building_dataclass.name] = building_dataclass.post_process(results,building_component)

        final_results[electricity_demand_dataclass.name] = electricity_demand_dataclass.post_process()

        final_results[heat_demand_dataclass.name] = heat_demand_dataclass.post_process()


        final_results["co2_post_process"] = (final_results[battery_dataclass.name]["investment_co2"
                                ]+final_results[hot_water_tank_dataclass.name]["investment_co2"
                                ]+final_results[gas_heater_dataclass.name]["investment_co2"
                                ]+final_results[air_heat_pump_dataclass.name]["investment_co2"
                                ]+final_results[pv_dataclass.name]["investment_co2"
                                ]+sum(final_results[building_dataclass.name]["investment_co2"
                                ].values())
                                +final_results[heat_grid_dataclass.name]["investment_co2"
                                ]+final_results[heat_grid_dataclass.name]["flow_from_grid_co2"
                                ]+final_results[electricity_grid_dataclass.name]["flow_from_grid_co2"
                                ]-final_results[electricity_grid_dataclass.name]["flow_into_grid_co2"
                                ]+final_results[gas_grid_dataclass.name]["flow_from_grid_co2"
                                ])
        co2 = model.total_limit_co2()

        print("co2_constraint: ", co2)
        print("co2_manuel: ", final_results["co2_post_process"])
        print("objective",str(meta_results["objective"]))
        final_results["co2_oemof_model"] = co2
        final_results["totex"] = meta_results["objective"]

        return final_results, co2
    except:
        return None, None


building_ids = [
    #"DENILD1100004vsl",
                #"DENILD1100004uSx",
                #"DENILD1100004u2T",
                #"DENILD1100004smj",
                "DENILD1100004sZd",
                "DENILD1100004rW0",
                #"representativeSFH"
]
floor_areas = [
    #375,
               #212,
    #366,
    #393,
    363,
    249,

    #326
]
if False:
    building_ids = ["DENILD1100004vsl",
                    "DENILD1100004uSx",
                    "DENILD1100004u2T",
                    "DENILD1100004sZd",
                    "DENILD1100004smj",
                    "DENILD1100004rW0",
                    "representativeSFH"]
building_floor_area_dict = dict(zip(building_ids, floor_areas))

for building_id, floor_area in building_floor_area_dict.items():

    refurbishment =["no_refurbishment","usual_refurbishment","advanced_refurbishment","GEG_standard"] # ,"no_refurbishment","usual_refurbishment""advanced_refurbishment","GEG_standard"
    results_loop_to_save = {}
    for refurbish in refurbishment:
        final_results_ref, co2_ref = main(None, None,refurbish,building_id, floor_area)
        co2_reduction_factor_ref = 1
        peak_reduction_factor_ref = 1
        results_loop_to_save[(co2_reduction_factor_ref, peak_reduction_factor_ref,refurbish)] = {
            "results": final_results_ref,
            "co2": co2_ref,
            "peak_reduction_factor" : peak_reduction_factor_ref,
            "refurbish": refurbish,
            "totex": final_results_ref["totex"],
            "peak": max(final_results_ref["Electricity"]["peak_into_grid"],final_results_ref["Electricity"]["peak_from_grid"])

        }
        co2_reference = co2_ref
        peak_reference = max(final_results_ref["Electricity"]["peak_into_grid"],final_results_ref["Electricity"]["peak_from_grid"])
        co2_reduction_factors = [0.8,0.6,0.4,0.2] # [0.8,0.6,0.4,0.2]
        peak_reduction_factors = [1,0.8,0.6,0.4,0.2]

        for co2_reduction_factor in co2_reduction_factors:
            co2_new = co2_reference * co2_reduction_factor
            for peak_reduction_factor in peak_reduction_factors:
                print("new opt for: "+str(building_id))
                print("co2: "+str(co2_reduction_factor))
                print("peak: " + str(peak_reduction_factor))
                peak_new = peak_reference * peak_reduction_factor
                try:
                    final_results, co2  = main(co2_new,peak_new,refurbish,building_id, floor_area)
                    totex = final_results["totex"]
                    peak = max(final_results_ref["Electricity"]["peak_into_grid"],
                        final_results_ref["Electricity"]["peak_from_grid"])
                except:
                    final_results = None
                    co2 = None
                    totex = None
                    peak = None

                results_loop_to_save[(co2_reduction_factor, peak_reduction_factor,refurbish)] = {
                    "results": final_results,
                    "co2": co2,
                    "peak_reduction_factor": peak_reduction_factor,
                    "refurbish": refurbish,
                    "totex": totex,
                    "peak": peak
                }
                if final_results is None:
                    continue
        file_path="results_"+str(building_id)+"_"+str(refurbish)+"_.pkl"
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
    # Save the updated or new results back to the pickle file
    if results_loop_to_save is not None:
        with open("results_"+str(building_id)+"_.pkl", "wb") as f:
            pickle.dump(results_loop_to_save, f)