"""I5-IMPL-W5-P01 — Iran directory search API.

Authenticated via X-Admin-Token when ADMIN_TOKEN is set (same I5 admin convention
as i5_admin). Router is allowlisted CREATE; main.py is NOT on W5-P01 allowlist —
mounting follows W2-P03 test-mount pattern until a later registration package.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas.i5_iran_directory import DirectorySearchResponse
from backend.app.services.i5 import iran_directory_service as ids

router = APIRouter(prefix="/i5/directory", tags=["i5-iran-directory"])


def _require_admin(request: Request) -> None:
    token = os.environ.get("ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="Not Found")
    header_token = (request.headers.get("X-Admin-Token") or "").strip()
    if header_token != token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _map_err(exc: ids.IranDirectoryServiceError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/meta", response_model=dict)
def directory_meta(_: None = Depends(_require_admin)) -> dict:
    return ids.directory_package_metadata()


@router.get("/doctors", response_model=DirectorySearchResponse)
def search_doctors(
    request: Request,
    name: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    specialty: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> DirectorySearchResponse:
    try:
        items = ids.search_doctors(
            db, name=name, city=city, province=province, specialty=specialty, limit=limit
        )
    except ids.IranDirectoryServiceError as exc:
        raise _map_err(exc) from exc
    return DirectorySearchResponse(
        package_id=ids.PACKAGE_ID,
        management_alias=ids.MANAGEMENT_ALIAS,
        entity_family=ids.ENTITY_DOCTOR,
        count=len(items),
        items=items,
        endorsement_disclaimer=ids.ENDORSEMENT_DISCLAIMER,
        is_clinical_knowledge=False,
        no_ir_to_ku=True,
    )


@router.get("/laboratories", response_model=DirectorySearchResponse)
def search_laboratories(
    request: Request,
    name: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> DirectorySearchResponse:
    try:
        items = ids.search_laboratories(
            db, name=name, city=city, province=province, service=service, limit=limit
        )
    except ids.IranDirectoryServiceError as exc:
        raise _map_err(exc) from exc
    return DirectorySearchResponse(
        package_id=ids.PACKAGE_ID,
        management_alias=ids.MANAGEMENT_ALIAS,
        entity_family=ids.ENTITY_LABORATORY,
        count=len(items),
        items=items,
        endorsement_disclaimer=ids.ENDORSEMENT_DISCLAIMER,
        is_clinical_knowledge=False,
        no_ir_to_ku=True,
    )


@router.get("/hospitals", response_model=DirectorySearchResponse)
def search_hospitals(
    request: Request,
    name: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    province: Optional[str] = Query(None),
    facility_type: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
) -> DirectorySearchResponse:
    try:
        items = ids.search_hospitals(
            db,
            name=name,
            city=city,
            province=province,
            facility_type=facility_type,
            limit=limit,
        )
    except ids.IranDirectoryServiceError as exc:
        raise _map_err(exc) from exc
    return DirectorySearchResponse(
        package_id=ids.PACKAGE_ID,
        management_alias=ids.MANAGEMENT_ALIAS,
        entity_family="HOSPITAL_OR_MEDICAL_CENTER",
        count=len(items),
        items=items,
        endorsement_disclaimer=ids.ENDORSEMENT_DISCLAIMER,
        is_clinical_knowledge=False,
        no_ir_to_ku=True,
    )
