from enum import StrEnum


class Role(StrEnum):
    OPERATOR = 'operator'
    SUPERVISOR = 'supervisor'
    VIEWER = 'viewer'


class Slot(StrEnum):
    DAY = 'day'
    NIGHT = 'night'


class Profile(StrEnum):
    COOL = 'cool'
    BALANCED = 'balanced'
    WARM = 'warm'


class RoundState(StrEnum):
    SCHEDULED = 'scheduled'
    NEEDS_REPLAN = 'needs_replan'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


MINUTES = {Profile.COOL: 20, Profile.BALANCED: 35, Profile.WARM: 50}
