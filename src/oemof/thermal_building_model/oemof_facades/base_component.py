from dataclasses import dataclass
from oemof.tools import economics
from typing import Optional

@dataclass(kw_only=True)
class BaseComponent:
    name: str
    investment: Optional[bool] = None

@dataclass
class EconomicsInvestmentComponents:
    maximum_capacity: float
    cost_per_unit: float
    cost_offset: float
    lifetime: float
    cost_offset: float
    operational_cost_relative_to_capacity: float = 0
    minimal_capacity: float = 0
    wacc: float = 0.03
    observation_period: float = 20# Weighted Average Cost of Capital (default 3%)

    def calculate_epc(self) -> float:
        """Calculates Equivalent Annual Cost (EPC) using annuity formula."""
        capex = (
                self.cost_per_unit
                + self.cost_per_unit * self.operational_cost_relative_to_capacity * self.lifetime
                + (self.cost_offset / self.lifetime if self.cost_offset is not None else 0)  # ✅ Correct check
        )
        return economics.annuity(capex=capex, n=self.observation_period, u=self.lifetime, wacc=self.wacc)

@dataclass
class EconomicsInvestmentRefurbishment:
    material: str
    component: str
    cost_per_unit: float
    thermal_conductivity: float
    lifetime: float
    cost_offset: Optional[float] = None
    shgc: Optional[float] = None
    wacc: float = 0.03
    observation_period: float = 20
    co2_per_unit: float  = 0
    wacc: float = 0.03
    cost_per_unit_exponent :float = 1
    # Weighted Average Cost of Capital (default 3%)
    def calculate_epc(self, investment) -> float:
        """Calculates Equivalent Annual Cost (EPC) using annuity formula."""
        capex = (
                investment
                 # ✅ Correct check
        )
        return economics.annuity(capex=capex, n=self.observation_period, u=self.lifetime, wacc=self.wacc)
    def get_depreciation_period(self):
        return self.observation_period / self.lifetime
@dataclass(kw_only=True)
@dataclass
class EconomicsGrid:
    working_rate: float
    revenue: float
    price_change_factor: float

@dataclass
class CO2Components:
    per_capacity: float = 0.00  # kg CO2 per W installed
    per_flow: float = 0.00  # kg CO2 per Wh used
    offset_capacity: float = 0.00  # CO2 offset in W
    lifetime: Optional[float] = None
    observation_period: Optional[float] = 20

    def __post_init__(self):
        if self.lifetime is not None:
            self.per_capacity = self.per_capacity * self.get_depreciation_period()
            self.offset_capacity = self.offset_capacity * self.get_depreciation_period()
    def get_depreciation_period(self):
        return self.observation_period / self.lifetime






