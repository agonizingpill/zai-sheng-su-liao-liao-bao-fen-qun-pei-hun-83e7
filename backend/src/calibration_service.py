"""Fit rapid-tester PVC calibration from paired reference readings, gate it on
leave-one-lot-out validation, and invalidate versions when a reference sample is revoked."""
import numpy as np
from decimal import Decimal
from datetime import datetime,timezone
from fastapi import HTTPException
from sqlalchemy import select
from .models import Bale
from .quality_models import SupplierLot
from .calibration_models import ReferenceSample,CalibrationVersion,CalibrationSample
from .blending import obj,get,audit

MIN_SAMPLES=3
MIN_LOTS=2

def now():return datetime.now(timezone.utc).isoformat()
def line(xs,ys):
    if len({float(v) for v in xs})<2:raise HTTPException(409,'快检仪读数没有差异，无法拟合校准直线')
    a,b=np.polyfit(np.array([float(v) for v in xs]),np.array([float(v) for v in ys]),1)
    return float(a),float(b)
def rmse(pairs):return round(float(np.sqrt(np.mean([(p-t)**2 for p,t in pairs]))),4)

def evaluate(samples):
    # Hold out one supplier lot at a time: fit on the remaining lots, score the held-out lot.
    lots={}
    for x in samples:lots.setdefault(x.lot_id,[]).append(x)
    if len(samples)<MIN_SAMPLES:raise HTTPException(409,f'有效参考样不足{MIN_SAMPLES}份，不能拟合校准')
    if len(lots)<MIN_LOTS:raise HTTPException(409,'有效参考样只覆盖一个供应批，无法按批留出验证')
    held=[]
    for lid in sorted(lots):
        train=[x for x in samples if x.lot_id!=lid]
        if len(train)<2:raise HTTPException(409,'按供应批留出后训练样本不足2份，先补充参考样')
        a,b=line([x.instrument_ppm for x in train],[x.lab_ppm for x in train])
        held+=[(a*float(x.instrument_ppm)+b,float(x.lab_ppm)) for x in lots[lid]]
    a,b=line([x.instrument_ppm for x in samples],[x.lab_ppm for x in samples])
    raw=[(float(x.instrument_ppm),float(x.lab_ppm)) for x in samples]
    fitted=[(a*float(x.instrument_ppm)+b,float(x.lab_ppm)) for x in samples]
    return a,b,{'sample_count':len(samples),'lot_count':len(lots),'holdout_scheme':'leave-one-lot-out 按供应批留出','holdout_rmse_raw':rmse(raw),'holdout_rmse_calibrated':rmse(held),'train_rmse_raw':rmse(raw),'train_rmse_calibrated':rmse(fitted)}

def apply(version,bale):
    val=(Decimal(str(version.slope))*bale.pvc_ppm+Decimal(str(version.intercept))).quantize(Decimal('0.001'))
    bale.cal_pvc_ppm=max(val,Decimal('0'));bale.calibration_version_id=version.id
def apply_active(s,bale):
    v=s.scalar(select(CalibrationVersion).where(CalibrationVersion.state=='active'))
    if v:apply(v,bale)
    else:bale.cal_pvc_ppm=None;bale.calibration_version_id=None

def version_view(s,v):
    d=obj(v)
    links=s.scalars(select(CalibrationSample).where(CalibrationSample.version_id==v.id).order_by(CalibrationSample.sample_id)).all()
    d['samples']=[{'sample_id':x.sample_id,'sample_code':s.get(ReferenceSample,x.sample_id).code} for x in links]
    return d
def sample_view(s,x):
    d=obj(x);lot=s.get(SupplierLot,x.lot_id);d['lot_code']=lot.code if lot else None
    d['used_by']=[s.get(CalibrationVersion,v).code for v in s.scalars(select(CalibrationSample.version_id).where(CalibrationSample.sample_id==x.id)).all()]
    return d

def create_sample(s,data,u):
    lot=get(s,SupplierLot,data.lot_id)
    x=ReferenceSample(**data.model_dump(),state='active',created_by=u['email'],created_at=now())
    s.add(x);s.flush();audit(s,u,'ref_sample_registered',f'{x.code} / {lot.code}');return sample_view(s,x)

def create_version(s,u):
    samples=s.scalars(select(ReferenceSample).where(ReferenceSample.state=='active').order_by(ReferenceSample.id)).all()
    a,b,metrics=evaluate(samples)
    improved=metrics['holdout_rmse_calibrated']<metrics['holdout_rmse_raw']
    v=CalibrationVersion(code='',slope=a,intercept=b,state='active' if improved else 'rejected',metrics={**metrics,'improved':improved},created_by=u['email'],created_at=now())
    s.add(v);s.flush();v.code=f'CAL-{v.id:04d}'
    for x in samples:s.add(CalibrationSample(version_id=v.id,sample_id=x.id))
    if improved:
        for old in s.scalars(select(CalibrationVersion).where(CalibrationVersion.state=='active',CalibrationVersion.id!=v.id).with_for_update()):old.state='superseded'
        # Recalibrate every bale under the newly enabled version; bales lock in id order like release does.
        for x in s.scalars(select(Bale).order_by(Bale.id).with_for_update()):apply(v,x)
    audit(s,u,'calibration_fitted',f"{v.code} / {v.state} / 留出RMSE {metrics['holdout_rmse_raw']}→{metrics['holdout_rmse_calibrated']}")
    return version_view(s,v)

def revoke_sample(s,id,data,u):
    x=get(s,ReferenceSample,id,True)
    if x.state!='active':raise HTTPException(409,'参考样已撤销，不可重复操作')
    reason=data.reason.strip()
    if len(reason)<8:raise HTTPException(409,'请填写至少8字的撤销依据')
    x.state='revoked';x.revoked_by=u['email'];x.revoked_at=now();x.revoke_reason=reason
    vids=list(s.scalars(select(CalibrationSample.version_id).where(CalibrationSample.sample_id==x.id)))
    versions=[];bales=[]
    if vids:
        # Lock bales first, then versions — the same order weighing/release uses, so revoking and
        # releasing serialize on the version row: whichever commits first wins, no double deduction.
        bales=s.scalars(select(Bale).where(Bale.calibration_version_id.in_(vids)).order_by(Bale.id).with_for_update()).all()
        versions=s.scalars(select(CalibrationVersion).where(CalibrationVersion.id.in_(vids),CalibrationVersion.state.in_(['active','superseded'])).order_by(CalibrationVersion.id).with_for_update()).all()
    why=f'参考样 {x.code} 已撤销：{reason}'
    disabled={v.id for v in versions}
    for v in versions:
        v.state='disabled';v.disabled_by=u['email'];v.disabled_at=now();v.disabled_reason=why
        audit(s,u,'calibration_disabled',f'{v.code} / {why}')
    for b in bales:
        # Keep the version pointer for traceability; the calibrated value is dropped so
        # clustering and weighing fall back to the raw instrument reading.
        if b.calibration_version_id in disabled:b.cal_pvc_ppm=None
    audit(s,u,'ref_sample_revoked',f'{x.code} / {reason}')
    return sample_view(s,x)
