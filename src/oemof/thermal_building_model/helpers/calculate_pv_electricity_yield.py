from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
from pvlib.iotools import read_epw
from pvlib.location import Location
import pvlib
# Standort definieren
from pvlib.pvsystem import PVSystem
from pvlib.modelchain import ModelChain
from pvlib.iotools import read_epw
from pvlib.location import Location
import matplotlib.pyplot as plt
import pandas as pd
import pvlib


def simulate_pv_yield(pv_nominal_power_in_watt, epw_path, tilt=35, azimuth=180, show_plot=True):
    # EPW einlesen
    data, meta = read_epw(epw_path)

    # Standort aus EPW
    site = Location(meta['latitude'], meta['longitude'], tz=meta['TZ'])

    # DC-Leistung in W
    pdc0_watt = pv_nominal_power_in_watt

    # Einfaches PV-System
    system = PVSystem(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        module_parameters={'pdc0': pdc0_watt, 'gamma_pdc': -0.004},
        inverter_parameters={'pdc0': pdc0_watt},
        temperature_model_parameters=pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
    )

    # ModelChain aufbauen und starten
    mc = ModelChain(system, site, aoi_model='physical', spectral_model='no_loss')
    mc.run_model(data)


    return mc.results.ac

