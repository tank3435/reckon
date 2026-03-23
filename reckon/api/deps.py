from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.db import get_db

DBDep = Depends(get_db)
