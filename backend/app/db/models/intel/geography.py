from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from sqlalchemy.orm import declarative_base
Base = declarative_base()
from sqlalchemy.orm import relationship

class Continent(Base):
    __tablename__ = "continents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True, nullable=False)
    code = Column(String, unique=True, nullable=False)
    
    countries = relationship("Country", back_populates="continent")

class Country(Base):
    __tablename__ = "countries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    continent_id = Column(UUID(as_uuid=True), ForeignKey("continents.id"))
    name = Column(String, unique=True, index=True, nullable=False)
    iso_code = Column(String, unique=True, nullable=False)
    
    continent = relationship("Continent", back_populates="countries")
    profile = relationship("CountryProfile", back_populates="country", uselist=False)

class CountryProfile(Base):
    __tablename__ = "country_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    country_id = Column(UUID(as_uuid=True), ForeignKey("countries.id"), unique=True)
    overall_risk_score = Column(String, nullable=True) # e.g. Low, Medium, High, Critical
    metadata_json = Column(String, nullable=True) # JSON containing demographics, leadership 
    
    country = relationship("Country", back_populates="profile")
