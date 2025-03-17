from oemof.thermal_building_model.oemof_facades.infrastructure.grids import ElectricityGrid, HeatGrid
from oemof.thermal_building_model.oemof_facades.infrastructure.carriers import ElectricityCarrier, HeatCarrier
from oemof.thermal_building_model.oemof_facades.helper_functions import connect_buses, flatten_components_list
from  oemof.thermal_building_model.oemof_facades.infrastructure.demands import ElectricityDemand, HeatDemand
from  oemof.thermal_building_model.oemof_facades.technologies.renewable_energy_source import PVSystem
from  oemof.thermal_building_model.oemof_facades.technologies.storages import Battery, HotWaterTank
from oemof import solph
import matplotlib.pyplot as plt
import networkx as nx
from oemof.network.graph import create_nx_graph
from  oemof.thermal_building_model.oemof_facades.constraints.storage_level import storage_level_constraint
#  create solver
solver = "gurobi"  # 'glpk', 'gurobi',....
number_of_time_steps = 3
date_time_index = solph.create_time_index(
    2012, number=number_of_time_steps)
es = solph.EnergySystem(timeindex=date_time_index,
                        infer_last_interval=False)


electricity_grid_dataclass = ElectricityGrid()
electricity_grid_bus_from_grid = electricity_grid_dataclass.get_bus_from_grid()
electricity_grid_bus_into_grid = electricity_grid_dataclass.get_bus_into_grid()

electricity_grid_sink = electricity_grid_dataclass.create_sink()
electricity_grid_source = electricity_grid_dataclass.create_source()

electricity_carrier_dataclass = ElectricityCarrier()
electricity_carrier_bus = electricity_carrier_dataclass.get_bus()
connect_buses(input=electricity_grid_bus_from_grid, target=electricity_carrier_bus, output=electricity_grid_bus_into_grid)
electricity_demand_dataclass = ElectricityDemand(
                                                value_list=[0,0,4],
                                                bus=electricity_carrier_bus)
electricity_demand = electricity_demand_dataclass.create_demand()

electricity  = [electricity_grid_bus_from_grid,
                electricity_grid_bus_into_grid,
                electricity_grid_sink,
                electricity_grid_source,
                electricity_carrier_bus,
                electricity_demand]

if False:
    gas_carrier_dataclass = GasCarrier()
    gas_carrier_bus = gas_carrier_dataclass.get_bus()

heat_grid_temperature_levels = [20,40]
heat_grid_dataclass = HeatGrid()
heat_grid_sink = heat_grid_dataclass.create_sink()
heat_grid_source = heat_grid_dataclass.create_source()
heat_grid_bus_from_grid = heat_grid_dataclass.get_bus_from_grid()
heat_grid_bus_into_grid = heat_grid_dataclass.get_bus_into_grid()

heat_carrier_temperature_levels = [20]
heat_carrier_dataclass = HeatCarrier(levels = heat_carrier_temperature_levels)
heat_carrier_dataclass.connect_buses_decreasing_levels()
heat_carrier_bus = heat_carrier_dataclass.get_bus()
connect_buses(
    input=heat_grid_bus_from_grid,
    target=heat_carrier_bus, output=heat_grid_bus_into_grid)


heat_demand_dataclass = HeatDemand(name="HotWater",
                                   value_list=[0,0,2],
                                   level = 20,
                                   bus=heat_carrier_dataclass.get_bus([20]))


hot_water_tank_dataclass = HotWaterTank(
    min_temperature=min(heat_carrier_bus.keys()),
    max_temperature=max(heat_carrier_bus.keys())+10,
    temperature_buses = heat_carrier_bus
    )
hot_water_tank_bus_from_storage = hot_water_tank_dataclass.generate_bus_from_storage()
hot_water_tank_bus_into_storage = hot_water_tank_dataclass.generate_storage_into_bus()
hot_water_tank = hot_water_tank_dataclass.create_storage(input_bus=hot_water_tank_bus_into_storage,
                                                        output_bus=hot_water_tank_bus_from_storage)
generate_error = False
if generate_error:
    connect_buses(input=heat_carrier_bus,
                  target=hot_water_tank_bus_into_storage,

        )

connect_buses(input = hot_water_tank_bus_from_storage,
             target=heat_carrier_bus)

es.add(hot_water_tank_bus_from_storage,hot_water_tank_bus_into_storage,hot_water_tank)

find_error_plotting=False
if find_error_plotting:
    list=[]
    for i in heat_carrier_bus:
        list.append(heat_carrier_bus[i].outputs)
    for i in heat_carrier_bus:
        list.append(heat_carrier_bus[i].inputs)
    list.append(hot_water_tank_bus_into_storage.inputs)
    list.append(hot_water_tank_bus_into_storage.outputs)
if False:
    battery_dataclass = Battery(investment=True)
    battery = battery_dataclass.create_storage(input_bus = electricity_carrier_bus,
                                               output_bus = electricity_carrier_bus,
                                               )
    es.add(battery)

pv_dataclass = PVSystem()
pv_system = pv_dataclass.create_source(output_bus = electricity_carrier_bus,
                         )
es.add(pv_system)

heat_demand = heat_demand_dataclass.create_demand()
heat = []
if True:
    heat = [heat_grid_sink,
            heat_grid_source,
            heat_grid_bus_from_grid,
            heat_grid_bus_into_grid,
            heat_carrier_bus,
            heat_demand]

if False:
    electricity_components = flatten_components_list(electricity)
    es.add(*(electricity_components))
heat_components = flatten_components_list(heat)
# Add all components to the energy system in one go
es.add(*(heat_components))
# Create the graph from the energy system (es)
graph = create_nx_graph(es)

# Draw the graph
plt.figure(figsize=(10, 6))  # Set figure size
nx.draw(graph, with_labels=True, font_size=8)

# Show the graph
plt.show()
model = solph.Model(es)
if False:
    storage_level_constraint(model,
                             name=hot_water_tank.label,
                             storage_component=hot_water_tank,
                             multiplexer_bus=hot_water_tank_multiplexer_bus,
                             input_levels=hot_water_tank_dataclass.get_temperature_buses(),
                             output_levels=hot_water_tank_dataclass.get_temperature_buses())
model.solve(solver=solver, solve_kwargs={"tee": True})


# The processing module of the outputlib can be used to extract the results
# from the model transfer them into a homogeneous structured dictionary.
results = solph.processing.results(model)
meta_results = solph.processing.meta_results(model)
