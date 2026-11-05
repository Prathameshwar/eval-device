from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pms_api.database.session import session_dependency

Session = Annotated[AsyncSession, Depends(session_dependency)]
