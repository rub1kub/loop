import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ReferralCode


async def get_or_create_referral_code(
    db: AsyncSession,
    user_id: str,
) -> ReferralCode:
    existing = await db.scalar(
        select(ReferralCode).where(ReferralCode.owner_user_id == user_id)
    )
    if existing is not None:
        return existing

    for _ in range(3):
        referral = ReferralCode(
            code=secrets.token_urlsafe(9),
            owner_user_id=user_id,
        )
        db.add(referral)
        try:
            await db.commit()
            return referral
        except IntegrityError:
            await db.rollback()
            existing_after_conflict = await db.scalar(
                select(ReferralCode).where(ReferralCode.owner_user_id == user_id)
            )
            if existing_after_conflict is not None:
                return existing_after_conflict
    raise RuntimeError("could not create referral code")
