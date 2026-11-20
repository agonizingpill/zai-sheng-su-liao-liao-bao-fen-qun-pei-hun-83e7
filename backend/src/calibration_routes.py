from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import Session
from .security import current,allow
from .calibration_models import ReferenceSample,CalibrationVersion
from .calibration_schemas import RefSampleIn,SampleRevoke
from . import calibration_service as svc
router=APIRouter()
@router.get('/reference-samples')
def samples(u=Depends(current)):
    with Session() as s:return [svc.sample_view(s,x) for x in s.scalars(select(ReferenceSample).order_by(ReferenceSample.id.desc()))]
@router.post('/reference-samples')
def create_sample(p:RefSampleIn,u=Depends(current)):
    allow(u,'admin','blender')
    with Session.begin() as s:return svc.create_sample(s,p,u)
@router.post('/reference-samples/{id}/revoke')
def revoke_sample(id:int,p:SampleRevoke,u=Depends(current)):
    allow(u,'admin')
    with Session.begin() as s:return svc.revoke_sample(s,id,p,u)
@router.get('/calibration-versions')
def versions(u=Depends(current)):
    with Session() as s:return [svc.version_view(s,x) for x in s.scalars(select(CalibrationVersion).order_by(CalibrationVersion.id.desc()))]
@router.post('/calibration-versions')
def fit_version(u=Depends(current)):
    allow(u,'admin','blender')
    with Session.begin() as s:return svc.create_version(s,u)
