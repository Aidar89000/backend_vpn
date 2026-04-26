from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate, TransactionUpdate


async def create_transaction(
    db: AsyncSession,
    transaction: TransactionCreate
) -> Transaction:
    db_transaction = Transaction(**transaction.model_dump())
    db.add(db_transaction)
    await db.commit()
    await db.refresh(db_transaction)
    return db_transaction


async def get_transaction(
    db: AsyncSession,
    transaction_id: int
) -> Optional[Transaction]:
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    return result.scalar_one_or_none()


async def get_transactions_by_user(
    db: AsyncSession,
    user_id: int
) -> List[Transaction]:
    result = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id)
    )
    return list(result.scalars().all())


async def get_transaction_by_platega_id(
    db: AsyncSession,
    platega_transaction_id: str
) -> Optional[Transaction]:
    result = await db.execute(
        select(Transaction).where(Transaction.platega_transaction_id == platega_transaction_id)
    )
    return result.scalar_one_or_none()


async def update_transaction(
    db: AsyncSession,
    transaction_id: int,
    transaction_update: TransactionUpdate
) -> Optional[Transaction]:
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    db_transaction = result.scalar_one_or_none()
    if db_transaction:
        for key, value in transaction_update.model_dump(exclude_unset=True).items():
            setattr(db_transaction, key, value)
        await db.commit()
        await db.refresh(db_transaction)
    return db_transaction


async def update_transaction_by_platega_id(
    db: AsyncSession,
    platega_transaction_id: str,
    transaction_update: TransactionUpdate
) -> Optional[Transaction]:
    result = await db.execute(
        select(Transaction).where(Transaction.platega_transaction_id == platega_transaction_id)
    )
    db_transaction = result.scalar_one_or_none()
    if db_transaction:
        for key, value in transaction_update.model_dump(exclude_unset=True).items():
            setattr(db_transaction, key, value)
        await db.commit()
        await db.refresh(db_transaction)
    return db_transaction