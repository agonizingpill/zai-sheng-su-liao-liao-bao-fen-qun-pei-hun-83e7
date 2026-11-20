from decimal import Decimal
from pydantic import BaseModel,Field
class RefSampleIn(BaseModel):
    code:str=Field(min_length=2,max_length=60)
    lot_id:int=Field(gt=0)
    instrument_ppm:Decimal=Field(ge=0,le=10000,max_digits=9,decimal_places=3)
    lab_ppm:Decimal=Field(ge=0,le=10000,max_digits=9,decimal_places=3)
class SampleRevoke(BaseModel):
    reason:str=Field(min_length=8,max_length=600)
