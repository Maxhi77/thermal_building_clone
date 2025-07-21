from SALib.analyze import sobol
import pickle
from SALib.sample import saltelli
import seaborn as sns
import numpy as np
import matplotlib.pyplot as plt
import os
def map_tabula_class_to_year(tabula_class):
    return {
        1: 1850, 2: 1910, 3: 1930, 4: 1950, 5: 1960, 6: 1970,
        7: 1980, 8: 1990, 9: 2000, 10: 2005, 11: 2010, 12: 2020
    }.get(tabula_class, None)
def plot_sobol_indices(sobol_result, title, param_names):
    s1 = sobol_result['S1']
    st = sobol_result['ST']
    s1_conf = sobol_result['S1_conf']
    st_conf = sobol_result['ST_conf']

    x = np.arange(len(param_names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - width/2, s1, width, yerr=s1_conf, capsize=5, label='S1 (First-order)')
    ax.bar(x + width/2, st, width, yerr=st_conf, capsize=5, label='ST (Total-order)')

    ax.set_ylabel('Sobol index')
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(param_names, rotation=45)
    ax.legend()
    plt.tight_layout()
    plt.show()


# Initialize an empty dictionary to hold the data


# Define the directory where the .pkl files are stored
directory = r'C:\Users\hill_mx\PycharmeProjects\thermal_building_model\src\oemof\thermal_building_model\examples\a04_advanced_investment_optimization_sobol_analysis'  # Adjust the directory path if necessary

# Loop over the file numbers (2400, 2550, ..., 6143)
if False:
    data_structure = {}
    used_first_digits = set()
    for i in range(0, 6144):  # (0, 6144) non-inclusive at start
        file_name = f'results_sobol_{i}.pkl'
        if i in [2100,2850, 4050,4000,4100, 4500, 4950, 5100, 5550, 6000, 6143]:
            pass
        else:
            continue

        # Construct the full file path
        file_path = os.path.join(directory, file_name)

        # Check if the file exists before attempting to load it
        if os.path.exists(file_path):
            # Open the .pkl file and load its contents
            with open(file_path, 'rb') as f:
                data = pickle.load(f)
                print(i)
                for x in range(0, 6144):
                    for key in data:
                        if key[0] == x:
                            original = data[key]
                            filtered = {k: original[k] for k in ("co2", "totex", "peak") if k in original}
                            data_structure[x] = filtered
                            data_structure[x]["peak"] = max(data[key]["results"]["Electricity"]["flow_from_grid"])
                            break  # optional: nur den ersten passenden Key speichern
                print("saved: "+str(i))
    with open("results_sobol_final", "wb") as f:
        pickle.dump(data_structure, f)

with open("results_sobol_final", "rb") as f:
    data_dict = pickle.load(f)

    print("results saved")
    problem = {
        'num_vars': 4,
        'names': ['floor area', 'construction period', 'number of residents',
                  'household type'],
        'bounds': [
            [80, 360],      # Wohnfläche in m²
            [1, 11],        # tabula_year_class (1-11 Klassen)
            [1, 3],         # Bewohner
            [0, 2]  # Haushaltstyp: 0 = Senioren, 1 = Familie, 2 = Erwachsene
        ]
    }
    # Sampling (kleine Anzahl für Test)
    param_values = saltelli.sample(problem, int(128*8,), calc_second_order=False)
    idx_size = problem['names'].index('floor area')
    idx_year_class = problem['names'].index('construction period')
    idx_residents = problem['names'].index('number of residents')
    idx_household_type = problem['names'].index('household type')

    peak_list = []
    co2_list = []
    totex_list = []

    for key in data_dict:
        entry = data_dict[key]
        if "peak" in entry and "co2" in entry and "totex" in entry:
            peak_list.append(entry["peak"]/param_values[key][0])
            co2_list.append(entry["co2"]/param_values[key][0])
            totex_list.append(entry["totex"]/param_values[key][0])

    # Convert lists to numpy arrays
    co2_array = np.array(co2_list)
    totex_array = np.array(totex_list)
    peak_array = np.array(peak_list)

    sobol_co2 = sobol.analyze(problem, co2_array, calc_second_order=False)
    sobol_totex = sobol.analyze(problem, totex_array, calc_second_order=False)
    sobol_peak = sobol.analyze(problem, peak_array, calc_second_order=False)

    def plot_sobol_indices(sobol_result, title, problem_names):
        # Extract the first-order and total indices
        first_order = sobol_result['S1']  # First-order Sobol indices
        total_order = sobol_result['ST']  # Total-order Sobol indices

        # Plot first-order Sobol indices
        plt.figure(figsize=(10, 6))
        plt.bar(problem_names, first_order)
        plt.title(f'{title} - First-Order Sobol Indices')
        plt.xlabel('Parameters')
        plt.ylabel('First-Order Sobol Index')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()

        # Plot total-order Sobol indices
        plt.figure(figsize=(10, 6))
        plt.bar(problem_names, total_order)
        plt.title(f'{title} - Total Sobol Indices')
        plt.xlabel('Parameters')
        plt.ylabel('Total Sobol Index')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()


    import numpy as np
    import seaborn as sns
    import matplotlib.pyplot as plt


    def plot_sobol_heatmap_with_total_index(sobol_results, title, problem_names):
        # Combine the Sobol indices into a matrix (rows: outputs, columns: parameters)
        # Prepare the Sobol indices for both first-order and total for each output
        sobol_alternating_matrix = []
        total_index_matrix = []

        # Loop over the Sobol results and extract the first-order and total Sobol indices for each output
        for sobol_result in sobol_results:
            sobol_alternating_matrix.append(sobol_result['S1'])  # First-order Sobol indices
            sobol_alternating_matrix.append(sobol_result['ST'])  # Total Sobol indices

        # Convert the list to a numpy array (combined_matrix now stacks first and total Sobol indices vertically)
        combined_matrix = np.array(sobol_alternating_matrix)

        # Create a custom y-tick label that represents both first and total indices for each output
        output_names = ['CO₂ (First) \n/ floor area', 'CO₂ (Total) \n/ floor area',
                        'TOTEX (First) \n/ floor area', 'TOTEX (Total) \n/ floor area',
                        'PEAK (First) \n/ floor area', 'PEAK (Total) \n/ floor area']

        # Create a new figure for the plot
        fig, ax = plt.subplots(figsize=(12, 8))

        # Plotting the heatmap with color bar limits from 0 to 1
        sns.heatmap(combined_matrix, annot=True, cmap='coolwarm', xticklabels=problem_names, yticklabels=output_names,
                    cbar_kws={'label': 'Sobol Index', 'ticks': [0, 0.25, 0.5, 0.75, 1]},
                    center=0, ax=ax, vmin=0, vmax=1)  # Set the color bar to go from 0 to 1
        ax.set_title(f'{title} - Sobol Indices Heatmap')
        plt.yticks(rotation=0)
        # Return the figure object so it can be saved later
        return fig
    # Funktion für Sobol-Indizes mit Fehlerbalken
    import matplotlib.pyplot as plt


    def plot_sobol_indices_with_error_bars(sobol_result, title, problem_names):
        # Extract Sobol indices and their confidence intervals
        first_order = sobol_result['S1']
        total_order = sobol_result['ST']
        first_order_conf = sobol_result['S1_conf']
        total_order_conf = sobol_result['ST_conf']

        # Create a figure with 2 subplots (1 row, 2 columns)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))  # Set the figure size and subplots

        # Plot first-order Sobol indices with error bars in the first subplot
        ax1.bar(problem_names, first_order, yerr=first_order_conf, capsize=5, label='First-Order')
        ax1.set_title(f'{title} - First-Order Sobol Indices')
        ax1.set_xlabel('Parameters')
        ax1.set_ylabel('Sobol Index')
        ax1.tick_params(axis='x', rotation=45)
        ax1.legend()

        # Plot total-order Sobol indices with error bars in the second subplot
        ax2.bar(problem_names, total_order, yerr=total_order_conf, capsize=5, label='Total')
        ax2.set_title(f'{title} - Total Sobol Indices')
        ax2.set_xlabel('Parameters')
        ax2.set_ylabel('Sobol Index')
        ax2.tick_params(axis='x', rotation=45)
        ax2.legend()

        # Adjust layout to make it more readable
        plt.tight_layout()

        # Return the figure object for saving
        return fig


    #### 2. Speichern der Plot-Funktion:

    def save_plot_as_pdf(fig, plot_name, path_to_save):
        # Speichern des Plots im angegebenen Verzeichnis als PDF
        plot_path = os.path.join(path_to_save, plot_name + "_relative.pdf")
        fig.savefig(plot_path, format='pdf', dpi=300)  # Speichern des Plots mit 300 DPI
        plt.close(fig)  # Schließt den Plot, um den nächsten zu erzeugen


    path_to_save = r"C:\Users\hill_mx\Desktop\Präsentationen Berkeley\Ergebnisse Sobol"

    # Plot Sobol indices for each output (CO2, TOTEX, PEAK)
    fig_co2 = plot_sobol_indices_with_error_bars(sobol_co2, 'Sobol Sensitivity for CO₂', problem['names'])
    save_plot_as_pdf(fig_co2, "Sobol_Sensitivity_CO2", path_to_save)

    fig_totex = plot_sobol_indices_with_error_bars(sobol_totex, 'Sobol Sensitivity for TOTEX', problem['names'])
    save_plot_as_pdf(fig_totex, "Sobol_Sensitivity_TOTEX", path_to_save)

    fig_peak = plot_sobol_indices_with_error_bars(sobol_peak, 'Sobol Sensitivity for PEAK', problem['names'])
    save_plot_as_pdf(fig_peak, "Sobol_Sensitivity_PEAK", path_to_save)

    # Plot Sobol indices for CO2, TOTEX, and PEAK (including total indices)
    sobol_results = [sobol_co2, sobol_totex, sobol_peak]
    fig_sensitivity_analysis = plot_sobol_heatmap_with_total_index(sobol_results, 'Sobol Sensitivity Analysis',
                                                                   problem['names'])
    save_plot_as_pdf(fig_sensitivity_analysis, "Sobol_Sensitivity_Analysis", path_to_save)

