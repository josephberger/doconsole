import questionary


def select(message, choices):
    """choices: list of (label, value) tuples. Returns the chosen value, or None if cancelled."""
    q_choices = [questionary.Choice(title=label, value=value) for label, value in choices]
    return questionary.select(message, choices=q_choices).ask()
