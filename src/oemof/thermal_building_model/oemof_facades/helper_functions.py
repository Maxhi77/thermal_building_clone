from oemof import solph

def celsius_to_kelvin(arg):
    ZERO_CELSIUS = 273.15  # K
    """
    converts °C to K
    """
    return ZERO_CELSIUS + arg

def calculate_cop(
                  cop_for_setted_temp_interval,
                  lorenz_cop_temp_in,
                  lorenz_cop_temp_out,
                  temp_input,
                  temp_output):
    """
    :param temp_input: Higher Temperature of the source (in K)
    :param temp_output: Flow Temperature of the heating system (in K)
    :param cop_0_35: COP for B0/W35
    :return: Scaled COP for the given temperatures
    """
    # todo: add COP calculation for HP - see tutorial: https://oemof.github.io/heat-pump-tutorial/model/solph-simple.html#heat-pump
    # change temperature niveau for realistic values (f.E.0-20) and search cop for that
    # has to be added that there are additionately heat exchangers, for small tempreature differences cop is smaller for big differences
    # other possibility: add list of specfic cop for temp levels, than we dont need to interpolate
    cpf = cop_for_setted_temp_interval / lorenz_cop(
        temp_in=celsius_to_kelvin(lorenz_cop_temp_in), temp_out=celsius_to_kelvin(lorenz_cop_temp_out)
    )

    cop = cpf * lorenz_cop(temp_in=temp_input, temp_out=temp_output)
    if isinstance(cop, float):
        if cop < 0:
            cop = 0.001
    else:
        cop = cop.apply(lambda x: 0.5 if x < 1 else x)
        cop = cop.apply(lambda x: 300 if x > 300 else x)
    return cop

def lorenz_cop(temp_in, temp_out, one_value=False):
    """
    Calculate the theoretical COP of a infinite number
    of heat pump processes acc. to Lorenz 1895

    (Lorenz, H, 1895. Die Ermittlung der Grenzwerte der
    thermodynamischen Energieumwandlung. Zeitschrift für
    die gesammte Kälte-Industrie, 2(1-3, 6-12).)
    :param temp_in: Inlet Temperature (in K?)
    :param temp_out: Outlet Temperature (in K?)
    :return: Ideal COP
    """
    return temp_out / (temp_out - temp_in)
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
            print("________")
            print("input bus: " + str(i_bus))
            print("to bus: " +str(t_bus))
            t_bus.inputs[i_bus] = solph.Flow()

    # Connect target → output
    for _, o_bus in output_buses.items():
        for _, t_bus in target_buses.items():
            print("________")
            print("off bus: " + str(o_bus))
            print("from bus: " +str(t_bus))
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