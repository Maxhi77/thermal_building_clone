from oemof.thermal_building_model.oemof_facades.base_component import EconomicsInvestmentRefurbishment

wall_config = EconomicsInvestmentRefurbishment(
    component="wall",
    material="mineral_wool",
    thermal_conductivity=0.035,
    cost_per_unit=4.49,
    cost_offset=155.06,
    lifetime=50,
    co2_per_unit = 69.3
)

roof_config = EconomicsInvestmentRefurbishment(
    component="roof",
    material="mineral_wool",
    thermal_conductivity=0.035,
    cost_per_unit=5.45,
    cost_offset=171.08,
    lifetime=50,
    co2_per_unit=46.24
)

floor_config = EconomicsInvestmentRefurbishment(
    component="floor",
    material="mineral_wool",
    thermal_conductivity=0.035,
    cost_per_unit=2.32,
    cost_offset=70.35,
    lifetime=50,
    co2_per_unit=134.15
)

door_config = {
    1: EconomicsInvestmentRefurbishment(
    component="door",
    material="new",
    thermal_conductivity=1 / 1.8,
    cost_per_unit=0,
    cost_offset=3000,
    lifetime=25,
    co2_per_unit=500,
    ),
    2: EconomicsInvestmentRefurbishment(
    component="door",
    material="new",
    thermal_conductivity=1 / 1.3,
    cost_per_unit=0,
    cost_offset=5000,
    lifetime=25,
    co2_per_unit=500
    ),
    3: EconomicsInvestmentRefurbishment(
    component="door",
    material="new",
    thermal_conductivity=1 / 1.1,
    cost_per_unit=0,
    cost_offset=6000,
    lifetime=25,
    co2_per_unit=500
    ),
    4: EconomicsInvestmentRefurbishment(
    component="door",
    material="new",
    thermal_conductivity=1 / 0.8,
    cost_per_unit=2.32,
    cost_offset=7000,
    lifetime=25,
    co2_per_unit=500
    ),

}

window_config = {
    1: EconomicsInvestmentRefurbishment(
    component="window",
    material="new",
    thermal_conductivity=1 / 1.3,
    cost_per_unit=680.54,
    lifetime=25,
    co2_per_unit=200,
    cost_per_unit_exponent= -0.216
    ),
    2: EconomicsInvestmentRefurbishment(
    component="window",
    material="new",
    thermal_conductivity=1 / 1,
    cost_per_unit=773.85,
    lifetime=25,
    co2_per_unit=200,
    cost_per_unit_exponent= -0.216
    ),
    3: EconomicsInvestmentRefurbishment(
    component="window",
    material="new",
    thermal_conductivity=1 / 0.8,
    cost_per_unit=1078.65,
    lifetime=25,
    co2_per_unit=200,
    cost_per_unit_exponent= -0.268
    ),

}