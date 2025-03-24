from oemof.thermal_building_model.oemof_facades.base_component import InvestmentComponents

# Investment Components for each technology
battery_config = InvestmentComponents(
    maximum_capacity=20000,
    minimum_capacity=1000,
    cost_per_unit=1000 / 1000,
    cost_offset=500,
    co2_per_capacity=0.1303,
    lifetime=20,
)
# capacity is m^3
hot_water_tank_config = InvestmentComponents(
    maximum_capacity=500,
    minimum_capacity=1,
    cost_per_unit=500 / 1000,
    cost_offset=800,
    co2_per_capacity=0.2695,
    lifetime=20,
    operational_cost_relative_to_capacity = 0.02
)

air_heat_pump_config = InvestmentComponents(
    maximum_capacity=30000,
    minimum_capacity=2000,
    cost_per_unit=500 / 1000,
    cost_offset=5000,
    lifetime=20,
    co2_per_capacity = 0.03097,
    operational_cost_relative_to_capacity= 0.02,
)

gas_heater_config = InvestmentComponents(
    maximum_capacity=30000,
    minimum_capacity=1000,
    cost_per_unit=100 / 1000,
    cost_offset=2800,
    operational_cost_relative_to_capacity=0.015,
    co2_per_capacity=0.00809,
    lifetime=20,
)

pv_system_config = InvestmentComponents(
    maximum_capacity=12000,
    cost_per_unit=800 / 1000,
    cost_offset=600,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.91,
    lifetime=25,
)

heat_grid_config = InvestmentComponents(
    maximum_capacity=30000,
    minimum_capacity=5000,
    cost_per_unit=800 / 1000,
    cost_offset=6000,
    operational_cost_relative_to_capacity=0.02,
    co2_per_capacity=0.02264,
    lifetime=25,
)