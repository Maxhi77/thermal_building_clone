from oemof.thermal_building_model.oemof_facades.base_component import EconomicsGrid

# Gas Grid
gas_grid_config = EconomicsGrid(
    working_rate=0.1003 / 1000,
    revenue=0,
    price_change_factor=0.062,
)

# Electricity Grid
electricity_grid_config = EconomicsGrid(
    working_rate=0.4175 / 1000,
    revenue=0.0803 / 1000,
    price_change_factor=0.038,
)

# Heat Grid
heat_grid_config = EconomicsGrid(
    working_rate=0.1032 / 1000,
    revenue=0.0 / 1000,
    price_change_factor=0.061,
)
