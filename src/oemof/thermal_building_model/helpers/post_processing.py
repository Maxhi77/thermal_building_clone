def calc_excess_temperature_degree_hours(t_air : list,
                                    boundary_temp: float = 26):
    '''
    Excess temperature degree hours of DIN 4108-2 in Kh/a
    Boundaries are for residential Buildings 1200Kh/a and non-residential
    Buildings 500 Kh/a
    '''
    excess_temperature_degree_hours = 0
    for temp in t_air:
        if temp > boundary_temp:
            difference = temp - boundary_temp
            excess_temperature_degree_hours = excess_temperature_degree_hours + difference
    return excess_temperature_degree_hours