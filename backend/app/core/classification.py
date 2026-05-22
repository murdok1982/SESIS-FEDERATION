# -*- coding: utf-8 -*-
from enum import Enum
from typing import List, Optional


class ClassificationLevel(str, Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"
    TOP_SECRET = "top_secret"


class TLPMarker(str, Enum):
    CLEAR = "TLP:CLEAR"
    GREEN = "TLP:GREEN"
    AMBER = "TLP:AMBER"
    AMBER_STRICT = "TLP:AMBER+STRICT"
    RED = "TLP:RED"


class STANAG4774(str, Enum):
    UNCLASSIFIED = "NATO UNCLASSIFIED"
    RESTRICTED = "NATO RESTRICTED"
    CONFIDENTIAL = "NATO CONFIDENTIAL"
    SECRET = "NATO SECRET"
    COSMIC_TS = "COSMIC TOP SECRET"


LEVEL_ORDER = {
    ClassificationLevel.PUBLIC: 0,
    ClassificationLevel.RESTRICTED: 1,
    ClassificationLevel.CONFIDENTIAL: 2,
    ClassificationLevel.SECRET: 3,
    ClassificationLevel.TOP_SECRET: 4,
}


def check_clearance(user_level: ClassificationLevel, required_level: ClassificationLevel) -> bool:
    return LEVEL_ORDER.get(user_level, 0) >= LEVEL_ORDER.get(required_level, 0)


def requires_clearance(required: ClassificationLevel):
    from fastapi import Depends, HTTPException, status
    from app.core.security import get_current_user

    async def clearance_checker(user: dict = Depends(get_current_user)):
        user_clearance = ClassificationLevel(user.get("clearance", "public"))
        if not check_clearance(user_clearance, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Clearance {required.value} required, have {user_clearance.value}",
            )
        return user

    return clearance_checker
