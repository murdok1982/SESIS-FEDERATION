from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.api.intel.deps import get_db
from app.db.models.intel.geography import Country, CountryProfile
from app.db.models.intel.intelligence import IntelligenceItem, IntelligenceCategory
from app.db.models.intel.reports import DailyReport
from app.schemas.country import CountryDetail, CountryProfile as CountryProfileSchema
from app.schemas.intelligence import IntelligenceItem as IntelligenceItemSchema, IntelligenceListResponse
from app.schemas.report import ReportResponse

router = APIRouter()


async def _get_country_by_iso(iso_code: str, db: AsyncSession) -> Country:
    result = await db.execute(
        select(Country).where(Country.iso_code == iso_code.upper())
    )
    country = result.scalars().first()
    if not country:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Country not found")
    return country


@router.get("/{iso_code}", response_model=CountryDetail)
async def get_country(
    iso_code: str,
    db: AsyncSession = Depends(get_db),
) -> CountryDetail:
    country = await _get_country_by_iso(iso_code, db)

    profile_result = await db.execute(
        select(CountryProfile).where(CountryProfile.country_id == country.id)
    )
    profile = profile_result.scalars().first()
    profile_schema = CountryProfileSchema.model_validate(profile) if profile else None

    return CountryDetail(
        id=country.id,
        name=country.name,
        iso_code=country.iso_code,
        continent_id=country.continent_id,
        profile=profile_schema,
    )


@router.get("/{iso_code}/intelligence", response_model=IntelligenceListResponse)
async def get_country_intelligence(
    iso_code: str,
    category: str | None = Query(None, description="Filter by category name"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> IntelligenceListResponse:
    country = await _get_country_by_iso(iso_code, db)

    base_query = select(IntelligenceItem).where(IntelligenceItem.country_id == country.id)

    if category:
        cat_result = await db.execute(
            select(IntelligenceCategory).where(IntelligenceCategory.name == category)
        )
        cat = cat_result.scalars().first()
        if not cat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        base_query = base_query.where(IntelligenceItem.category_id == cat.id)

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar() or 0
    pages = max(1, (total + size - 1) // size)

    items_result = await db.execute(
        base_query.offset((page - 1) * size).limit(size)
    )
    items = items_result.scalars().all()

    return IntelligenceListResponse(
        items=[IntelligenceItemSchema.model_validate(i) for i in items],
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/{iso_code}/reports", response_model=list[ReportResponse])
async def get_country_reports(
    iso_code: str,
    db: AsyncSession = Depends(get_db),
) -> list[ReportResponse]:
    country = await _get_country_by_iso(iso_code, db)

    result = await db.execute(
        select(DailyReport)
        .where(DailyReport.country_id == country.id, DailyReport.published.is_(True))
        .order_by(DailyReport.report_date.desc())
    )
    reports = result.scalars().all()
    return [ReportResponse.model_validate(r) for r in reports]
