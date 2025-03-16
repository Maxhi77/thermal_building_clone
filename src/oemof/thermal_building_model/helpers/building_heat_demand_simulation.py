from typing import List
import warnings
from thermal_building_model.m_5RC import M5RC
class HeatDemand_Simulation_5RC():
    r"""
    This class simulates the heating and cooling demand of a 5RC thermal
    building model. It can be used in the oemof.thermal_building_model
    repository as a comparison to an optimized building which uses the
    building envelope as a thermal storage.
    
    The “RC_BuildingSimulator” from Jayathissa Prageeth
    (https://github.com/architecture-building-systems/RC_BuildingSimulator) is used.
    """ # noqa: E501

    def __init__(
        self,
        building_config,
        label: str,
        t_outside: List,
        solar_gains: List,
        internal_gains: List,
        t_set_heating: List | float,
        t_set_cooling: List | float,
        t_set_heating_max: List | float,
        max_power_heating: float,
        max_power_cooling: float,
        timesteps: int,
        phi_m_tot: float = 0,
        t_inital: float = 20,
        t_m: float = 20,
        t_m_ts: float = 20,
    ):
        self.building_config = building_config
        self.t_e = t_outside
        self.internal_gains = internal_gains
        self.phi_m_tot = phi_m_tot
        self.solar_gains = solar_gains
        self.t_set_heating = t_set_heating
        if t_set_heating_max is None:
            self.t_set_heating_max = t_set_heating
        else:
            self.t_set_heating_max = t_set_heating_max
        if isinstance(self.t_set_heating_max, list):
            t_set_heating_max_down = min(self.t_set_heating_max)
        else:
            t_set_heating_max_down = self.t_set_heating_max
        if isinstance(self.t_set_heating, list):
            t_set_heating_up = max(self.t_set_heating)
        else:
            t_set_heating_up = self.t_set_heating

        assert t_set_heating_max_down > t_set_heating_up, "set heating max must be " \
                                                          "higher than set heating"
        if t_set_heating_max_down - t_set_heating_up < 0.2:
            warnings.warn("set heating max should have at least a difference of "
                          "0.2 Celsius to set_heating to guarantee quick optimization"
                          ,UserWarning)
        self.t_set_cooling = t_set_cooling
        self.t_inital = t_inital
        self.t_m = t_m
        self.t_m_ts = t_m_ts
        self.max_power_heating = max_power_heating
        self.max_power_cooling = max_power_cooling
        self.floor_area = self.building_config.floor_area  # [m2] Floor Area
        self.mass_area = (
            self.building_config.mass_area
        )  # [m2] Effective Mass Area DIN 12.3.1.2
        self.A_t = (
            self.building_config.total_internal_area
        )  # [m2] the area of all surfaces facing the room DIN 7.2.2.2
        self.c_m = self.building_config.c_m  # [kWh/K] Room Capacitance
        self.ach_tot = (
            self.building_config.total_air_change_rate
        )  # [m3/s]Total Air Changes Per Hour

        self.h_tr_em = (
            self.building_config.h_tr_em
        )  # [W/K] Conductance of opaque surfaces to exterior
        self.h_tr_w = (
            self.building_config.h_tr_w
        )  # [W/K] Conductance to exterior through glazed surfaces
        # [W/K] Conductance to ventilation
        self.h_ve = self.building_config.h_ve
        self.h_tr_ms = (
            self.building_config.h_tr_ms
        )  # [W/K] transmittance from the internal air to the thermal mass
        self.h_tr_is = (
            self.building_config.h_tr_is
        )  # [W/K] Conductance from the conditioned air to interior zone surface

        self.phi_st = (
            []
        )  # [W] Combination of internal and solar gains directly to the internal surfa
        self.phi_m = (
            []
        )  # [W] Combination of internal and solar gains directly to the medium
        self.phi_ia = []  # [W] Combination of internal and solar gains to the air
        self.h_tr_1 = (
            M5RC.calc_h_tr_1(self)
        )  # [W/K] combined heat conductance, see function for definition
        self.h_tr_2 = (
            M5RC.calc_h_tr_2(self)
        )  # [W/K] combined heat conductance, see function for definition
        self.h_tr_3 = (
            M5RC.calc_h_tr_3(self)
        )  # [W/K] combined heat conductance, see function for definition
        for i in range(len(self.solar_gains)):
            self.phi_ia.append(M5RC.calc_phi_ia(self, i))
            self.phi_st.append(M5RC.calc_phi_st(self, i))
            self.phi_m.append(M5RC.calc_phi_m(self, i))
        self.timestep = timesteps
    def solve(self):
        first=True
        heating_demand = []
        cooling_demand = []
        t_air = []
        self.max_power_cooling = - self.max_power_cooling
        for timestep in range(self.timestep):
            if isinstance(self.t_set_heating, (float, int)):
                self.t_set_heating_calculation = self.t_set_heating
            elif isinstance(self.t_set_heating, List):
                self.t_set_heating_calculation = self.t_set_heating[timestep]
            if isinstance(self.t_set_cooling, (float, int)):
                self.t_set_cooling_calculation = self.t_set_cooling
            elif isinstance(self.t_set_cooling, List):
                self.t_set_cooling_calculation = self.t_set_cooling[timestep]
            if first:
                first=False
                self.t_m_prev=20
            self.solve_energy(internal_gains = self.internal_gains[timestep],
                              solar_gains=self.solar_gains[timestep],
                              t_out=self.t_e[timestep],
                              t_m_prev=self.t_m_prev,
                              )
            self.t_m_prev = self.t_m_next
            heating_demand.append(self.heating_demand)
            cooling_demand.append(-self.cooling_demand)
            t_air.append(self.t_air)
        return heating_demand, cooling_demand, t_air

    def solve_energy(self, internal_gains, solar_gains, t_out, t_m_prev):
        """
        Calculates the heating and cooling consumption of a building for a set timestep

        :param internal_gains: internal heat gains from people and appliances [W]
        :type internal_gains: float
        :param solar_gains: solar heat gains [W]
        :type solar_gains: float
        :param t_out: Outdoor air temperature [C]
        :type t_out: float
        :param t_m_prev: Previous air temperature [C]
        :type t_m_prev: float

        :return: self.heating_demand, space heating demand of the building
        :return: self.heating_sys_electricity, heating electricity consumption
        :return: self.heating_sys_fossils, heating fossil fuel consumption
        :return: self.cooling_demand, space cooling demand of the building
        :return: self.cooling_sys_electricity, electricity consumption from cooling
        :return: self.cooling_sys_fossils, fossil fuel consumption from cooling
        :return: self.electricity_out, electricity produced from combined heat pump systems
        :return: self.sys_total_energy, total exergy consumed (electricity + fossils) for heating and cooling
        :return: self.heating_energy, total exergy consumed (electricity + fossils) for heating
        :return: self.cooling_energy, total exergy consumed (electricity + fossils) for cooling
        :return: self.cop, Coefficient of Performance of the heating or cooling system
        :rtype: float

        """
        # Main File

        # check demand, and change state of self.has_heating_demand, and self._has_cooling_demand
        self.has_demand(internal_gains, solar_gains, t_out, t_m_prev)

        if not self.has_heating_demand and not self.has_cooling_demand:

            # no heating or cooling demand
            # calculate temperatures of building R-C-model and exit
            # --> rc_model_function_1(...)
            self.energy_demand = 0

            self.heating_demand = 0  # Energy required by the zone
            self.cooling_demand = 0  # Energy surplus of the zone

        else:
            # has heating/cooling demand

            # Calculates energy_demand used below
            self.calc_energy_demand(
                internal_gains, solar_gains, t_out, t_m_prev)

            self.calc_temperatures_crank_nicolson(
                self.energy_demand, internal_gains, solar_gains, t_out, t_m_prev)
            # calculates the actual t_m resulting from the actual heating
            # demand (energy_demand)

            if self.has_heating_demand:
                # All Variables explained underneath line 467
                self.heating_demand = self.energy_demand
                self.cooling_demand = 0

            elif self.has_cooling_demand:
                self.heating_demand = 0
                self.cooling_demand = self.energy_demand
    # TODO: rename. this is expected to return a boolean. instead, it changes state??? you don't want to change state...
    # why not just return has_heating_demand and has_cooling_demand?? then call the function "check_demand"
    # has_heating_demand, has_cooling_demand = self.check_demand(...)

    @property
    def t_opperative(self):
        """
        The opperative temperature is a weighted average of the air and mean radiant temperatures.
        It is not used in any further calculation at this stage
        # (C.12) in [C.3 ISO 13790]
        """
        return 0.3 * self.t_air + 0.7 * self.t_s
    def has_demand(self, internal_gains, solar_gains, t_out, t_m_prev):
        """
        Determines whether the building requires heating or cooling
        Used in: solve_energy()

        # step 1 in section C.4.2 in [C.3 ISO 13790]
        """

        # set energy demand to 0 and see if temperatures are within the comfort
        # range
        energy_demand = 0
        # Solve for the internal temperature t_Air
        self.calc_temperatures_crank_nicolson(
            energy_demand, internal_gains, solar_gains, t_out, t_m_prev)

        # If the air temperature is less or greater than the set temperature,
        # there is a heating/cooling load
        if self.t_air < self.t_set_heating_calculation:
            self.has_heating_demand = True
            self.has_cooling_demand = False
        elif self.t_air > self.t_set_cooling_calculation:
            self.has_cooling_demand = True
            self.has_heating_demand = False
        else:
            self.has_heating_demand = False
            self.has_cooling_demand = False

    def calc_temperatures_crank_nicolson(self, energy_demand, internal_gains, solar_gains, t_out, t_m_prev):
        """
        Determines node temperatures and computes derivation to determine the new node temperatures
        Used in: has_demand(), solve_energy(), calc_energy_demand()
        # section C.3 in [C.3 ISO 13790]
        """

        self.calc_heat_flow(t_out, internal_gains, solar_gains, energy_demand)

        self.calc_phi_m_tot(t_out)

        # calculates the new bulk temperature POINT from the old one
        self.calc_t_m_next(t_m_prev)

        # calculates the AVERAGE bulk temperature used for the remaining
        # calculation
        self.calc_t_m(t_m_prev)

        self.calc_t_s(t_out)

        self.calc_t_air(t_out)

        return self.t_m, self.t_air, self.t_opperative

    def calc_energy_demand(self, internal_gains, solar_gains, t_out, t_m_prev):
        """
        Calculates the energy demand of the space if heating/cooling is active
        Used in: solve_energy()
        # Step 1 - Step 4 in Section C.4.2 in [C.3 ISO 13790]
        """

        # Step 1: Check if heating or cooling is needed
        # (Not needed, but doing so for readability when comparing with the standard)
        # Set heating/cooling to 0
        energy_demand_0 = 0
        # Calculate the air temperature with no heating/cooling
        t_air_0 = self.calc_temperatures_crank_nicolson(
            energy_demand_0, internal_gains, solar_gains, t_out, t_m_prev)[1]

        # Step 2: Calculate the unrestricted heating/cooling required

        # determine if we need heating or cooling based based on the condition
        # that no heating or cooling is required
        if self.has_heating_demand:
            t_air_set = self.t_set_heating_calculation
        elif self.has_cooling_demand:
            t_air_set = self.t_set_cooling_calculation
        else:
            raise NameError(
                'heating function has been called even though no heating is required')

        # Set a heating case where the heating load is 10x the floor area (10
        # W/m2)
        energy_floorAx10 = 10 * self.floor_area

        # Calculate the air temperature obtained by having this 10 W/m2
        # setpoint
        t_air_10 = self.calc_temperatures_crank_nicolson(
            energy_floorAx10, internal_gains, solar_gains, t_out, t_m_prev)[1]

        # Determine the unrestricted heating/cooling off the building
        self.calc_energy_demand_unrestricted(
            energy_floorAx10, t_air_set, t_air_0, t_air_10)

        # Step 3: Check if available heating or cooling power is sufficient
        if self.max_power_cooling <= self.energy_demand_unrestricted <= self.max_power_heating:

            self.energy_demand = self.energy_demand_unrestricted

        # Step 4: if not sufficient then set the heating/cooling setting to the
        # maximum
        # necessary heating power exceeds maximum available power
        assert (self.energy_demand_unrestricted > self.max_power_heating,
                "max heating power smaller than heat demand")

        # necessary cooling power exceeds maximum available power
        assert (self.energy_demand_unrestricted < self.max_power_cooling,
                "max cooling power smaller than cooling demand")

        # calculate system temperatures for Step 3/Step 4
        self.calc_temperatures_crank_nicolson(
            self.energy_demand, internal_gains, solar_gains, t_out, t_m_prev)

    def calc_energy_demand_unrestricted(self, energy_floorAx10, t_air_set, t_air_0, t_air_10):
        """
        Calculates the energy demand of the system if it has no maximum output restrictions
        # (C.13) in [C.3 ISO 13790]


        Based on the Thales Intercept Theorem.
        Where we set a heating case that is 10x the floor area and determine the temperature as a result
        Assuming that the relation is linear, one can draw a right angle triangle.
        From this we can determine the heating level required to achieve the set point temperature
        This assumes a perfect HVAC control system
        """
        self.energy_demand_unrestricted = energy_floorAx10 * \
            (t_air_set - t_air_0) / (t_air_10 - t_air_0)

    def calc_heat_flow(self, t_out, internal_gains, solar_gains, energy_demand):
        """
        Calculates the heat flow from the solar gains, heating/cooling system, and internal gains into the building

        The input of the building is split into the air node, surface node, and thermal mass node based on
        on the following equations

        #C.1 - C.3 in [C.3 ISO 13790]

        Note that this equation has diverged slightly from the standard
        as the heating/cooling node can enter any node depending on the
        emission system selected

        """

        # Calculates the heat flows to various points of the building based on the breakdown in section C.2, formulas C.1-C.3
        # Heat flow to the air node
        self.phi_ia = 0.5 * internal_gains + energy_demand
        # Heat flow to the surface node
        self.phi_st = (1 - (self.mass_area / self.A_t) -
                       (self.h_tr_w / (9.1 * self.A_t))) * (0.5 * internal_gains + solar_gains)
        # Heatflow to the thermal mass node
        self.phi_m = (self.mass_area / self.A_t) * \
            (0.5 * internal_gains + solar_gains)


    def calc_t_m_next(self, t_m_prev):
        """
        Primary Equation, calculates the temperature of the next time step
        # (C.4) in [C.3 ISO 13790]
        """

        self.t_m_next = ((t_m_prev * ((self.c_m / 3600.0) - 0.5 * (self.h_tr_3 + self.h_tr_em))) +
                         self.phi_m_tot) / ((self.c_m / 3600.0) + 0.5 * (self.h_tr_3 + self.h_tr_em))

    def calc_phi_m_tot(self, t_out):
        """
        Calculates a global heat transfer. This is a definition used to simplify equation
        calc_t_m_next so it's not so long to write out
        # (C.5) in [C.3 ISO 13790]
        # h_ve = h_ve_adj and t_supply = t_out [9.3.2 ISO 13790]
        """

        t_supply = t_out  # ASSUMPTION: Supply air comes straight from the outside air

        self.phi_m_tot = self.phi_m + self.h_tr_em * t_out + \
            self.h_tr_3 * (self.phi_st + self.h_tr_w * t_out + self.h_tr_1 *
                           ((self.phi_ia / self.h_ve) + t_supply)) / self.h_tr_2

    def calc_t_m(self, t_m_prev):
        """
        Temperature used for the calculations, average between newly calculated and previous bulk temperature
        # (C.9) in [C.3 ISO 13790]
        """
        self.t_m = (self.t_m_next + t_m_prev) / 2.0

    def calc_t_s(self, t_out):
        """
        Calculate the temperature of the inside room surfaces
        # (C.10) in [C.3 ISO 13790]
        # h_ve = h_ve_adj and t_supply = t_out [9.3.2 ISO 13790]
        """

        t_supply = t_out  # ASSUMPTION: Supply air comes straight from the outside air

        self.t_s = (self.h_tr_ms * self.t_m + self.phi_st + self.h_tr_w * t_out + self.h_tr_1 *
                    (t_supply + self.phi_ia / self.h_ve)) / \
                   (self.h_tr_ms + self.h_tr_w + self.h_tr_1)

    def calc_t_air(self, t_out):
        """
        Calculate the temperature of the air node
        # (C.11) in [C.3 ISO 13790]
        # h_ve = h_ve_adj and t_supply = t_out [9.3.2 ISO 13790]
        """

        t_supply = t_out

        # Calculate the temperature of the inside air
        self.t_air = (self.h_tr_is * self.t_s + self.h_ve *
                      t_supply + self.phi_ia) / (self.h_tr_is + self.h_ve)