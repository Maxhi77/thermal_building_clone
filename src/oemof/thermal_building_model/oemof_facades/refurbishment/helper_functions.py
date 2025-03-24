def calculate_heat_distribution(self):
    # todo get dimension of 1 timestep - so far static:
    nominal_timespan = 1  # hour
    # heize mit temp entsprechend era
    # wenn kein tabula refurb, setze heiz ref temp nach era
    # wenn tabula refurb, setze heiz ref temp auf ???
    # bekomme alte heiz last oder berechne sie und speichere sie
    # berechne neue heizlast mit ausgewählten sanierungsoptionen
    # berechne neue mögliche Vorlauftemperatur
    # WENN Heizlast <= 30 W/m² erlaube Flächenheizung
    tabula_building_code = self.building_tabula.tabula_building_code.array[0]
    index = tabula_building_code.find("Gen.") - 2
    tabula_gen = int(tabula_building_code[index:index + 1])
    if tabula_building_code.endswith(".001"):
        tabula_refurb = False
    else:
        tabula_refurb = True
    # era_related_heat_distribution_temp_levels = [(1980, 70), (2000, 60), (2010, 50), (3000, 40)]
    # todo move to init
    era_related_heat_distribution_temp_levels = [(5, 70), (6, 60), (7, 50), (8, 40)]  # (XY.Gen,T_inlet)
    T_old = 70
    for index in range(0, len(era_related_heat_distribution_temp_levels)):
        if tabula_gen >= era_related_heat_distribution_temp_levels[index][0]:
            if tabula_refurb:
                T_old = era_related_heat_distribution_temp_levels[index + 1][1]
            else:
                T_old = era_related_heat_distribution_temp_levels[index][1]
            continue

    space_heating_load_old = max(self.space_heating_demand_old) / nominal_timespan
    space_heating_load_new = get_space_heating_load_at(temperature=self.nominal_outside_temperature,
                                                       coldest_3day_finish_index=self.coldest_3day_finish_index,
                                                       ecos=self,
                                                       nominal_timespan=nominal_timespan)
    self.space_heat_load_max = space_heating_load_new
    distribution_delta = self.temp_levels['heat_distribution_inlet'] - self.temp_levels['heat_distribution_outlet']

    self.temp_levels['heat_distribution_inlet'] = calculate_inlet_temp(
        space_heating_load_old=space_heating_load_old,
        space_heating_load_new=space_heating_load_new,
        T_inlet_old=T_old)

    self.temp_levels['heat_distribution_inlet'] = self.find_nearest(era_related_heat_distribution_temp_levels,
                                                                    self.temp_levels['heat_distribution_inlet'])

    self.temp_levels['heat_distribution_outlet'] = self.temp_levels['heat_distribution_inlet'] - distribution_delta

    print(f"* ----- ----- Calcualted Heat Distribution -----\n"
          f"* -----       'heat_distribution_inlet':{self.temp_levels['heat_distribution_inlet']}\n"
          f"* -----       'heat_distribution_outlet':{self.temp_levels['heat_distribution_outlet']}\n")

    # put all levels together
    old_carrier_lvls = self.carriers['HeatCarrier']['temperature_levels']
    new_temp_levels = [self.temp_levels['heat_distribution_inlet'],
                       self.temp_levels['heat_distribution_outlet']]
    # remove duplicates
    all_temp_levels = list(set(new_temp_levels + old_carrier_lvls))
    # place new temp levels list into heat carrier

    # todo for delay debug

    ecos_temp_lvls = self.temp_levels.values()
    all_temp_levels = []

    if self.temp_levels['heat_distribution_inlet'] > self.temp_levels['domestic_heat_water']:
        max_value = self.temp_levels['heat_distribution_inlet']
    else:
        max_value = self.temp_levels['domestic_heat_water']

    for temp_lvl in ecos_temp_lvls:
        if temp_lvl <= max_value:
            all_temp_levels.append(temp_lvl)

    # sort and unify
    all_temp_levels = sorted(list(set(new_temp_levels + old_carrier_lvls)))

    # end todo

    print(f"* ----- ----- ALL TEMP LVLS \n {all_temp_levels}")
    self.carriers['HeatCarrier']['temperature_levels'] = all_temp_levels
