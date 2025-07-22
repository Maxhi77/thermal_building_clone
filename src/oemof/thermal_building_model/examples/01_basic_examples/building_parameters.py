# Fensterbreite 0.9m
window_length =0.9
window_width=2.2
window_area= window_length * window_width
# Fensterhöhe? = 2.2
# Wandhöhe? = 2.39m

room_height = 2.39

floor_area_reference = 100
a_roof = {
    "a_roof_1": 85.62,
}
u_roof = {
    "u_roof_1": 0.943,
}
b_roof = {
    "b_roof_1": 1,
}

a_floor = {
    "a_floor_1": 74.1675
}
u_floor = {
    "u_floor_1": 3.84
}
b_floor = {
    "b_floor_1": 0.5
}

a_wall = {
    "a_wall_1": 41.39 * 4 + 17.37*2 -2.6
}
u_wall = {
    "u_wall_1": 0.336
}
b_wall = {
    "b_wall_1": 1
}

a_door = {
    "a_door_1": 2.6
}
u_door = {
    "u_door_1": 1.3
}

a_window = {
    "a_window_1": window_area*22
}
a_window_specific = {
    "a_window_horizontal": 0 ,
    "a_window_east": window_area*1 ,
    "a_window_south": window_area*8 ,
    "a_window_west": window_area*4,
    "a_window_north":window_area*9 ,
}

delta_u_thermal_bridiging = {"delta_u_thermal_bridiging": 0.05}

g_gl_n_window = {"g_gl_n_window_1": 0.6}

radiation_non_perpendicular_to_the_glazing = 0.9

frame_area_fraction_of_window = 0.3

heat_transfer_coefficient_ventilation = 0.51

total_air_change_rate = 0.6

