from dataclasses import dataclass
from oemof.tools import economics
from typing import Optional

@dataclass
class GeneralInvestmentEconomics:
    name: str
    observation_period: float = 20
    interest: float =  1.060
    price_change_factor: float = 1.027
    maintenance_price_change_factor: float = 1.0