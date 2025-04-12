import pickle as pickle
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt
import pandas as pd
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import numpy as np
buildings = ["DENILD1100004rW0.pkl",
"DENILD1100004smj.pkl",
"DENILD1100004sZd.pkl",
"DENILD1100004u2T.pkl",
"DENILD1100004uSx.pkl",
#"DENILD1100004vsl.pkl",
             ]
building_dict = {}
# Loop over each building in the list
for building in buildings:
    # Create the full file path
    file_path = r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\input\bds_in_DENI03403000SEC5291\\" + building

    # Open the pickle file and load the content into the dictionary
    with open(file_path, "rb") as f:
        building_dict[building] = pickle.load(f)
electricity_demand_buildings = {}
warm_water_demand_buildings = {}
for building in building_dict:
    electricity_demand =  building_dict[building]["Electricity_HH1"] + building_dict[building]["Electricity_House"]
    warm_water_demand = building_dict[building]["Warm Water_HH1"]
    # Optional: Falls gewünscht, konvertiere diese Werte in Pandas Series für jedes Gebäude (z. B. über die Zeit)
    electricity_demand_buildings[building] = electricity_demand
    warm_water_demand_buildings[building] = warm_water_demand
with open(r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\input\bds_in_DENI03403000SEC5291\representativeSFH.pkl", "rb") as f:
    representative_building = pickle.load(f)
    electricity_demand_representative = representative_building["Electricity_HH1"] + representative_building["Electricity_House"]
    warm_water_demand_representative = representative_building["Warm Water_HH1"]
    # Ensure the representative series is also in 2020
    electricity_demand_representative.index = electricity_demand_representative.index.map(lambda dt: dt.replace(year=2021))
    warm_water_demand_representative.index = warm_water_demand_representative.index.map(lambda dt: dt.replace(year=2021))

def plot_elect_demand ():
    # Set up colormap
    num_series = len(electricity_demand_buildings)
    colors = cm.Blues(mcolors.Normalize()(range(num_series)))

    # Start the plot
    plt.figure(figsize=(15, 6))
    if False:
        # Plot each building's series, modifying the year in-place
        for i, (name, series) in enumerate(electricity_demand_buildings.items()):
            shifted_index = series.index.map(lambda dt: dt.replace(year=2020))
            plt.plot(shifted_index, series.values, color=colors[i], label=name, linewidth=0.8)
    if True:
        # Step 1: Align all series to 2020 and combine into a DataFrame
        aligned_series = {}

        for name, series in electricity_demand_buildings.items():
            shifted_index = series.index.map(lambda dt: dt.replace(year=2021))
            aligned_series[name] = pd.Series(series.values, index=shifted_index)
        # Combine into a DataFrame
        df_all = pd.DataFrame(aligned_series)
        average_demand = df_all.mean(axis=1)
        print(sum(average_demand))
        print(sum(electricity_demand_representative))
        plt.plot(average_demand.index, average_demand.values, color='blue', label='Average Demand', linewidth=0.8)

        # Step 2: Calculate the average across all buildings
        average_demand = df_all.mean(axis=1)
    # Plot the representative series in green
    plt.plot(
        electricity_demand_representative,
        color='green',
        label='Representative',
        linewidth=0.8
    )

    plt.title('Electricity Demand')
    plt.xlabel('Time')
    plt.ylabel('Electricity in kW')
    plt.legend(loc='upper right', fontsize='small')
    plt.tight_layout()
    plt.show()

def plot_warm_water_demand ():
    # Set up colormap
    num_series = len(warm_water_demand_buildings)
    colors = cm.Blues(mcolors.Normalize()(range(num_series)))

    # Start the plot
    plt.figure(figsize=(15, 6))
    if False:
        # Plot each building's series, modifying the year in-place
        for i, (name, series) in enumerate(warm_water_demand_buildings.items()):
            shifted_index = series.index.map(lambda dt: dt.replace(year=2020))
            plt.plot(shifted_index, series.values, color=colors[i], label=name, linewidth=0.8)
    if True:
        # Step 1: Align all series to 2020 and combine into a DataFrame
        aligned_series = {}

        for name, series in electricity_demand_buildings.items():
            shifted_index = series.index.map(lambda dt: dt.replace(year=2020))
            aligned_series[name] = pd.Series(series.values, index=shifted_index)
        # Combine into a DataFrame
        df_all = pd.DataFrame(aligned_series)
        average_demand = df_all.mean(axis=1)
        print(sum(average_demand))
        print(sum(warm_water_demand_representative))
        plt.plot(average_demand.index, average_demand.values, color='blue', label='Average Demand', linewidth=0.8)

        # Step 2: Calculate the average across all buildings
        average_demand = df_all.mean(axis=1)
    # Plot the representative series in green
    plt.plot(
        electricity_demand_representative,
        color='green',
        label='Representative',
        linewidth=0.8
    )

    plt.title('Warm Water Demand')
    plt.xlabel('Time')
    plt.ylabel('Warm Water Demand in l')
    plt.legend(loc='upper right', fontsize='small')
    plt.tight_layout()
    plt.show()
plot_warm_water_demand ()
#plot_elect_demand ()