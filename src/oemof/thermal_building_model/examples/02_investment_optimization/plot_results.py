import seaborn as sns
import matplotlib
from matplotlib.font_manager import FontProperties
import matplotlib.pyplot as plt

handles = []  # to collect legend handles
labels = []  # to collect legend labels

def plot_stacked_bars(refurbishment_status, results_dict, cost_refurbishment):

    # Define font properties
    matplotlib.rcParams["font.size"] = "12"
    font = FontProperties()
    font.set_family("Times New Roman")
    font.set_size(12)
    fig, ax = plt.subplots(figsize=(15.99773 / 2.54, 8 / 2.54))
    handle = []

    # Specify the number of unique colors you want
    num_colors = 20  # Adjust this as needed
    # Generate a color palette with the specified number of colors
    custom_colors = sns.color_palette("husl", n_colors=num_colors)

    for status in reversed(list(refurbishment_status)):
        total_cost = 0
        color_counter = 0
        for name, cost in results_dict[status]["annual_cost_components"].items():
            handle.append(
                ax.barh(
                    status,
                    cost,
                    left=total_cost,
                    label="CAPEX+OPEX of " + str(name),
                    color=custom_colors[color_counter],
                )
            )
            total_cost = total_cost + cost
            color_counter = color_counter + 1
        delta_grid_elect = (
            results_dict[status]["annual_cost_flows"]["elect_from_grid"]
            - results_dict[status]["annual_cost_flows"]["elect_into_grid"]
        )
        handle.append(
            ax.barh(
                status,
                delta_grid_elect,
                left=total_cost,
                label="Net of electricity costs",
                color=custom_colors[color_counter],
            )
        )
        total_cost = delta_grid_elect + total_cost
        color_counter = color_counter + 1
        handle.append(
            ax.barh(
                status,
                results_dict[status]["annual_cost_flows"]["gas_from_grid"],
                left=total_cost,
                label="Gas costs",
                color=custom_colors[color_counter],
            )
        )
        total_cost = (
            total_cost +
            results_dict[status]["annual_cost_flows"]["gas_from_grid"]
        )
        color_counter = color_counter + 1
        handle.append(
            ax.barh(
                status,
                cost_refurbishment[status],
                left=total_cost,
                label="CAPEX of Refurbishment",
                color=custom_colors[color_counter],
            )
        )

        # Collect handles and labels for the legend
    # Customize the plot
    ax.legend(handles, labels, prop=font)
    ax.set_xlabel("Annual Costs in Euro", fontproperties=font)
    ax.tick_params(axis="both", labelsize=12)
    # Set font style for x-axis tick labels (refurbishment status)
    ax.set_xticklabels(ax.get_xticklabels(), fontproperties=font)
    ax.set_yticklabels(ax.get_yticklabels(), fontproperties=font)

    # Set font style for y-axis tick labels
    ax.tick_params(axis="y", labelsize=12)
    # Shrink current axis by 20%
    plt.tight_layout(pad=1.08)
    # Save the figure in PDF format with specified dpi
    plt.savefig("figure.svg", format="svg", dpi=1000, bbox_inches="tight")
    plt.rcParams.update({"font.size": 12})
    # Show the plot (optional)
    plt.show()
