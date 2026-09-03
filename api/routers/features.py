"""Public read-only feature flags."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.database import get_db
from api.services import features_service

router = APIRouter(prefix="/v1", tags=["features"])


@router.get("/features")
def public_features(db: Session = Depends(get_db)):
    return features_service.get_public(db)
