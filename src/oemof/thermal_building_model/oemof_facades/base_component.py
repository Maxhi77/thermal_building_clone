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
    operational_cost_per_capacity: float = 0
    minimal_capacity: float = 0
    wacc: float = 0.03  # Weighted Average Cost of Capital (default 3%)

    def calculate_epc(self) -> float:
        """Calculates Equivalent Annual Cost (EPC) using annuity formula."""
        capex = (
                self.cost_per_unit
                + self.cost_per_unit * self.operational_cost_per_capacity * self.lifetime
                + (self.cost_offset / self.lifetime if self.cost_offset is not None else 0)  # ✅ Correct check
        )
        return economics.annuity(capex=capex, n=self.lifetime, wacc=self.wacc)

@dataclass
class CO2Components:
    per_capacity: float = 0.00  # kg CO2 per W installed
    per_flow: float = 0.00  # kg CO2 per Wh used
    offset_capacity: float = 0.00  # CO2 offset in W






