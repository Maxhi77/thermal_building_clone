from oemof import solph
from oemof.thermal_building_model.oemof_facades.infrastructure.grids import Grid
def get_oemof_component_name(component_dataclass):
    if isinstance(component_dataclass,Grid):
        component_dataclass.get_oemof_component_names()
    else:
        component_dataclass.get_oemof_component_name()

def get_invested_capacity_from_components_in_a_bus(results,bus_name):
    return solph.views.node(results, bus_name)["scalars"]

def get_flow_from_input_to_output(results,input_name,output_name):
    return solph.views.node(results, input_name)["sequences"][
                ((output_name, output_name), "flow")
            ]

