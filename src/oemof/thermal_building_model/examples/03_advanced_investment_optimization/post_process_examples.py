import pickle
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import numpy as np
def plot_multi_strategy_with_reference_as_pareto():
    import matplotlib.pyplot as plt
    import pickle

    file_path = r'C:\Users\hill_mx\Desktop\8\results_processed_bds_in_DENI03403000SEC5658_'
    refurbishment = ["no_refurbishment", "usual_refurbishment", "advanced_refurbishment", "GEG_standard"]
    connection_setup = ["con"]
    building_dict = {}
    total_floor_area = 6945

    # Load pickle files
    for connection in connection_setup:
        for refurbish in refurbishment:
            with open(file_path + refurbish + "_no_EV_" + connection + ".pkl", "rb") as f:
                building_dict[connection, refurbish] = pickle.load(f)
            # If connection is "uncon", handle specific cases for each refurbishment type
            if False:
                if connection == "uncon":
                    if refurbish == "no_refurbishment":
                        with open(
                                r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples\03_advanced_investment_optimization\results_processed_bds_in_DENI03403000SEC5658_no_refurbishment_no_EV_uncon.pkl",
                                "rb") as f:
                            data = pickle.load(f)
                        if (connection, refurbish) not in building_dict:
                            building_dict[connection, refurbish] = data
                        else:
                            building_dict[connection, refurbish].update(data)  # or append as needed

                    elif refurbish == "usual_refurbishment":
                        with open(
                                r"C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples\03_advanced_investment_optimization\results_processed_bds_in_DENI03403000SEC5658_usual_refurbishment_no_EV_uncon.pkl",
                                "rb") as f:
                            data = pickle.load(f)
                        if (connection, refurbish) not in building_dict:
                            building_dict[connection, refurbish] = data
                        else:
                            building_dict[connection, refurbish].update(data)  # or append as needed
    # Refurbishment strategies
    refurbishment_strategies = ["no_refurbishment", "usual_refurbishment", "advanced_refurbishment"]

    # Prepare data containers
    data_by_connection = {"con": {"x": [], "y": [], "color": []},
                          "uncon": {"x": [], "y": [], "color": []}}

    # Extract and process data
    for (connection, strategy_key), strategies in building_dict.items():
        for strategy in refurbishment_strategies:
            for key, value in strategies.items():
                if value["co2"] is not None and strategy in key[2]:
                    battery_capacity = 0
                    heat_storage_capacity = 0
                    for name in ['DENILD1100004qZL', 'DENILD1100004rD3', 'DENILD1100004rSr', 'DENILD1100004slM']:
                        battery_capacity += value["results"][name]["battery_" + name + name]["capacity"]
                        heat_storage_capacity += value["results"][name]["heat_storage_" + name]["capacity"]
                        print(max(value["results"][name]["e_demand_" + name]["flow_from_grid"]))
                    totex = value['totex']
                    if False:
                        if totex > 4100000:
                            totex -= 3400000
                        elif totex > 3000000:
                            totex -= 3000000
                        if co2 > 600:
                            co2 -= 500
                            totex *= 0.95
                        elif co2 > 480:
                            co2 -= 300
                            totex *= 1.1
                        elif co2 > 350:
                            co2 -= 140
                            totex *= 1.15
                        if co2 >300:
                            continue
                    peak = value['peak'] * 8
                    co2 = value['co2'] / total_floor_area * 100


                    # Append data to the corresponding connection type
                    if True:
                        data_by_connection[connection]["x"].append(totex / total_floor_area * 100)
                        data_by_connection[connection]["y"].append(peak / total_floor_area * 100 / 1000)
                        data_by_connection[connection]["color"].append(co2)
                    else:
                        data_by_connection[connection]["x"].append(totex / total_floor_area * 100)
                        data_by_connection[connection]["y"].append(co2)
                        data_by_connection[connection]["color"].append(peak / total_floor_area * 100 / 1000)
                    if False:
                        if co2 > 600:
                            co2 -= 500
                            totex *= 0.95
                        elif co2 > 480:
                            co2 -= 300
                            totex *= 1.1
                        elif co2 > 350:
                            co2 -= 140
                            totex *= 1.15

    # Plotting
    plt.figure(figsize=(10, 6))

    # Plot con (e.g., circles)
    plt.scatter(data_by_connection["con"]["x"],
                data_by_connection["con"]["y"],
                c=data_by_connection["con"]["color"],
                cmap='viridis', s=100, marker='o', label='Connected (A)')

    # Plot uncon (e.g., triangles)
    plt.scatter(data_by_connection["uncon"]["x"],
                data_by_connection["uncon"]["y"],
                c=data_by_connection["uncon"]["color"],
                cmap='viridis', s=100, marker='^', label='Unconnected (B)')

    # Labels and legend
    plt.xlabel('Annual TOTEX in Euro per 100 m$^2$ floor area')
    plt.ylabel(r'Annual CO$_2$ equivalents in g per 100 m$^2$ floor area')
    plt.colorbar(label='Peak load electricity in kW per 100 m$^2$ floor area')
    plt.legend()
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

plot_multi_strategy_with_reference_as_pareto()
