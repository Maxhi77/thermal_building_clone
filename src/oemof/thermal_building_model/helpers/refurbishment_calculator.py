from dataclasses import dataclass
from oemof.thermal_building_model.oemof_facades.base_component import EconomicsInvestmentRefurbishment
@dataclass
class ThermalResistivity:
    internal_up = 0.10
    internal_hor = 0.13
    internal_down = 0.17
    external_air = 0.04
    external_soil = 0.00

def get_thermal_resistivity_of_element(u_value: float, rsi: float, rse: float):
    """ removes the thermal resistivity from air to mass
        :param rsi: internal resistivity
        :param rse: external resistivity
        :param u_value: old / fixed value
    """
    return 1 / u_value - rsi - rse
from dataclasses import dataclass
from typing import Optional

@dataclass
class BuildingElement:
    old_u_value: float
    new_u_value: float
    thermal_conductivity: float

    def calculate_insulation_thickness(self, internal_resistivity, external_resistivity):
        """
        Berechnet die notwendige Dämmstoffdicke für die gewünschte energetische Verbesserung.
        """
        fixed_thermal_resistivity = get_thermal_resistivity_of_element(
            u_value=self.old_u_value,
            rsi=internal_resistivity,
            rse=external_resistivity
        )

        # Berechnung der Dämmstoffdicke
        self.insulation_thickness = (
            (1 / self.new_u_value - (external_resistivity + fixed_thermal_resistivity + internal_resistivity))
            * 100
            * self.thermal_conductivity
        )
        return self.insulation_thickness

# 🔥 Verbesserte Kindklassen mit `property` für Wärmewiderstände
class Floor(BuildingElement):
    @property
    def internal_resistivity(self):
        return ThermalResistivity.internal_down

    @property
    def external_resistivity(self):
        return ThermalResistivity.external_soil

    def calculate_insulation_thickness(self):
        return super().calculate_insulation_thickness(self.internal_resistivity, self.external_resistivity)

class Roof(BuildingElement):
    @property
    def internal_resistivity(self):
        return ThermalResistivity.internal_up

    @property
    def external_resistivity(self):
        return ThermalResistivity.external_air

    def calculate_insulation_thickness(self):
        return super().calculate_insulation_thickness(self.internal_resistivity, self.external_resistivity)

class Wall(BuildingElement):
    @property
    def internal_resistivity(self):
        return ThermalResistivity.internal_hor

    @property
    def external_resistivity(self):
        return ThermalResistivity.external_air

    def calculate_insulation_thickness(self):
        return super().calculate_insulation_thickness(self.internal_resistivity, self.external_resistivity)


@dataclass
class FixedRefurbStrategy:
    """ usecase: data container for one refurbishment strategy with fixed attributes
        e.g. windows, doors costs depending on the amount """
    name: str = 'name'
    units: int | float = 0
    investment_costs_per_unit: float = 0.0
    specific_maintenance_costs_per_unit: float = 0.0
    co2_costs_per_unit: float = 0.0
    depreciation_period: int = 30

    def calculate_u_value(self):
        """ no dimensional assign since whole element should be replaced """
        return self.u_value

    def investment_costs(self, units: float = None):
        if units is None:
            return self.investment_costs_per_unit * self.units
        else:
            return self.investment_costs_per_unit * units

    def specific_maintenance_costs(self):
        return self.specific_maintenance_costs_per_unit

    def get_co2_costs(self, units: float = None):
        if units is None:
            return self.co2_costs_per_unit * self.units
        else:
            return self.co2_costs_per_unit * units

    def get_depreciation_period(self):
        return self.depreciation_period

    def set_units(self, units: int | float):
        self.units = float(units)

    def __str__(self):
        return str(f"{self.nominal_value} cm {self.name}")
