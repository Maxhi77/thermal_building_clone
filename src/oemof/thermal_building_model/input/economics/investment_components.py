from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents

# Investment Components for each technology
battery_config = InvestmentComponents(
    maximum_capacity=100000,
    minimum_capacity=1000,
    cost_per_unit=1000 / 1000,
    cost_offset=500,
    co2_per_capacity=0.1303,
    lifetime=20,
)
# capacity is m^3
hot_water_tank_config = InvestmentComponents(
    maximum_capacity=200,
    minimum_capacity=2,
    cost_per_unit=300 / 1000,
    cost_offset=200,
    co2_per_capacity=0.2695,
    lifetime=30,
    operational_cost_relative_to_capacity = 0.01
)

air_heat_pump_config = InvestmentComponents(
    maximum_capacity=100000,
    minimum_capacity=2000,
    cost_per_unit=1600 / 1000,
    cost_offset=6000,
    lifetime=20,
    co2_per_capacity = 0.03097,
    operational_cost_relative_to_capacity= 0.025,
)

gas_heater_config = InvestmentComponents(
    maximum_capacity=100000,
    minimum_capacity=2000,
    cost_per_unit=300 / 1000,
    cost_offset=3528,
    operational_cost_relative_to_capacity=0.01,
    co2_per_capacity=0.00809,
    lifetime=25,
)

pv_system_config = InvestmentComponents(
    maximum_capacity=12000,
    cost_per_unit=900 /1000,
    cost_offset=500,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.91,
    lifetime=25,
)

heat_grid_config = InvestmentComponents(
    maximum_capacity=30000,
    minimum_capacity=3000,
    cost_per_unit=20 / 1000,
    cost_offset=8000,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.02264,
    lifetime=25,
)

chp_config = InvestmentComponents(
    maximum_capacity=30000,
    minimum_capacity=3000,
    cost_per_unit=20 / 1000,
    cost_offset=8000,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.02264,
    lifetime=15,
)