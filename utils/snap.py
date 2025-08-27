import math

def snap_down(x, tick):
    return math.floor(x / tick) * tick

def snap_up(x, tick):
    return math.ceil(x / tick) * tick

def round_to_tick(x, tick):
    """Round to tick precision to avoid floating point errors before snapping"""
    # For 0.01 tick, round to 2 decimal places
    if tick == 0.01:
        return round(x, 2)
    elif tick == 0.001:
        return round(x, 3)
    elif tick == 0.0001:
        return round(x, 4)
    else:
        # General case: determine decimal places from tick size
        decimal_places = len(str(tick).rstrip('0').split('.')[-1]) if '.' in str(tick) else 0
        return round(x, decimal_places)

def safe_snap_up(x, tick):
    snapped = snap_up(x, tick)
    return round_to_tick(snapped, tick)

def safe_snap_down(x, tick):
    snapped = snap_down(x, tick)
    return round_to_tick(snapped, tick)
