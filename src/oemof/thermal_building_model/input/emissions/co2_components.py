from oemof.thermal_building_model.oemof_facades.base_component import CO2Components


gas_co2 = CO2Components(per_flow=0.2511 / 1000)

electricity_co2 = CO2Components(per_flow=0.380 / 1000)

air_heat_pump_co2 = CO2Components(per_capacity=0.03097)

gas_heater_co2 = CO2Components(per_capacity=0.00809)

heat_grid_co2 = CO2Components(per_capacity=0.01264,
                              per_flow=0.1655 / 1000)

hot_water_tank_co2 = CO2Components(per_capacity=0.2695)

battery_co2 = CO2Components(per_capacity=0.1303)

pv_system_co2 = CO2Components(per_capacity=0.91)

