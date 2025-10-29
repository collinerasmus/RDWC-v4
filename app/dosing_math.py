"""
Dosing Mathematics for RDWC-v4
Volume-based calculations for nutrient dosing
"""

def per_litre(value_ml_per_10l: float) -> float:
    """
    Convert ml per 10L to ml per 1L
    
    Args:
        value_ml_per_10l: Amount in ml per 10 litres
        
    Returns:
        Amount in ml per 1 litre
        
    Example:
        >>> per_litre(50)  # 50ml per 10L
        5.0                # = 5ml per 1L
    """
    return value_ml_per_10l / 10.0


def for_system(volume_l: float, value_ml_per_10l: float) -> float:
    """
    Calculate total dose for system volume
    
    Args:
        volume_l: System volume in litres
        value_ml_per_10l: Dose rate in ml per 10 litres
        
    Returns:
        Total dose in ml, rounded to 2 decimal places
        
    Example:
        >>> for_system(25.0, 40)  # 25L system, 40ml per 10L
        100.0                     # = 100ml total dose
    """
    return round(volume_l * per_litre(value_ml_per_10l), 2)


def dose_time_seconds(dose_ml: float, pump_rate_ml_per_sec: float) -> float:
    """
    Calculate pump runtime for desired dose
    
    Args:
        dose_ml: Dose amount in ml
        pump_rate_ml_per_sec: Pump flow rate in ml per second
        
    Returns:
        Runtime in seconds, rounded to 1 decimal place
        
    Example:
        >>> dose_time_seconds(100.0, 2.5)  # 100ml at 2.5ml/sec
        40.0                               # = 40 seconds
    """
    if pump_rate_ml_per_sec <= 0:
        raise ValueError("Pump rate must be greater than 0")
    
    return round(dose_ml / pump_rate_ml_per_sec, 1)


def schedule_dose(volume_l: float, nutrient_ml_per_10l: float, pump_rate_ml_per_sec: float = 2.0) -> dict:
    """
    Calculate complete dose schedule for a nutrient
    
    Args:
        volume_l: System volume in litres
        nutrient_ml_per_10l: Nutrient dose rate in ml per 10L
        pump_rate_ml_per_sec: Pump flow rate (default 2.0 ml/sec)
        
    Returns:
        Dict with dose_ml, runtime_sec, and rate info
        
    Example:
        >>> schedule_dose(25.0, 40)
        {
            'dose_ml': 100.0,
            'runtime_sec': 50.0,
            'rate_per_litre': 4.0,
            'pump_rate_ml_per_sec': 2.0
        }
    """
    dose_ml = for_system(volume_l, nutrient_ml_per_10l)
    runtime_sec = dose_time_seconds(dose_ml, pump_rate_ml_per_sec)
    
    return {
        'dose_ml': dose_ml,
        'runtime_sec': runtime_sec,
        'rate_per_litre': per_litre(nutrient_ml_per_10l),
        'pump_rate_ml_per_sec': pump_rate_ml_per_sec
    }


# Common nutrient schedules (ml per 10L)
NUTRIENT_SCHEDULES = {
    'seedling': {
        'micro': 10,
        'grow': 15,
        'bloom': 5
    },
    'vegetative': {
        'micro': 20,
        'grow': 30,
        'bloom': 10
    },
    'flowering': {
        'micro': 15,
        'grow': 20,
        'bloom': 25
    }
}


def get_schedule_doses(stage: str, volume_l: float) -> dict:
    """
    Get complete nutrient doses for a growth stage
    
    Args:
        stage: Growth stage ('seedling', 'vegetative', 'flowering')
        volume_l: System volume in litres
        
    Returns:
        Dict with doses for each nutrient type
        
    Example:
        >>> get_schedule_doses('vegetative', 25.0)
        {
            'micro': {'dose_ml': 50.0, 'runtime_sec': 25.0, ...},
            'grow': {'dose_ml': 75.0, 'runtime_sec': 37.5, ...},
            'bloom': {'dose_ml': 25.0, 'runtime_sec': 12.5, ...}
        }
    """
    if stage not in NUTRIENT_SCHEDULES:
        raise ValueError(f"Unknown stage '{stage}'. Available: {list(NUTRIENT_SCHEDULES.keys())}")
    
    schedule = NUTRIENT_SCHEDULES[stage]
    return {
        nutrient: schedule_dose(volume_l, rate_per_10l)
        for nutrient, rate_per_10l in schedule.items()
    }