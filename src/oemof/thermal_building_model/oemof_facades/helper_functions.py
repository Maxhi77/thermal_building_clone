from oemof import solph


def connect_buses(input=None, output=None, target=None):
    """
    Connects input and/or output buses to a target bus by setting solph.Flow().

    :param input: A single bus or a dictionary of buses to connect as inputs.
    :param output: A single bus or a dictionary of buses to connect as outputs.
    :param target: The target bus (single or dictionary), required.
    :raises ValueError: If no target is provided or if both input and output are missing.
    """
    if target is None:
        raise ValueError("Target bus must be defined.")

    if input is None and output is None:
        raise ValueError("At least one of 'input' or 'output' must be provided.")

    # Ensure all parameters are in dictionary format
    def ensure_dict(bus):
        return bus if isinstance(bus, dict) else {0: bus}  # Use key 0 for single bus

    input_buses = ensure_dict(input) if input else {}
    output_buses = ensure_dict(output) if output else {}
    target_buses = ensure_dict(target)  # Target must always be dict

    # Connect input → target
    for _, i_bus in input_buses.items():
        for _, t_bus in target_buses.items():
            print(i_bus)
            print(t_bus)
            t_bus.inputs[i_bus] = solph.Flow()

    # Connect target → output
    for _, o_bus in output_buses.items():
        for _, t_bus in target_buses.items():
            print(o_bus)
            print(t_bus)
            t_bus.outputs[o_bus] = solph.Flow()
    return


def flatten_components_list(components):
    flattened = []
    for item in components:
        if isinstance(item, dict):  # If it's a dictionary, add only the values (not the keys)
            flattened.extend(item.values())
        else:
            flattened.append(item)  # Otherwise, add it as is
    return flattened