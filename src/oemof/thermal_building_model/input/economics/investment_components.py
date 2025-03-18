from oemof.thermal_building_model.oemof_facades.base_component import EconomicsInvestmentComponents

# Investment Components for each technology
battery_config = EconomicsInvestmentComponents(
    maximum_capacity=10000,
    cost_per_unit=1000 / 1000,
    cost_offset=10,
    lifetime=20,
)
# capacity is m^3
hot_water_tank_config = EconomicsInvestmentComponents(
    maximum_capacity=100,
    cost_per_unit=1200 / 1000,
    cost_offset=0,
    lifetime=20,
    operational_cost_relative_to_capacity = 0.02
)

air_heat_pump_config = EconomicsInvestmentComponents(
    maximum_capacity=15000,
    cost_per_unit=600 / 1000,
    cost_offset=1000,
    lifetime=20,
    operational_cost_relative_to_capacity= 0.02
)

gas_heater_config = EconomicsInvestmentComponents(
    maximum_capacity=15000,
    cost_per_unit=100 / 1000,
    cost_offset=0,
    operational_cost_relative_to_capacity=0.015,
    lifetime=20,
)

pv_system_config = EconomicsInvestmentComponents(
    maximum_capacity=10000,
    cost_per_unit=800 / 1000,
    cost_offset=0,
    operational_cost_relative_to_capacity=0.02,
    lifetime=25,
)

heat_grid_config = EconomicsInvestmentComponents(
    maximum_capacity=10000,
    cost_per_unit=800 / 1000,
    cost_offset=0,
    operational_cost_relative_to_capacity=0.02,
    lifetime=25,
)