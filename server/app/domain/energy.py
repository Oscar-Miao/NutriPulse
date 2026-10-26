from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyDay:
    target_kcal: float
    intake_kcal: float
    bmr_kcal: float
    tdee_kcal: float
    activity_kcal: float
    activity_adjustment_kcal: float
    total_expenditure_kcal: float
    net_kcal: float
    remaining_kcal: float


def calculate_day(target_kcal: float, intake_kcal: float, bmr_kcal: float,
                  tdee_kcal: float, activity_kcal: float) -> EnergyDay:
    # The activity factor in TDEE already includes ordinary daily movement.
    # V1 uses the higher of baseline TDEE and BMR plus recorded activity to
    # avoid adding the same exercise to both quantities.
    raw_expenditure = max(tdee_kcal, bmr_kcal + activity_kcal)
    activity_adjustment = max(0.0, raw_expenditure - tdee_kcal)
    expenditure = round(raw_expenditure, 1)
    return EnergyDay(
        target_kcal=target_kcal,
        intake_kcal=round(intake_kcal, 1),
        bmr_kcal=bmr_kcal,
        tdee_kcal=tdee_kcal,
        activity_kcal=round(activity_kcal, 1),
        activity_adjustment_kcal=round(activity_adjustment, 1),
        total_expenditure_kcal=expenditure,
        net_kcal=round(intake_kcal - raw_expenditure, 1),
        remaining_kcal=round(target_kcal - intake_kcal + activity_adjustment, 1),
    )
