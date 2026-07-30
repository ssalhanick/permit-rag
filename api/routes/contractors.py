"""
api/routes/contractors.py — Contractor profile and license management routes.
================================================================================
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user
from api.contractor_auth import require_contractor_profile
from api.schemas import (
    ContractorLicenseResponse,
    ContractorProfileResponse,
    CreateContractorLicenseRequest,
    CreateContractorProfileRequest,
    UpdateContractorLicenseRequest,
    UpdateContractorProfileRequest,
)
from db import client as db_client
from forms.ontology import validate_value

router = APIRouter(prefix="/contractors", tags=["contractors"])
CurrentUser = Annotated[dict, Depends(get_current_user)]
Profile = Annotated[dict, Depends(require_contractor_profile)]


def _validate_license_number(value: str) -> str:
    """Format-check a license number against forms.ontology's shared regex."""
    result = validate_value("contractor.license_number", value)
    if not result.ok:
        raise HTTPException(status_code=422, detail=f"Invalid license number: {result.error}")
    return result.normalized


@router.post("/profile", response_model=ContractorProfileResponse, status_code=201)
def create_profile(body: CreateContractorProfileRequest, current_user: CurrentUser) -> dict:
    """Create the caller's contractor profile (one per user)."""
    if db_client.contractor_profile_exists(current_user["user_id"]):
        raise HTTPException(status_code=409, detail="Contractor profile already exists.")
    profile = db_client.create_contractor_profile(
        user_id=current_user["user_id"],
        business_name=body.business_name,
        contact_name=body.contact_name,
        phone=body.phone,
        trades=body.trades,
        service_municipalities=body.service_municipalities,
        bio=body.bio,
        years_in_business=body.years_in_business,
    )
    return dict(profile)


@router.get("/profile", response_model=ContractorProfileResponse)
def get_profile(current_user: CurrentUser) -> dict:
    """Fetch the caller's own contractor profile."""
    profile = db_client.get_contractor_profile_by_user(current_user["user_id"])
    if not profile:
        raise HTTPException(status_code=404, detail="No contractor profile for this user.")
    return dict(profile)


@router.patch("/profile", response_model=ContractorProfileResponse)
def update_profile(body: UpdateContractorProfileRequest, current_user: CurrentUser) -> dict:
    """Update the caller's contractor profile."""
    updated = db_client.update_contractor_profile(
        current_user["user_id"],
        **body.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="No contractor profile for this user.")
    return dict(updated)


@router.post("/licenses", response_model=ContractorLicenseResponse, status_code=201)
def create_license(body: CreateContractorLicenseRequest, profile: Profile) -> dict:
    """Add a license/insurance record to the caller's contractor profile."""
    license_number = _validate_license_number(body.license_number)
    row = db_client.create_contractor_license(
        contractor_profile_id=profile["id"],
        trade=body.trade,
        license_number=license_number,
        expiration_date=body.expiration_date,
        issuing_authority=body.issuing_authority,
        insurance_provider=body.insurance_provider,
        insurance_policy_number=body.insurance_policy_number,
        insurance_coverage_amount=body.insurance_coverage_amount,
        insurance_expiration_date=body.insurance_expiration_date,
    )
    return dict(row)


@router.get("/licenses", response_model=list[ContractorLicenseResponse])
def list_licenses(profile: Profile) -> list[dict]:
    """List the caller's license/insurance records."""
    rows = db_client.list_contractor_licenses(profile["id"])
    return [dict(row) for row in rows]


def _require_own_license(license_id: UUID, profile: dict) -> dict:
    """404 if the license doesn't exist or belongs to a different contractor."""
    row = db_client.get_contractor_license(license_id)
    if not row or row["contractor_profile_id"] != profile["id"]:
        raise HTTPException(status_code=404, detail="License not found.")
    return row


@router.patch("/licenses/{license_id}", response_model=ContractorLicenseResponse)
def update_license(license_id: UUID, body: UpdateContractorLicenseRequest, profile: Profile) -> dict:
    """Update one of the caller's license/insurance records."""
    _require_own_license(license_id, profile)
    fields = body.model_dump(exclude_unset=True)
    if fields.get("license_number"):
        fields["license_number"] = _validate_license_number(fields["license_number"])
    updated = db_client.update_contractor_license(license_id, **fields)
    return dict(updated)


@router.delete("/licenses/{license_id}", status_code=200)
def delete_license(license_id: UUID, profile: Profile) -> dict:
    """Remove one of the caller's license/insurance records."""
    _require_own_license(license_id, profile)
    db_client.delete_contractor_license(license_id)
    return {"detail": "License removed."}
