ALLOWED_CHANCES = {2_500, 5_000, 7_500}


def canonical_duel_terms(requested_stake_nano: int, chance_bps: int) -> tuple[int, int, int]:
    """Return exact stake, opponent stake and pool using quarter units.

    The user amount is rounded upward by at most two nanoGRAM. New product flows
    use 50/50; quarter units remain here for deterministic legacy-offer recovery.
    """

    if chance_bps not in ALLOWED_CHANCES:
        raise ValueError("unsupported chance")
    if requested_stake_nano <= 0:
        raise ValueError("stake must be positive")
    quarter = chance_bps // 2_500
    pool_unit = (requested_stake_nano + quarter - 1) // quarter
    stake = pool_unit * quarter
    opponent = pool_unit * (4 - quarter)
    return stake, opponent, pool_unit * 4


def payout_after_fee(total_pool_nano: int, fee_bps: int) -> int:
    return total_pool_nano - total_pool_nano * fee_bps // 10_000
