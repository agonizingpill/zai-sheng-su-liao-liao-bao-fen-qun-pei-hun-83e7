"""Rapid-tester PVC calibration: paired reference readings, fitted versions and their dependency links."""
from sqlalchemy import String,Numeric,ForeignKey,UniqueConstraint,CheckConstraint,JSON,Float
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
class ReferenceSample(Base):
    __tablename__='reference_samples'
    __table_args__=(CheckConstraint('instrument_ppm >= 0 AND lab_ppm >= 0'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(60),unique=True)
    lot_id:Mapped[int]=mapped_column(ForeignKey('supplier_lots.id'))
    instrument_ppm:Mapped[float]=mapped_column(Numeric(9,3))
    lab_ppm:Mapped[float]=mapped_column(Numeric(9,3))
    state:Mapped[str]=mapped_column(String(20),default='active')
    created_by:Mapped[str]=mapped_column(String(120),default='')
    created_at:Mapped[str]=mapped_column(String(40),default='')
    revoked_by:Mapped[str]=mapped_column(String(120),default='')
    revoked_at:Mapped[str]=mapped_column(String(40),default='')
    revoke_reason:Mapped[str]=mapped_column(String(600),default='')
class CalibrationVersion(Base):
    __tablename__='calibration_versions'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(60),unique=True)
    slope:Mapped[float]=mapped_column(Float)
    intercept:Mapped[float]=mapped_column(Float)
    state:Mapped[str]=mapped_column(String(20),default='active')
    metrics:Mapped[dict]=mapped_column(JSON)
    created_by:Mapped[str]=mapped_column(String(120),default='')
    created_at:Mapped[str]=mapped_column(String(40),default='')
    disabled_by:Mapped[str]=mapped_column(String(120),default='')
    disabled_at:Mapped[str]=mapped_column(String(40),default='')
    disabled_reason:Mapped[str]=mapped_column(String(600),default='')
class CalibrationSample(Base):
    __tablename__='calibration_samples'
    __table_args__=(UniqueConstraint('version_id','sample_id'),)
    id:Mapped[int]=mapped_column(primary_key=True)
    version_id:Mapped[int]=mapped_column(ForeignKey('calibration_versions.id'))
    sample_id:Mapped[int]=mapped_column(ForeignKey('reference_samples.id'))
