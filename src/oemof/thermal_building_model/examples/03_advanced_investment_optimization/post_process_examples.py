import pickle
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
def plot_multi_strategy_with_reference_as_pareto():

    buildings = [
    #"DENILD1100004sZd", #363
    #"DENILD1100004u2T", # 366
    #"DENILD1100004uSx", #212
    "DENILD1100004rW0", # 249
    #"DENILD1100004vsl"
                 ] #usual_refurbishment
    #strategies = ["no_refurbishment","advanced_refurbishment","GEG_standard"]
    strategies = ["no_refurbishment","usual_refurbishment"]#,"advanced_refurbishment","GEG_standard"]
    building_dict = {}
    # Loop over each building in the list
    for building in buildings:
        for strategy in strategies:
            # Open the pickle file and load the content into the dictionary
            with open("results_"+building+"_"+strategy+"_.pkl", "rb") as f:
                building_dict[building,strategy] = pickle.load(f)
                for key in building_dict[building,strategy]:
                    if building_dict[building,strategy][key]["peak"] is not None:
                        building_dict[building,strategy][key]["peak"] = max(
                            building_dict[building,strategy][key]["results"]["Electricity"]["peak_into_grid"],
                            building_dict[building,strategy][key]["results"]["Electricity"]["peak_from_grid"])
                        building_dict[building, strategy][key]["heat_demand"] = building_dict[building, strategy][key]["results"][building]["flow_into"].sum()/1000
    reference_building = {}
    for strategy in strategies:
        # Open the pickle file and load the content into the dictionary
        with open("results_representativeSFH" + "_" + strategy + "_.pkl", "rb") as f:
            reference_building[strategy] = pickle.load(f)
            for key in reference_building[strategy]:
                if reference_building[strategy][key]["peak"] is not None:
                    reference_building[strategy][key]["peak"] = max(
                        reference_building[strategy][key]["results"]["Electricity"]["peak_into_grid"],
                        reference_building[strategy][key]["results"]["Electricity"]["peak_from_grid"])
                    reference_building[strategy][key]["heat_demand"] = \
                    reference_building[strategy][key]["results"]["representativeSFH"]["flow_into"].sum() / 1000

    from collections import defaultdict

    # Fields to average
    fields = ['co2', 'totex', 'peak',"heat_demand"]

    # Nested dict to collect values: { key -> { field -> [values] } }
    grouped_values = defaultdict(lambda: defaultdict(list))

    # Loop over buildings and collect values
    for building, inner_dict in building_dict.items():
        for key, metrics in inner_dict.items():
            for field in fields:
                value = metrics.get(field)
                if value is not None:
                    grouped_values[key][field].append(value)

    # Compute averages for each key and field
    averages = {}

    for key, field_dict in grouped_values.items():
        averages[key] = {
            field: sum(vals) / len(vals)
            for field, vals in field_dict.items()
            if vals  # make sure list is not empty
        }

    # Optional: print results nicely
    for key, metrics in averages.items():
        print(f"\nKey: {key}")
        for field, avg in metrics.items():
            print(f"  {field}: {avg:.2f}")

    # Extract average values
    avg_co2, avg_totex, avg_peak, avg_heat_demand = [], [], [], []
    for key, val in averages.items():
        if all(k in val for k in ['co2', 'totex', 'peak',"heat_demand" ]):
            avg_co2.append(val['co2'])
            avg_totex.append(val['totex'])
            avg_peak.append(val['peak'])
            avg_heat_demand.append(val['heat_demand'])
    # Extract reference building values
    ref_co2, ref_totex, ref_peak, ref_heat_demand = [], [], [], []
    for strategy in strategies:
        for key, val in reference_building[strategy].items():
            if all(k in val for k in ['co2', 'totex', 'peak',"heat_demand"]):
                ref_co2.append(val['co2'])
                ref_totex.append(val['totex'])
                ref_peak.append(val['peak'])
                ref_heat_demand.append(val['heat_demand'])
    # Plot
    plt.figure(figsize=(10, 6))

    # Average points
    sc1 = plt.scatter(avg_co2, avg_totex, c=avg_heat_demand, cmap='Blues', s=150, edgecolor='darkred',
                      label='Average values')

    # Reference points
    sc2 = plt.scatter(ref_co2, ref_totex, c=ref_heat_demand, cmap='Blues', s=150, marker='^', edgecolor='darkred',
                      label='Reference values')

    # Colorbar
    cbar = plt.colorbar(sc1)
    cbar.set_label('Annual Heat Demand of the Building im kWh')

    # Labels & style
    plt.xlabel('Annual CO₂ Emissions in kg')
    plt.ylabel('Annual Total Expenditure (Totex)')
    plt.title('Average vs Representative Building Metrics 1 Building')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def plot_only_1_strategy_with_reference_as_pareto():
    buildings = [
        "results_DENILD1100004rW0_no_refurbishment_.pkl",
    "results_DENILD1100004sZd_no_refurbishment_.pkl",
    "results_DENILD1100004u2T_no_refurbishment_.pkl",
    "results_DENILD1100004uSx_no_refurbishment_.pkl",
    #"results_DENILD1100004vsl_no_refurbishment_.pkl",
                 ]
    building_dict = {}
    # Loop over each building in the list
    for building in buildings:
        # Open the pickle file and load the content into the dictionary
        with open(building, "rb") as f:
            building_dict[building] = pickle.load(f)
            for key in building_dict[building]:
                if building_dict[building][key]["peak"] is not None:
                    building_dict[building][key]["peak"] = max(
                        building_dict[building][key]["results"]["Electricity"]["peak_into_grid"],
                        building_dict[building][key]["results"]["Electricity"]["peak_from_grid"])

    from collections import defaultdict

    # Fields to average
    fields = ['co2', 'totex', 'peak']

    # Nested dict to collect values: { key -> { field -> [values] } }
    grouped_values = defaultdict(lambda: defaultdict(list))

    # Loop over buildings and collect values
    for building, inner_dict in building_dict.items():
        for key, metrics in inner_dict.items():
            for field in fields:
                value = metrics.get(field)
                if value is not None:
                    grouped_values[key][field].append(value)

    # Compute averages for each key and field
    averages = {}

    for key, field_dict in grouped_values.items():
        averages[key] = {
            field: sum(vals) / len(vals)
            for field, vals in field_dict.items()
            if vals  # make sure list is not empty
        }

    # Optional: print results nicely
    for key, metrics in averages.items():
        print(f"\nKey: {key}")
        for field, avg in metrics.items():
            print(f"  {field}: {avg:.2f}")

    with open("results_representativeSFH_no_refurbishment_.pkl", "rb") as f:
        reference_building = pickle.load(f)
        for key in reference_building:
            if reference_building[key]["peak"] is not None:
                reference_building[key]["peak"] = max(
                    reference_building[key]["results"]["Electricity"]["peak_into_grid"],
                    reference_building[key]["results"]["Electricity"]["peak_from_grid"])

    # Extract average values
    avg_co2, avg_totex, avg_peak = [], [], []
    for key, val in averages.items():
        if all(k in val for k in ['co2', 'totex', 'peak']):
            avg_co2.append(val['co2'])
            avg_totex.append(val['totex'])
            avg_peak.append(val['peak'])

    # Extract reference building values
    ref_co2, ref_totex, ref_peak = [], [], []
    for key, val in reference_building.items():
        if all(k in val for k in ['co2', 'totex', 'peak']):
            ref_co2.append(val['co2'])
            ref_totex.append(val['totex'])
            ref_peak.append(val['peak'])


    # Plot
    plt.figure(figsize=(10, 6))

    # Average points
    sc1 = plt.scatter(avg_co2, avg_totex, c=avg_peak, cmap='Blues', s=150, edgecolor='darkred', label='Average values')

    # Reference points
    sc2 = plt.scatter(ref_co2, ref_totex, c=ref_peak, cmap='Blues', s=150, marker='^', edgecolor='darkred', label='Reference values')

    # Colorbar
    cbar = plt.colorbar(sc1)
    cbar.set_label('Peak Demand')

    # Labels & style
    plt.xlabel('Annual CO₂ Emissions in kg')
    plt.ylabel('Annual Total Expenditure (Totex)')
    plt.title('Average vs Reference Building Metrics for No Refurbishment')
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.show()


