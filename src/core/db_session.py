# from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
# from sqlalchemy.orm import declarative_base
# from src.core.config import get_settings

# settings = get_settings()

# DB_URL = settings.DB_URL

# engine = create_async_engine(DB_URL, echo=True)
# SessionLocal = async_sessionmaker(
#     bind=engine,
#     class_=AsyncSession,
#     expire_on_commit=False,
# )

# Base = declarative_base()


# async def get_db():
#     """
#     Dependency to get the database session.
#     """
#     async with SessionLocal() as db:
#         try:
#             yield db
#         finally:
#             await db.close()
