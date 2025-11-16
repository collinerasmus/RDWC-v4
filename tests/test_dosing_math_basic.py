import pytest
from app import dosing_math as dm

def test_per_litre_conversion():
    assert dm.per_litre(50) == 5.0
    assert dm.per_litre(0) == 0.0

def test_for_system_rounding():
    # 25L at 40ml/10L => 25 * 4 = 100.0
    assert dm.for_system(25.0, 40) == 100.0
    # Rounding to 2 decimals
    assert dm.for_system(12.345, 10) == round(12.345 * 1.0, 2)

def test_dose_time_seconds_validation():
    with pytest.raises(ValueError):
        dm.dose_time_seconds(10, 0)
    with pytest.raises(ValueError):
        dm.dose_time_seconds(10, -2)

def test_dose_time_seconds_calculation():
    assert dm.dose_time_seconds(100.0, 2.5) == 40.0
    # Rounding to 1 decimal
    assert dm.dose_time_seconds(10.0, 3.0) == round(10.0 / 3.0, 1)

def test_schedule_dose_structure():
    sched = dm.schedule_dose(25.0, 40, pump_rate_ml_per_sec=2.0)
    assert sched['dose_ml'] == 100.0
    assert sched['runtime_sec'] == 50.0
    assert sched['rate_per_litre'] == 4.0
    assert sched['pump_rate_ml_per_sec'] == 2.0

def test_get_schedule_doses_unknown_stage():
    with pytest.raises(ValueError):
        dm.get_schedule_doses('unknown', 25.0)

def test_get_schedule_doses_values():
    doses = dm.get_schedule_doses('seedling', 20.0)
    # micro: 10/10L =>1ml/L => 20ml total
    assert doses['micro']['dose_ml'] == 20.0
    assert 'runtime_sec' in doses['micro']
    # bloom: 5/10L =>0.5ml/L => 10ml total
    assert doses['bloom']['dose_ml'] == 10.0