def two_dimension_pareto_plotter():
    plt.figure(figsize=(8, 6))

    # Scatter plot for average buildings, color by peak
    scatter_avg = plt.scatter(totex_avg, co2_avg, c=peak_avg, cmap='viridis', label='Average Buildings', marker='o')

    # Scatter plot for other buildings, color by peak
    scatter_other = plt.scatter(totex_other, co2_other, c=peak_other, cmap='plasma', label='Other Buildings', marker='^')

    # Labels for axes
    plt.xlabel('Totex')
    plt.ylabel('CO2')

    # Title and legend
    plt.title('2D Scatter Plot of Totex and CO2 with Peak Indicated by Color')
    plt.legend()

    # Color bar for peak values
    plt.colorbar(scatter_avg, label='Peak')

    # Show the plot
    plt.show()



def calculate_average_values():
    from collections import defaultdict

    # Fields to average
    fields = ['co2', 'totex', 'peak']

    # Nested dict to collect values: { key -> { field -> [values] } }
    grouped_values = defaultdict(lambda: defaultdict(list))

    # Loop over buildings and collect values
    for building, inner_dict in building_dict.items():
        for key, metrics in inner_dict.items():
            for field in fields:
                value = metrics.get(field)
                if value is not None:
                    grouped_values[key][field].append(value)

    # Compute averages for each key and field
    averages = {}

    for key, field_dict in grouped_values.items():
        averages[key] = {
            field: sum(vals) / len(vals)
            for field, vals in field_dict.items()
            if vals  # make sure list is not empty
        }

    # Optional: print results nicely
    for key, metrics in averages.items():
        print(f"\nKey: {key}")
        for field, avg in metrics.items():
            print(f"  {field}: {avg:.2f}")
with open("results_processed_bds_in_DENI03403000SEC5658/results_processed_bds_in_DENI03403000SEC5658_no_refurbishment_no_EV_con.pkl", "rb") as f:
    reference_building = pickle.load(f)
plot_multi_strategy_with_reference_as_pareto()
