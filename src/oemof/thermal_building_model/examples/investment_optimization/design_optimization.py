import os
import pprint as pp
import logging

import pandas as pd
import pickle

from thermal_building_model.tabula.tabula_reader import Building
from thermal_building_model.helpers.path_helper import get_project_root
from thermal_building_model.helpers import calculate_gain_by_sun

import oemof.solph as solph
from oemof.solph import views
from oemof.tools import logger
from oemof.tools import economics
from thermal_building_model.m_5RC import M5RC
from plot_results import plot_stacked_bars
from oemof.solph import constraints
"""
General description
-------------------
This examples optimizes the internal building temperature.
It is suppose to show how to use the component GenericBuilding.
For the generation of a GenericBuilding the tabula building data set is used.
In the end it compares the heat demand calculated by oemof and the tabula data sheet.


Installation requirements
-------------------------
This example requires the version v0.5.x of oemof.solph. Install by:

    pip install 'oemof.solph>=0.5,<0.6'

"""

__copyright__ = "oemof developer group"
__license__ = "MIT"


def main(refurbishment_status, cost_refurbishment):
    #  create solver
    solver = "gurobi"  # 'glpk', 'gurobi',....
    number_of_time_steps = 8760
    main_path = get_project_root()

    # Generates 5RC Building-Model
    building_example = Building(
        country="DE",
        construction_year=1980,
        floor_area=200,
        class_building="average",
        building_type="SFH",
        refurbishment_status=refurbishment_status,
        number_of_time_steps=number_of_time_steps,
    )
    building_example.calculate_all_parameters()
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
        t_outside=t_outside
    )

    # Pre-Calculation of solar gains with weather_data and building_data

    # Load PV generation profile and weather
    pv_data = pd.read_csv(
        os.path.join(
            main_path,
            "thermal_building_model",
            "input",
            "sfh_example",
            "pvwatts_hourly_1kW.csv",
        )
    )
    # Elect Demand
    df_elect = pd.read_csv(
        os.path.join(
            main_path,
            "thermal_building_model",
            "input",
            "sfh_example",
            "SumProfiles.Electricity.csv",
        ),
        delimiter=";",
    )
    elect_demand_df = (
        df_elect.groupby(df_elect.index // 60)["Sum [kWh]"]
        .sum()
        .to_frame(name="Hourly_Sum")
    )
    elect_demand_in_watt = elect_demand_df * 1000

    # Warm Water Demand
    input_file_path_ww = pd.read_csv(
        os.path.join(
            main_path,
            "thermal_building_model",
            "input",
            "sfh_example",
            "SumProfiles.Warm Water.csv",
        )
    )
    df_warm_water = pd.read_csv(
        os.path.join(
            main_path,
            "thermal_building_model",
            "input",
            "sfh_example",
            "SumProfiles.Warm Water.csv",
        ),
        delimiter=";",
    )
    warm_water_demand_df = (
        df_warm_water.groupby(df_warm_water.index // 60)["Sum [L]"]
        .sum()
        .to_frame(name="Hourly_Sum")
    )
    heat_capacity_water = 4.18  # [kJ/(kg/K)
    warm_water_demand_in_watt = (
        (35 - 10) * heat_capacity_water * warm_water_demand_df * (1000 / 3600)
    )

    # Internal gains of residents, machines (f.e. fridge, computer,...) and lights have to be added manually
    internal_gains = []
    for _ in range(number_of_time_steps):
        internal_gains.append(0)

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
    # Prices are in Euro per Watt
    storage_volumen_in_Wh_per_kg = 4.18 * 1000 / 3600 * (50 - 30)  # [Wh/kg]
    qubick_meter_water_in_kg = 992.2  # [kg/m^3]
    lifetime_heat_pump = 20
    lifetime_gas_heater = 20
    lifetime_heat_storage = 25
    lifetime_pv_system = 25
    epc_heat_pump = economics.annuity(
        capex=(600 + 600 * 0.02 * lifetime_heat_pump) / 1000,
        n=lifetime_heat_pump,
        wacc=0.03,
    )
    epc_gas_heater = economics.annuity(
        capex=(100 + 100 * 0.015 * lifetime_gas_heater) / 1000,
        n=lifetime_gas_heater,
        wacc=0.03,
    )
    epc_heat_storage = economics.annuity(
        capex=(1200 / qubick_meter_water_in_kg) / storage_volumen_in_Wh_per_kg,
        n=lifetime_heat_storage,
        wacc=0.03,
    )
    epc_pv_system = economics.annuity(
        capex=(800 + 800 * 0.02 * lifetime_pv_system) / 1000,
        n=lifetime_pv_system,
        wacc=0.03,
    )

    off_set_heat_pump = 1000
    off_set_gas_heater = 0
    off_set_heat_storage = 0
    off_set_pv_system = 0
    price_gas = 0.1225 / 1000
    price_electricity = 0.35 / 1000
    price_feed_in = 0.086 / 1000

    # create heat and cooling flow
    b_heat = solph.buses.Bus(label="b_heat")
    es.add(b_heat)
    b_cool = solph.buses.Bus(label="b_cool")
    es.add(b_cool)
    b_elect = solph.buses.Bus(label="electricity")
    es.add(b_elect)
    b_gas = solph.buses.Bus(label="b_gas")
    es.add(b_gas)

    # create source object representing the gas commodity
    gas_resource = solph.components.Source(
        label="gas_resource", outputs={b_gas: solph.Flow(variable_costs=price_gas)}
    )
    # create source object representing the electricity co commodity
    elect_from_grid = solph.components.Source(
        label="elect_from_grid",
        outputs={b_elect: solph.flows.Flow(variable_costs=price_electricity)},
    )
    # create sink object representing the feed-in
    elect_into_grid = solph.components.Sink(
        label="elect_into_grid",
        inputs={b_elect: solph.flows.Flow(variable_costs=price_feed_in)},
    )
    # create sink object representing the electricity demand
    elect_demand = solph.components.Sink(
        label="elect_demand",
        inputs={
            b_elect: solph.flows.Flow(
                nominal_value=1, fix=elect_demand_in_watt["Hourly_Sum"]
            )
        },
    )
    # create sink object representing the warm water demand
    warm_water = solph.components.Sink(
        label="warm_water_demand",
        inputs={
            b_heat: solph.flows.Flow(
                fix=warm_water_demand_in_watt["Hourly_Sum"], nominal_value=1
            )
        },
    )
    # create energy_system devices
    # create cooling device
    cooling_device = solph.components.Transformer(
        label="ElectricalCooler",
        inputs={
            b_cool: solph.flows.Flow(nominal_value=10000),
            b_elect: solph.flows.Flow(),
        },
        outputs={},
        conversion_factors={b_cool: 1, b_elect: 1},
    )

    # create pv-system
    pv_system = solph.components.Source(
        label="pv",
        outputs={
            b_elect: solph.Flow(
                fix=pv_data["AC System Output (W)"],
                nominal_value=solph.Investment(
                    maximum=25000, ep_costs=epc_pv_system, nonconvex=True
                ),
            )
        },
    )
    # create gas heater
    gas_heater = solph.components.Transformer(
        label="GasHeater",
        inputs={b_gas: solph.flows.Flow()},
        outputs={
            b_heat: solph.flows.Flow(
                nominal_value=solph.Investment(
                    maximum=1000 * 15,
                    ep_costs=epc_gas_heater,
                    nonconvex=True,
                )
            )
        },
        conversion_factors={b_heat: 0.95},
    )
    # create heat pump
    datasheet_cop = 4.5
    carnot_cop_7_35 = (35 + 273.15) / (35 - 7)
    cpf_7_35 = datasheet_cop / carnot_cop_7_35
    cpf_cop_7_35 = [cpf_7_35 * (40 + 273.15) / (40 - (temp))
                    for temp in t_outside]
    cpf_cop_7_35 = [1 / cop for cop in cpf_cop_7_35]
    heat_pump = solph.components.Transformer(
        label="HeatPump",
        inputs={b_elect: solph.flows.Flow()},
        outputs={
            b_heat: solph.flows.Flow(
                nominal_value=solph.Investment(
                    maximum=1000 * 20,
                    ep_costs=epc_heat_pump,
                    nonconvex=True,
                    offset=off_set_heat_pump,
                )
            )
        },
        conversion_factors={b_elect: cpf_cop_7_35, b_heat: 1},
    )
    # create heat storage
    heat_storage = solph.components.GenericStorage(
        label="GenericStorage",
        inputs={b_heat: solph.flows.Flow(variable_costs=0)},
        outputs={b_heat: solph.flows.Flow(variable_costs=0)},
        balanced=True,
        investment=solph.Investment(
            ep_costs=epc_heat_storage,
            nonconvex=True,
            maximum=5 * storage_volumen_in_Wh_per_kg * qubick_meter_water_in_kg,
        ),
        invest_relation_input_capacity=0.2,
        invest_relation_output_capacity=0.2,
        loss_rate=0.01,
        inflow_conversion_factor=0.99,
        outflow_conversion_factor=0.99,
    )
    # create building
    building = M5RC(
        label="GenericBuilding",
        inputs={b_heat: solph.flows.Flow(variable_costs=0)},
        outputs={b_cool: solph.flows.Flow(variable_costs=0)},
        solar_gains=solar_gains,
        t_outside=t_outside,
        internal_gains=internal_gains,
        t_set_heating=20,
        t_set_cooling=30,
        building_config=building_example.building_config,
        t_inital=20,
    )
    # add components to the energysystem
    es.add(
        building,
        heat_pump,
        gas_heater,
        elect_into_grid,
        elect_from_grid,
        gas_resource,
        warm_water,
        heat_storage,
        pv_system,
        cooling_device,
        elect_demand,
    )
    ##########################################################################
    # Optimise the energy system and plot the results
    ##########################################################################

    logging.info("Optimise the energy system")

    # initialise the operational model
    model = solph.Model(es)
    # add the emission constraint
    constraints.emission_limit(model, limit=100)
    # if tee_switch is true solver messages will be displayed
    logging.info("Solve the optimization problem")
    model.solve(solver=solver, solve_kwargs={"tee": True})

    logging.info("Store the energy system with the results.")

    # The processing module of the outputlib can be used to extract the results
    # from the model transfer them into a homogeneous structured dictionary.
    results = solph.processing.results(model)
    meta_results = solph.processing.meta_results(model)
    pp.pprint(meta_results)

    inv_elect_technologies = solph.views.node(
        results, "electricity")["scalars"]
    inv_heat_technologies = solph.views.node(results, "b_heat")["scalars"]
    investment = {
        "heat_pump": {
            "capacity": inv_heat_technologies[(("HeatPump", "b_heat"), "invest")],
            "epc": epc_heat_pump,
            "off_set": off_set_heat_pump,
            "lifetime": lifetime_heat_pump,
        },
        "generic_storage": {
            "capacity": inv_heat_technologies[(("GenericStorage", "b_heat"), "invest")],
            "epc": epc_heat_storage,
            "off_set": off_set_heat_storage,
            "lifetime": lifetime_heat_storage,
        },
        "gas_heater": {
            "capacity": inv_heat_technologies[(("GasHeater", "b_heat"), "invest")],
            "epc": epc_gas_heater,
            "off_set": off_set_heat_pump,
            "lifetime": lifetime_gas_heater,
        },
        "pv_system": {
            "capacity": inv_elect_technologies[(("pv", "electricity"), "invest")],
            "epc": epc_pv_system,
            "off_set": off_set_pv_system,
            "lifetime": lifetime_pv_system,
        },
    }
    annual_cost_components = {}
    for component in investment:
        annual_cost_components[component] = investment[component]["capacity"]
        if investment[component]["capacity"] != 0:
            annual_cost_components[component] = (
                investment[component]["epc"] *
                investment[component]["capacity"]
                + investment[component]["off_set"] /
                investment[component]["lifetime"]
            )
        else:
            investment[component]["capacity"] = 0

            # add results to the energy system to make it possible to store them.
    es.results["main"] = solph.processing.results(model)
    es.results["meta"] = solph.processing.meta_results(model)
    results = es.results["main"]

    flows = {
        "elect_from_grid": {
            "flow": views.node(results, "elect_from_grid")["sequences"][
                (("elect_from_grid", "electricity"), "flow")
            ],
            "price": price_electricity,
        },
        "elect_into_grid": {
            "flow": views.node(results, "elect_into_grid")["sequences"][
                (("electricity", "elect_into_grid"), "flow")
            ],
            "price": price_feed_in,
        },
        "gas_from_grid": {
            "flow": views.node(results, "gas_resource")["sequences"][
                (("gas_resource", "b_gas"), "flow")
            ],
            "price": price_gas,
        },
    }
    annual_cost_flows = {}
    for flow in flows:
        annual_cost_flows[flow] = flows[flow]["flow"].sum() * \
            flows[flow]["price"]
    total_results = {}
    total_results["flows"] = flows
    total_results["investment"] = investment
    total_results["objective_value"] = meta_results["objective"]
    total_results["refurbishment"] = cost_refurbishment
    total_results["annual_cost_flows"] = annual_cost_flows
    total_results["annual_cost_components"] = annual_cost_components

    # Open the file in write mode and dump the dictionary into it using pickle
    file_path = str(refurbishment_status) + ".pkl"
    with open(file_path, "wb") as file:
        pickle.dump(total_results, file)
    # print the solver results
    print("********* Meta results *********")
    pp.pprint(es.results["meta"])
    print("")


if __name__ == "__main__":
    refurbishment_status = [
        "no_refurbishment",
        "usual_refurbishment",
        "advanced_refurbishment",
    ]
    cost_refurbishment = {}
    results_dict = {}
    cost_refurbishment["no_refurbishment"] = 0
    cost_refurbishment["usual_refurbishment"] = economics.annuity(
        capex=70865.15, n=40, wacc=0.03
    ) - 70865.15 / (2 * 25)
    cost_refurbishment["advanced_refurbishment"] = economics.annuity(
        capex=96021.13, n=40, wacc=0.03
    ) - 96021.13 / (2 * 25)

    for status in refurbishment_status:
        main(refurbishment_status=status,
             cost_refurbishment=cost_refurbishment[status])

    for status in refurbishment_status:
        with open(status + ".pkl", "rb") as file:
            results_dict[status] = pickle.load(file)
    plot_stacked_bars(refurbishment_status, results_dict, cost_refurbishment)
