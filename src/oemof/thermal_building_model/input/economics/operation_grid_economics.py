from oemof.thermal_building_model.oemof_facades.base_component import GridComponents

# Gas Grid
gas_grid_config = GridComponents(
    working_rate=0.1187 / 1000,
    revenue=0,
    price_change_factor=0.062,
    co2_per_flow=0.2511 / 1000)


# Electricity Grid
electricity_grid_config = GridComponents(
    working_rate=0.4102 / 1000,
    revenue=0.0803 / 1000,
    price_change_factor=0.038,
    co2_per_flow=0.380 / 1000)


# Heat Grid
heat_grid_config = GridComponents(
    working_rate=0.1432 / 1000,
    revenue=0.0 / 1000,
    price_change_factor=0.061,
    co2_per_flow=0.1655 / 1000)

