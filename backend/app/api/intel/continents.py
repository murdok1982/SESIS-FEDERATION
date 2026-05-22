import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.api.intel.deps import get_db
from app.db.models.intel.geography import Continent, Country, CountryProfile
from app.schemas.continent import ContinentResponse, ContinentDetail
from app.schemas.country import CountryDetail, CountryProfile as CountryProfileSchema

router = APIRouter()


@router.get("", response_model=list[ContinentResponse])
async def list_continents(db: AsyncSession = Depends(get_db)) -> list[ContinentResponse]:
    result = await db.execute(select(Continent))
    continents = result.scalars().all()

    # Fetch country counts in one query
    counts_result = await db.execute(
        select(Country.continent_id, func.count(Country.id).label("cnt"))
        .group_by(Country.continent_id)
    )
    counts = {row.continent_id: row.cnt for row in counts_result}

    return [
        ContinentResponse(
            id=c.id,
            name=c.name,
            code=c.code,
            country_count=counts.get(c.id, 0),
        )
        for c in continents
    ]


@router.get("/{continent_id}", response_model=ContinentDetail)
async def get_continent(
    continent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ContinentDetail:
    result = await db.execute(select(Continent).where(Continent.id == continent_id))
    continent = result.scalars().first()
    if not continent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Continent not found")

    count_result = await db.execute(
        select(func.count(Country.id)).where(Country.continent_id == continent_id)
    )
    country_count = count_result.scalar() or 0

    return ContinentDetail(
        id=continent.id,
        name=continent.name,
        code=continent.code,
        country_count=country_count,
    )


@router.get("/{continent_id}/countries", response_model=list[CountryDetail])
async def list_continent_countries(
    continent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[CountryDetail]:
    continent_result = await db.execute(
        select(Continent).where(Continent.id == continent_id)
    )
    if not continent_result.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Continent not found")

    result = await db.execute(
        select(Country).where(Country.continent_id == continent_id)
    )
    countries = result.scalars().all()

    output = []
    for country in countries:
        profile_result = await db.execute(
            select(CountryProfile).where(CountryProfile.country_id == country.id)
        )
        profile = profile_result.scalars().first()
        profile_schema = (
            CountryProfileSchema.model_validate(profile) if profile else None
        )
        output.append(
            CountryDetail(
                id=country.id,
                name=country.name,
                iso_code=country.iso_code,
                continent_id=country.continent_id,
                profile=profile_schema,
            )
        )
    return output
