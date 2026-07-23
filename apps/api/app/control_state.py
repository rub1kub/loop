from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ApplicationControl, ContractControl
from .ton import normalize_address


async def application_control(db: AsyncSession) -> ApplicationControl:
    control = await db.get(ApplicationControl, 1)
    if control is None:
        control = ApplicationControl(id=1)
        db.add(control)
        await db.flush()
    return control


async def ensure_mode_enabled(db: AsyncSession, mode: str) -> None:
    control = await application_control(db)
    enabled = control.bank_enabled if mode == "bank" else control.duel_enabled
    if control.maintenance_enabled or not enabled:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Новые операции временно приостановлены",
        )


def contract_control_key(mode: str, network: int, address: str) -> str:
    return f"{mode}:{network}:{normalize_address(address)}"


async def effective_contract_fee(
    db: AsyncSession,
    *,
    mode: str,
    network: int,
    address: str,
    fallback: int,
) -> int:
    state = await db.get(ContractControl, contract_control_key(mode, network, address))
    return state.fee_bps if state is not None else fallback
