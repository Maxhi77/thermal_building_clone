import os
import pprint as pp
import logging
from matplotlib import pyplot as plt
import pandas as pd

from thermal_building_model.helpers.path_helper import get_project_root
from thermal_building_model.helpers import calculate_gain_by_sun
from thermal_building_model.tabula.tabula_reader import Building
from thermal_building_model.m_5RC import M5RC
from thermal_building_model.helpers.building_heat_demand_simulation import HeatDemand_Simulation_5RC
import oemof.solph as solph
from oemof.solph import views
from oemof.tools import logger
from thermal_building_model.helpers.post_processing import calc_excess_temperature_degree_hours
"""
General description
-------------------
This examples optimizes the internal building temperature.
It is suppose to show how to use the building component M5RC.
For the generation of a M5RC the tabula building data set is used.
In the end it compares the heat demand calculated by oemof and the tabula data sheet.


Installation requirements
-------------------------
This example requires the version v0.5.x of oemof.solph. Install by:

    pip install 'oemof.solph>=0.5,<0.6'

"""

__copyright__ = "oemof developer group"
__license__ = "MIT"


def main():
    #  create solver
    solver = "cbc"  # 'glpk', 'gurobi',....
    number_of_time_steps = 8760
    main_path = get_project_root()
    pv_data = pd.read_csv(
        os.path.join(
            main_path,
            "thermal_building_model",
            "input",
            "sfh_example",
            "pvwatts_hourly_1kW.csv",
        )
    )
    # Generates 5RC Building-Model
    building_example = Building(
        country="DE",
        construction_year=1980,
        class_building="average",
        building_type="SFH",
        refurbishment_status="no_refurbishment",
        number_of_time_steps=number_of_time_steps,
    )
    building_example.calculate_all_parameters()

    # Pre-Calculation of solar gains with weather_data and building_data
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
    solar_gains = building_example.calc_solar_gaings_through_windows(
        object_location_of_building=location,
        t_outside = t_outside
    )


    # Internal gains of residents, machines (f.e. fridge, computer,...) and lights have to be added manually
    internal_gains = []
    t_set_heating = []
    t_set_cooling = []
    for _ in range(number_of_time_steps + 1):
        internal_gains.append(3446 * 1000 /8760)
        t_set_heating.append(20)
        t_set_cooling.append(40)

    # initiate the logger (see the API docs for more information)
    logger.define_logging(
        logfile="oemof_example.log",
        screen_level=logging.INFO,
        file_level=logging.INFO,
    )

    logging.info("Initialize the energy system")
    date_time_index = solph.create_time_index(
        2012, number=number_of_time_steps)
    es = solph.EnergySystem(timeindex=date_time_index,
                            infer_last_interval=False)

    # create electricity, heat and cooling flow
    b_heat = solph.buses.Bus(label="b_heat")
    es.add(b_heat)
    b_cool = solph.buses.Bus(label="b_cool")
    es.add(b_cool)
    b_elect = solph.buses.Bus(label="electricity_from_grid")
    es.add(b_elect)

    es.add(
        solph.components.Source(
            label="elect_from_grid",
            outputs={b_elect: solph.flows.Flow(variable_costs=30)},
        )
    )

    es.add(
        solph.components.Sink(
            label="elect_into_grid",
            inputs={b_elect: solph.flows.Flow(variable_costs=10)},
        )
    )

    es.add(
        solph.components.Transformer(
            label="ElectricalHeater",
            inputs={b_elect: solph.flows.Flow()},
            outputs={b_heat: solph.flows.Flow(nominal_value=20000)},
            conversion_factors={b_elect: 1},
        )
    )
    es.add(
        solph.components.Transformer(
            label="ElectricalCooler",
            inputs={
                b_cool: solph.flows.Flow(nominal_value=20000),
                b_elect: solph.flows.Flow(),
            },
            outputs={},
            conversion_factors={b_cool: 0.9, b_elect: 1},
        )
    )

    es.add(solph.components.Source(
        label="pv",
        outputs={
            b_elect: solph.Flow(
                fix=pv_data["AC System Output (W)"],
                nominal_value= 10
                ),}
            ))
    heating_demand, cooling_demand, t_air = HeatDemand_Simulation_5RC(
            label="GenericBuilding",
            solar_gains=solar_gains,
            t_outside=t_outside,
            internal_gains=internal_gains,
            t_set_heating=t_set_heating,
            t_set_cooling=t_set_cooling,
            t_set_heating_max = 24,
            building_config=building_example.building_config,
            t_inital=20,
            max_power_heating = 20000,
            max_power_cooling = 20000,
            timesteps = 8760).solve()

    es.add(solph.components.Source(
        label="cooling_demand",
        outputs={
            b_cool: solph.Flow(
                fix=cooling_demand,
                nominal_value=1
            ), }
    ))
    es.add(solph.components.Sink(
        label="heating_demand",
        inputs={
            b_heat: solph.Flow(
                fix=heating_demand,
                nominal_value=1
            ), }
    ))
    ##########################################################################
    # Optimise the energy system and plot the results
    ##########################################################################

    logging.info("Optimise the energy system")

    # initialise the operational model
    model = solph.Model(es)

    # if tee_switch is true solver messages will be displayed
    logging.info("Solve the optimization problem")
    model.solve(solver=solver)

    logging.info("Store the energy system with the results.")

    floor_area = building_example.floor_area
    relative_heating_demand = sum(heating_demand) / floor_area


    # add results to the energy system to make it possible to store them.
    es.results["main"] = solph.processing.results(model)
    es.results["meta"] = solph.processing.meta_results(model)
    results = es.results["main"]
    custom_building = views.node(results, "GenericBuilding")
    print("annual heating demand in kWh/m^2: " + str(relative_heating_demand / 1000))

    # Plot `t_air`
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(t_air, drawstyle="steps-post")
    ax.set_ylabel("t_air in Celsius")
    ax.set_title("Temperature over time")
    plt.show()

    # Plot `heating_demand`
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(heating_demand, drawstyle="steps-post")
    ax.set_ylabel("Heating demand in Watt")
    ax.set_title("Heating demand over time")
    plt.show()

    # Plot `cooling_demand`
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(cooling_demand, drawstyle="steps-post")
    ax.set_ylabel("Cooling demand in Watt")
    ax.set_title("Cooling demand over time")
    plt.show()

    # print the solver results
    print("********* Meta results *********")
    pp.pprint(es.results["meta"])
    print("")

if __name__ == "__main__":
    main()
