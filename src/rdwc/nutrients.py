EHG_SCHEDULE = {
    1: {"grow": 7, "micro": 7, "bloom": 7},
    2: {"grow": 10, "micro": 10, "bloom": 10},
    3: {"grow": 12, "micro": 10, "bloom": 15},
    4: {"grow": 10, "micro": 10, "bloom": 20},
    5: {"grow": 8,  "micro": 10, "bloom": 20},
    6: {"grow": 6,  "micro": 8,  "bloom": 18},
    7: {"grow": 4,  "micro": 6,  "bloom": 16},
    8: {"grow": 0,  "micro": 4,  "bloom": 14}
}

def get_week_schedule(week: int):
    week = max(1, min(week, max(EHG_SCHEDULE.keys())))
    return EHG_SCHEDULE[week]